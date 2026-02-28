"""
GEOPulse FastAPI Server — Backend API for the Dashboard Add-In

Endpoints:
    GET  /api/live-positions    → vehicles + deviation scores
    GET  /api/live-events       → exception events with version token
    GET  /api/driver/{id}       → full DNA + weekly delta
    GET  /api/anomalies         → high-deviation entities
    POST /api/generate-commentary → LLM sportscaster narration
    POST /api/write-back/group  → create Geotab group

Run: uvicorn server.server:app --port 8000 --reload
"""

import json
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mcp.duckdb_cache import DuckDBCache
from mcp.geotab_client import GeotabClient
from mcp.fleetdna import FleetDNA
from mcp.llm_provider import LLMProvider

logger = logging.getLogger(__name__)

# Paths
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ADDIN_DIR = os.path.join(BASE_DIR, "addin")

# Shared instances
cache = None
geotab = None
dna = None
llm = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize on startup, cleanup on shutdown."""
    global cache, geotab, dna, llm
    cache = DuckDBCache(db_path="geopulse.db")
    cache.initialize()
    geotab = GeotabClient(db_cache=cache)
    geotab.authenticate()
    dna = FleetDNA(geotab, cache)
    llm = LLMProvider(db_cache=cache)
    logger.info("GEOPulse server initialized")
    yield
    cache.close()


app = FastAPI(
    title="GEOPulse API",
    description="Backend API for the GEOPulse fleet intelligence dashboard",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS for Add-In (MyGeotab runs on a different origin)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve dashboard static files
app.mount("/css", StaticFiles(directory=os.path.join(ADDIN_DIR, "css")), name="css")
app.mount("/js", StaticFiles(directory=os.path.join(ADDIN_DIR, "js")), name="js")


@app.get("/")
async def serve_dashboard():
    """Serve the main dashboard HTML."""
    return FileResponse(os.path.join(ADDIN_DIR, "index.html"))


# === Request Models ===

class CommentaryRequest(BaseModel):
    events: list[dict] = []
    context: str = ""
    tone: str = "energetic but professional fleet safety sportscaster"

class TTSRequest(BaseModel):
    text: str
    voice: str = "en-US-Neural2-D"

class GroupRequest(BaseModel):
    name: str
    vehicle_ids: list[str] = []
    reason: str = ""

# === Endpoints ===

@app.get("/api/live-positions")
async def live_positions():
    """Get all vehicle positions with FleetDNA deviation scores."""
    positions = geotab.get_live_positions()
    rankings = dna.rank_fleet()
    rank_map = {r["entity_id"]: r for r in rankings}

    enriched = []
    for p in positions:
        rank_info = rank_map.get(p["device_id"], {})
        enriched.append({
            **p,
            "deviation_score": rank_info.get("deviation_score", 0),
            "anomaly_type": rank_info.get("anomaly_type", "none"),
        })

    return {
        "total": len(enriched),
        "anomalies": sum(1 for e in enriched if e["deviation_score"] > 70),
        "vehicles": enriched,
    }


@app.get("/api/live-events")
async def live_events(from_version: str = None):
    """Get live exception events for the ticker."""
    result = geotab.get_live_events(from_version)
    return {
        "events": result["events"][:50],
        "next_version": result.get("version"),
        "total": len(result["events"]),
    }


@app.get("/api/driver/{entity_id}")
async def driver_detail(entity_id: str):
    """Get full FleetDNA profile for a driver/vehicle."""
    entities = dna.get_entities()
    entity = next((e for e in entities if e["id"] == entity_id), None)

    if not entity:
        # Try partial name match
        entity = next(
            (e for e in entities if entity_id.lower() in e["name"].lower()),
            None,
        )

    if not entity:
        raise HTTPException(status_code=404, detail=f"Entity not found: {entity_id}")

    baseline = dna.build_baseline(entity["id"])
    today_score = dna.score_today(entity["id"])
    weekly = dna.get_weekly_delta(entity["id"])

    return {
        "entity": entity,
        "baseline": baseline,
        "today_score": today_score,
        "weekly_delta": weekly,
    }


@app.get("/api/anomalies")
async def anomalies(threshold: int = 60):
    """Get all entities above the deviation threshold."""
    rankings = dna.rank_fleet()
    anomalous = [r for r in rankings if r["deviation_score"] >= threshold]
    return {
        "threshold": threshold,
        "anomalies": anomalous,
        "total_checked": len(rankings),
    }


@app.post("/api/generate-commentary")
async def generate_commentary(req: CommentaryRequest):
    """Generate sportscaster-style commentary from events."""
    system_prompt = (
        f"You are a {req.tone}. "
        "Rules: "
        "- Voice: match the tone perfectly. "
        "- Celebrate good driving if tone allows: 'Marcus is having an absolute clinic today'. "
        "- Flag concerns with urgency: 'that's the third harsh brake this morning'. "
        "- Mention specific vehicle numbers and driver names. "
        "- When FleetDNA flags an anomaly, note it with the deviation percentage. "
        "- Keep each commentary update to 3-4 sentences max. "
        "- Never use corporate/robotic language. You're having fun with this. "
        "Return ONLY the spoken text, no formatting."
    )

    events_text = json.dumps(req.events[:10], default=str)
    prompt = f"Generate live commentary for these fleet events:\n{events_text}"
    if req.context:
        prompt += f"\n\nAdditional context: {req.context}"

    try:
        text = llm.generate_cached(
            prompt=prompt,
            system_prompt=system_prompt,
            cache_key=f"commentary_{hash(events_text) % 100000}",
            ttl_seconds=300,
        )
        return {"text": text, "provider": llm.get_info()["provider"]}
    except Exception as e:
        logger.warning(f"Commentary generation failed: {e}")
        # Build contextual fallback from real event data
        event_names = [ev.get("device_name", "Unknown") for ev in req.events[:3]]
        event_types = [ev.get("rule_name", "event") for ev in req.events[:3]]
        vehicle_count = len(set(ev.get("device_id", "") for ev in req.events)) if req.events else 0

        if event_types and event_names:
            fallback = (
                f"We've got action across the fleet right now — {vehicle_count} vehicles on the board. "
                f"{event_names[0]} just triggered a {event_types[0].lower()} alert. "
                f"{'Meanwhile, ' + event_names[1] + ' is also lighting up with ' + event_types[1].lower() + '. ' if len(event_names) > 1 else ''}"
                f"Stay tuned, this fleet never sleeps!"
            )
        else:
            fallback = (
                "The fleet is humming along right now. All vehicles on the board, "
                "no major flags at this moment. A calm stretch in operations — "
                "but we'll keep our eyes on it. Stay tuned!"
            )
        return {"text": fallback, "provider": "fallback"}


@app.post("/api/tts")
async def generate_tts(req: TTSRequest):
    """Generate TTS audio using Google Cloud Text-to-Speech."""
    # Check cache first
    if cache:
        # Include voice in cache key to avoid mixing different voices
        # for the same text
        cache_key = f"{req.text}_{req.voice}"
        cached_path = cache.get_tts_cache(cache_key)
        if cached_path and os.path.exists(cached_path):
            return FileResponse(cached_path, media_type="audio/mpeg")

    try:
        from google.cloud import texttospeech
        import hashlib

        # Instantiates a client
        client = texttospeech.TextToSpeechClient()

        # Set the text input to be synthesized
        synthesis_input = texttospeech.SynthesisInput(text=req.text)

        # Build the voice request, select the language code and the ssml
        # voice gender ("neutral")
        parts = req.voice.split("-")
        lang_code = "-".join(parts[:2]) if len(parts) >= 2 else "en-US"
        voice = texttospeech.VoiceSelectionParams(
            language_code=lang_code,
            name=req.voice
        )

        # Select the type of audio file you want returned
        audio_config = texttospeech.AudioConfig(
            audio_encoding=texttospeech.AudioEncoding.MP3
        )

        # Perform the text-to-speech request on the text input with the selected
        # voice parameters and audio file type
        response = client.synthesize_speech(
            input=synthesis_input, voice=voice, audio_config=audio_config
        )

        os.makedirs(os.path.join(BASE_DIR, "audio"), exist_ok=True)
        filename = hashlib.sha256(f"{req.text}_{req.voice}".encode()).hexdigest()[:16] + ".mp3"
        filepath = os.path.join(BASE_DIR, "audio", filename)

        with open(filepath, "wb") as out:
            # Write the response to the output file.
            out.write(response.audio_content)

        if cache:
            # Include voice in cache key when setting the cache as well
            cache.set_tts_cache(f"{req.text}_{req.voice}", filepath)

        return FileResponse(filepath, media_type="audio/mpeg")
    except Exception as e:
        logger.error(f"TTS failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/write-back/group")
async def create_group_endpoint(req: GroupRequest):
    """Write-back: Create a group in Geotab."""
    try:
        group_id = geotab.create_group(req.name, req.vehicle_ids)
        return {
            "success": True,
            "group_id": group_id,
            "name": req.name,
            "vehicles_assigned": len(req.vehicle_ids),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health")
async def health():
    """Health check."""
    return {
        "status": "ok",
        "llm_provider": llm.get_info()["provider"],
        "llm_model": llm.get_info()["model"],
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server.server:app", host="0.0.0.0", port=8000, reload=True)

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
import html as _html

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s  [%(name)s] %(message)s",
)

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
from mcp.ace_client import AceClient
from mcp.email_sender import send_email
from frequencies.manager_email import generate_manager_brief, generate_manager_email_html

logger = logging.getLogger(__name__)

# Paths
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LANDING_PATH = os.path.join(BASE_DIR, "index.html")
LANDING_IMAGE_PATH = os.path.join(BASE_DIR, "geotab.png")
_dashboard_candidate = os.path.join(BASE_DIR, "dashboard")
_addin_candidate = os.path.join(BASE_DIR, "addin")
DASHBOARD_DIR = _dashboard_candidate if os.path.exists(os.path.join(_dashboard_candidate, "index.html")) else _addin_candidate
DASHBOARD_PATH = os.path.join(DASHBOARD_DIR, "index.html")
DASHBOARD_ICON_PATH = os.path.join(DASHBOARD_DIR, "icon.svg")

# Shared instances
cache = None
geotab = None
dna = None
llm = None
ace = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize on startup, cleanup on shutdown."""
    global cache, geotab, dna, llm, ace
    cache = DuckDBCache(db_path="geopulse.db")
    cache.initialize()
    geotab = GeotabClient(db_cache=cache)
    geotab.authenticate()
    dna = FleetDNA(geotab, cache)
    llm = LLMProvider(db_cache=cache)
    ace = AceClient(db_cache=cache)
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
dashboard_css_dir = os.path.join(DASHBOARD_DIR, "css")
dashboard_js_dir = os.path.join(DASHBOARD_DIR, "js")
if os.path.isdir(dashboard_css_dir):
    app.mount("/css", StaticFiles(directory=dashboard_css_dir), name="css")
if os.path.isdir(dashboard_js_dir):
    app.mount("/js", StaticFiles(directory=dashboard_js_dir), name="js")


@app.get("/")
async def serve_landing():
    """Serve the main landing HTML."""
    if os.path.exists(LANDING_PATH):
        return FileResponse(LANDING_PATH)
    return FileResponse(DASHBOARD_PATH)


@app.get("/dashboard")
@app.get("/dashboard/")
@app.get("/dashboard/index.html")
async def serve_dashboard():
    """Serve the dashboard HTML."""
    return FileResponse(DASHBOARD_PATH)


@app.get("/icon.svg")
@app.get("/dashboard/icon.svg")
async def serve_icon():
    """Serve app icon for favicon and UI."""
    if os.path.exists(DASHBOARD_ICON_PATH):
        return FileResponse(DASHBOARD_ICON_PATH)
    raise HTTPException(status_code=404, detail="Icon not found")


@app.get("/favicon.ico")
async def serve_favicon():
    """Serve favicon path used by browsers."""
    if os.path.exists(DASHBOARD_ICON_PATH):
        return FileResponse(DASHBOARD_ICON_PATH)
    raise HTTPException(status_code=404, detail="Favicon not found")


@app.get("/geotab.png")
async def serve_landing_image():
    """Serve landing page hero screenshot image."""
    if os.path.exists(LANDING_IMAGE_PATH):
        return FileResponse(LANDING_IMAGE_PATH)
    raise HTTPException(status_code=404, detail="Landing image not found")


# === Request Models ===

class CommentaryRequest(BaseModel):
    events: list[dict] = []
    context: str = ""
    tone: str = "energetic but professional fleet safety sportscaster"

class TTSRequest(BaseModel):
    text: str
    voice: str = "en-US-Journey-D"

class GroupRequest(BaseModel):
    name: str
    vehicle_ids: list[str] = []
    reason: str = ""

class AceQueryRequest(BaseModel):
    question: str

class ReportRequest(BaseModel):
    entity_id: str
    report_type: str = "incident"  # "incident" or "coaching"

class SendMailRequest(BaseModel):
    email: str
    summary_text: str = ""
    audio_b64: str | None = None
    include_overview: bool = True

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
        "anomalies": sum(1 for e in enriched if e["deviation_score"] >= 60),
        "vehicles": enriched,
    }


@app.get("/api/live-events")
async def live_events(from_version: str = None):
    """Get live exception events for the ticker."""
    result = geotab.get_live_events(from_version)
    return {
        "events": result["events"][:200],
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


# ---------------------------------------------------------------------------
# Shared TTS helper — called both by /api/tts and /api/generate-commentary
# ---------------------------------------------------------------------------
import re as _re
import base64 as _b64
import asyncio as _asyncio

async def _synthesize_to_b64(text: str, voice: str = "en-US-Journey-D") -> str | None:
    """Return base64-encoded MP3 audio or None on failure."""
    api_key = os.getenv("GOOGLE_TTS_API_KEY") or os.getenv("GEMINI_API_KEY")
    if not api_key:
        return None
    try:
        import requests as _req_inner
        clean = _re.sub(r'\*+|#+|`+|_{2,}|~+', '', text)
        clean = _re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', clean)
        clean = _re.sub(r'\s+', ' ', clean).strip()
        parts = voice.split("-")
        lang_code = "-".join(parts[:2]) if len(parts) >= 2 else "en-US"
        payload = {
            "input": {"text": clean},
            "voice": {"languageCode": lang_code, "name": voice},
            "audioConfig": {
                "audioEncoding": "MP3",
                "speakingRate": 1.05,
                "pitch": 0.0,
                "volumeGainDb": 1.0,
                "effectsProfileId": ["headphone-class-device"],
            },
        }
        is_journey = "Journey" in voice
        api_version = "v1beta1" if is_journey else "v1"

        def _post(url, body):
            return _req_inner.post(url, json=body, timeout=20)  # Journey can take up to 15s

        resp = await _asyncio.to_thread(
            _post,
            f"https://texttospeech.googleapis.com/{api_version}/text:synthesize?key={api_key}",
            payload,
        )
        if not resp.ok and is_journey:
            payload["voice"]["name"] = f"{lang_code}-Neural2-D"
            payload["audioConfig"].pop("effectsProfileId", None)
            resp = await _asyncio.to_thread(
                _post,
                f"https://texttospeech.googleapis.com/v1/text:synthesize?key={api_key}",
                payload,
            )
        resp.raise_for_status()
        return resp.json().get("audioContent")  # already base64
    except Exception as e:
        logger.warning(f"TTS synthesis failed: {e}")
        return None


@app.post("/api/generate-commentary")
async def generate_commentary(req: CommentaryRequest):
    """Generate sportscaster-style commentary and TTS audio in one shot."""
    system_prompt = (
        f"You are an {req.tone} broadcasting live fleet intelligence updates for GEOPulse — "
        "an AI-powered fleet behavioral analytics platform that uses FleetDNA fingerprinting to detect anomalies.\n\n"
        "YOUR BROADCAST STYLE:\n"
        "- Deliver 5-7 sentences of rich, insightful commentary — like an ESPN analyst breaking down the action.\n"
        "- Open with a punchy hook about the fleet's current state.\n"
        "- Call out specific vehicles and events by name, explaining what they mean operationally "
        "(e.g. harsh braking could indicate road hazards, fatigue, or aggressive driving patterns).\n"
        "- Reference FleetDNA deviation scores when provided — explain what high scores mean "
        "(the driver/vehicle is behaving unusually compared to their historical baseline).\n"
        "- Weave in fleet-wide context: how many vehicles are active, anomaly trends, safety patterns.\n"
        "- Close with a forward-looking take — what to watch for, who's trending up or down.\n\n"
        "STRICT RULES:\n"
        "- ONLY reference vehicle names, event types, and scores EXACTLY as given in the data below.\n"
        "- Do NOT invent driver names, speeds, scores, or any details not in the data.\n"
        "- If a driver name is provided, use it. If not, refer to the vehicle name.\n"
        "- Use an upbeat, human sportscaster voice — energetic but professional, never robotic or corporate.\n"
        "- Do NOT wrap your response in quotes or add any labels/formatting.\n"
        "Return ONLY the spoken commentary text."
    )

    # Build a rich event summary for the LLM
    event_lines = []
    for i, ev in enumerate(req.events[:10], 1):
        line = f"{i}. {ev.get('device_name','Unknown')} — {ev.get('rule_name','event')}"
        if ev.get('driver_name'):
            line += f" (driver: {ev['driver_name']})"
        if ev.get('deviation_score'):
            line += f" [FleetDNA deviation: {ev['deviation_score']}/100]"
        event_lines.append(line)
    event_block = "\n".join(event_lines) if event_lines else "No specific events at this moment."

    prompt = (
        f"LIVE FLEET FEED — {len(req.events)} active events:\n"
        f"{event_block}\n\n"
    )
    if req.context:
        prompt += f"FLEET STATUS: {req.context}\n"
    prompt += "\nDeliver your broadcast now."

    # Cache key: vehicle/rule pairs + 1-minute bucket → fresh commentary each minute
    # but cache hits within the same minute for repeated clicks
    import time as _time
    minute_bucket = int(_time.time() // 60)
    cache_fingerprint = "|".join(
        f"{ev.get('device_name','')}/{ev.get('rule_name','')}"
        for ev in req.events[:8]
    )
    cache_key = f"commentary_{hash(cache_fingerprint) % 1000000}_{minute_bucket}"

    try:
        text = await _asyncio.to_thread(
            llm.generate_cached,
            prompt=prompt,
            system_prompt=system_prompt,
            cache_key=cache_key,
            ttl_seconds=120,
            max_tokens=500,
        )
        # Strip wrapper quotes the LLM sometimes adds
        text = text.strip().strip('"').strip("'").strip()
        audio_b64 = await _synthesize_to_b64(text)
        return {"text": text, "audio_b64": audio_b64 or None, "provider": llm.get_info()["provider"]}
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
        audio_b64 = None
        return {"text": fallback, "provider": "fallback", "audio_b64": audio_b64}


@app.post("/api/tts")
async def generate_tts(req: TTSRequest):
    """Generate TTS audio using Google Cloud Text-to-Speech REST API."""
    # Check cache first
    if cache:
        cache_key = f"{req.text}_{req.voice}"
        cached_path = cache.get_tts_cache(cache_key)
        if cached_path and os.path.exists(cached_path):
            return FileResponse(cached_path, media_type="audio/mpeg")

    api_key = os.getenv("GOOGLE_TTS_API_KEY") or os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="GOOGLE_TTS_API_KEY not set in .env")

    try:
        import hashlib

        audio_b64 = await _synthesize_to_b64(req.text, req.voice)
        if not audio_b64:
            # Return a soft error instead of 500 — frontend falls back to browser speech
            raise HTTPException(status_code=503, detail="TTS temporarily unavailable")

        audio_bytes = _b64.b64decode(audio_b64)

        os.makedirs(os.path.join(BASE_DIR, "audio"), exist_ok=True)
        filename = hashlib.sha256(f"{req.text}_{req.voice}".encode()).hexdigest()[:16] + ".mp3"
        filepath = os.path.join(BASE_DIR, "audio", filename)

        with open(filepath, "wb") as out:
            out.write(audio_bytes)

        if cache:
            cache.set_tts_cache(f"{req.text}_{req.voice}", filepath)

        return FileResponse(filepath, media_type="audio/mpeg")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"TTS failed: {e}")
        raise HTTPException(status_code=503, detail="TTS temporarily unavailable")


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


@app.post("/api/send-mail")
async def send_mail(req: SendMailRequest):
    """Send manager overview email with optional audio summary attachment."""
    if "@" not in req.email:
        raise HTTPException(status_code=400, detail="Invalid email address")

    try:
        rankings = dna.rank_fleet()
        events_result = geotab.get_live_events()
        positions = geotab.get_live_positions()
        anomalies = [r for r in rankings if r.get("deviation_score", 0) > 40]

        fleet_summary = {
            "total_vehicles": len(positions),
            "anomaly_count": len(anomalies),
            "event_count": len(events_result.get("events", [])),
            "anomalies": anomalies[:5],
            "top_rankings": rankings[:5],
        }

        overview = ""
        if req.include_overview:
            fleet_data = {
                "rankings": rankings[:10],
                "events": events_result.get("events", [])[:10],
                "anomalies": anomalies[:10],
            }
            overview = await _asyncio.to_thread(generate_manager_brief, fleet_data, llm)

        primary_text = overview or req.summary_text or "No summary available."
        email_html = generate_manager_email_html(primary_text, fleet_summary)

        if req.summary_text:
            safe_summary = _html.escape(req.summary_text).replace("\n", "<br>")
            email_html += f"""
            <div style=\"max-width: 600px; margin: 12px auto 0; background: #161B22; color: #E6EDF3;
                 border: 1px solid #30363D; border-radius: 12px; padding: 16px;\">
                <h3 style=\"margin: 0 0 8px; font-size: 14px; color: #7D8590; text-transform: uppercase;\">Audio Broadcast Summary</h3>
                <div style=\"font-size: 14px; line-height: 1.6;\">{safe_summary}</div>
            </div>
            """

        attachment_path = None
        if req.audio_b64:
            try:
                import hashlib
                audio_bytes = _b64.b64decode(req.audio_b64)
                os.makedirs(os.path.join(BASE_DIR, "audio"), exist_ok=True)
                file_name = f"manager_brief_{hashlib.sha256(audio_bytes).hexdigest()[:12]}.mp3"
                attachment_path = os.path.join(BASE_DIR, "audio", file_name)
                with open(attachment_path, "wb") as audio_file:
                    audio_file.write(audio_bytes)
            except Exception as audio_err:
                logger.warning(f"Failed to decode audio attachment: {audio_err}")

        from datetime import datetime as _dt
        subject = f"📡 GEOPulse Overview — {_dt.now().strftime('%A, %B %d')}"
        result = await _asyncio.to_thread(
            send_email,
            req.email,
            subject,
            email_html,
            "GEOPulse",
            attachment_path,
        )

        if not result.get("success"):
            raise HTTPException(status_code=500, detail=result.get("error", "Email send failed"))

        return {
            "success": True,
            "email": req.email,
            "message_id": result.get("message_id"),
            "included_overview": bool(overview),
            "included_audio": bool(attachment_path),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health")
async def health():
    """Health check."""
    return {
        "status": "ok",
        "llm_provider": llm.get_info()["provider"],
        "llm_model": llm.get_info()["model"],
        "ace_available": ace is not None,
    }


@app.post("/api/ace-query")
async def ace_query(req: AceQueryRequest):
    """Query Geotab Ace AI with a natural language question."""
    import asyncio
    try:
        # Run blocking Ace call in a thread pool
        result = await asyncio.to_thread(ace.query, req.question)
        return {
            "answer": result.get("answer", ""),
            "data": result.get("data", []),
            "columns": result.get("columns", []),
            "reasoning": result.get("reasoning", ""),
            "source": "ace",
        }
    except Exception as e:
        logger.warning(f"Ace query failed, falling back to LLM: {e}")
        # Fallback: use local LLM with available fleet context
        try:
            from datetime import date as _date
            # Use already-loaded state to avoid expensive re-queries
            fleet_context = json.dumps({
                "total_vehicles": len(geotab.get_all_devices()),
                "recent_anomalies": [
                    {"name": r["name"], "score": r["deviation_score"], "type": r["anomaly_type"]}
                    for r in (dna.cache.get_rankings(_date.today()) or [])
                    if r.get("deviation_score", 0) > 40
                ][:5],
                "ace_unavailable": True,
                "ace_error": str(e),
            })
            answer = llm.generate(
                prompt=f"Answer this fleet management question using the context below.\n\nQuestion: {req.question}\n\nFleet context: {fleet_context}",
                system_prompt="You are a fleet analytics AI. Answer questions concisely from the provided context. "
                              "If Ace AI is unavailable, note that answers are approximate based on cached data.",
            )
            return {
                "answer": answer,
                "data": [],
                "columns": [],
                "reasoning": "",
                "source": "local_llm",
            }
        except Exception as fallback_err:
            raise HTTPException(status_code=500, detail=str(fallback_err))


@app.post("/api/generate-report")
async def generate_report(req: ReportRequest):
    """Generate an AI incident or coaching report for an entity."""
    import asyncio
    try:
        # Gather entity data
        baseline = dna.build_baseline(req.entity_id)
        today_score = dna.score_today(req.entity_id)
        events_result = geotab.get_live_events()
        entity_events = [
            e for e in events_result.get("events", [])
            if e.get("device_id") == req.entity_id or e.get("driver_id") == req.entity_id
        ][:10]

        # Build context
        context = json.dumps({
            "entity_id": req.entity_id,
            "baseline": baseline,
            "today_score": today_score,
            "recent_events": entity_events,
        }, default=str)

        if req.report_type == "coaching":
            system_prompt = (
                "You are a fleet safety coach. Generate a structured coaching report in Markdown.\n"
                "Use EXACTLY this structure:\n"
                "## Driver Coaching Report\n"
                "### Overview\n"
                "One paragraph: summarize driving behavior, deviation score, and overall assessment.\n"
                "### Key Observations\n"
                "- Bullet points of notable behaviors from the telemetry data\n"
                "- Reference actual metric values (speeds, distances, idle ratios)\n"
                "### Recommended Actions\n"
                "1. Numbered specific, actionable coaching items\n"
                "2. Each action should be concrete and measurable\n"
                "### Positive Notes\n"
                "Acknowledge any good behaviors or improvements visible in the data.\n\n"
                "RULES: Keep it 150-200 words. Use ONLY data provided — never invent facts.\n"
                "Reference actual z-scores and metric values from the context."
            )
        else:
            system_prompt = (
                "You are a fleet operations analyst. Generate a formal incident report in Markdown.\n"
                "Use EXACTLY this structure:\n"
                "## Incident Report\n"
                "### Summary\n"
                "Brief overview of the anomaly/incident with entity ID and date.\n"
                "### Contributing Factors\n"
                "- Bullet points of specific factors from the telemetry data\n"
                "### Telemetry Analysis\n"
                "| Metric | Today | Baseline | Z-Score | Status |\n"
                "|--------|-------|----------|---------|--------|\n"
                "Table rows for each metric from the data. Use the actual values.\n"
                "### Risk Assessment\n"
                "Overall risk level (Low/Medium/High/Critical) with justification.\n"
                "### Recommended Actions\n"
                "1. Numbered immediate and long-term action items\n\n"
                "RULES: Keep it 200-250 words. Professional tone. Use ONLY data provided.\n"
                "Reference actual z-scores and deviation values from the context."
            )

        report = await asyncio.to_thread(
            llm.generate,
            prompt=f"Generate a {req.report_type} report for this entity:\n{context}",
            system_prompt=system_prompt,
        )
        return {
            "report": report,
            "report_type": req.report_type,
            "entity_id": req.entity_id,
            "provider": llm.get_info()["provider"],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/trip-replay/{device_id}")
async def trip_replay(device_id: str):
    """Get GPS breadcrumbs for trip replay animation."""
    import asyncio
    try:
        trips = await asyncio.to_thread(geotab.get_driver_trips, device_id, 1)
        if not trips:
            return {"trips": [], "points": []}

        # Get GPS log records for the most recent trip
        latest_trip = trips[0]
        from_date = latest_trip.get("start", "")
        to_date = latest_trip.get("stop", "")

        # Fetch LogRecord breadcrumbs for this trip
        try:
            log_records = await asyncio.to_thread(
                geotab._cached_call,
                f"logrec_{device_id}_{from_date[:10]}",
                300,
                "Get",
                {
                    "typeName": "LogRecord",
                    "search": {
                        "deviceSearch": {"id": device_id},
                        "fromDate": from_date,
                        "toDate": to_date,
                    },
                    "resultsLimit": 500,
                }
            )
        except Exception:
            log_records = []

        points = []
        for rec in (log_records or []):
            lat = rec.get("latitude", 0)
            lon = rec.get("longitude", 0)
            if lat and lon and lat != 0 and lon != 0:
                points.append({
                    "lat": lat,
                    "lng": lon,
                    "time": rec.get("dateTime", ""),
                    "speed": rec.get("speed", 0),
                })

        return {
            "trip": {
                "start": from_date,
                "stop": to_date,
                "distance": latest_trip.get("distance", 0),
            },
            "points": points,
            "total_points": len(points),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server.server:app", host="0.0.0.0", port=8000, reload=True)

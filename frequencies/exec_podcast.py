"""
Frequency 3: Executive Podcast — Two-Host Fleet Analytics Podcast

Every Monday at 5 AM, generates a 5-minute two-host podcast episode:
- Alex (lead) and Jamie (analyst/counterpoint)
- Uses Gemini Pro for deeper analysis, falls back to Flash/Ollama
- TTS with two distinct voices (or text-only in Ollama mode)

Pipeline: Week data → LLM script → Two-voice TTS → Publish
"""

import os
import sys
import json
import logging
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mcp.duckdb_cache import DuckDBCache
from mcp.geotab_client import GeotabClient
from mcp.fleetdna import FleetDNA
from mcp.llm_provider import LLMProvider
from mcp.google_publisher import publish_podcast_episode, publish_to_sheets

logger = logging.getLogger(__name__)

PODCAST_PROMPT = """You are writing a script for a two-host fleet analytics podcast.
Host 1 name: Alex. Host 2 name: Jamie.
Rules:
- Alex leads, Jamie provides depth and counterpoints
- Structure: Cold open hook → Week's top story → Safety deep dive
             → Driver spotlight (one good, one improving)
             → Prediction for next week → Sign-off
- Each episode: 600-700 words (5 min when spoken at natural pace)
- Make specific references to real data: vehicle numbers, driver names,
  percentages, dollar amounts. No vague statements.
- Jamie should challenge Alex at least once ("But Alex, isn't the real
  story here...") — it makes it feel real
- One "story of the week" — the most interesting fleet narrative from the data
- End with one specific prediction for next week based on trends
- Format: Alex: [text] \\n Jamie: [text] — no stage directions
"""


def generate_podcast_script(week_data, llm_provider):
    """Generate a two-host podcast script from weekly fleet data."""
    prompt = f"Generate a two-host podcast episode script from this week's fleet data:\n{json.dumps(week_data, indent=2, default=str)}"

    # Use a more capable model for podcast (Pro if Gemini, larger if Ollama)
    original_model = llm_provider.model
    if llm_provider.provider == "gemini":
        llm_provider.model = "gemini-2.0-flash"  # Flash is good enough
    elif llm_provider.provider == "ollama":
        llm_provider.model = os.getenv("LLM_MODEL", "llama3.2")

    script = llm_provider.generate_cached(
        prompt=prompt,
        system_prompt=PODCAST_PROMPT,
        cache_key=f"podcast_{datetime.now().strftime('%Y_W%W')}",
        ttl_seconds=86400,
        temperature=0.85,
        max_tokens=4096,
    )

    llm_provider.model = original_model
    return script


def generate_podcast_audio(script_text, db_cache=None):
    """Generate two-voice TTS audio. Returns file path or None."""
    provider = os.getenv("LLM_PROVIDER", "gemini")

    if provider == "ollama":
        logger.info("Ollama mode: skipping podcast TTS")
        return None

    if db_cache:
        cached = db_cache.get_tts_cache(script_text[:500])  # Use first 500 chars as key
        if cached:
            return cached

    try:
        from google.cloud import texttospeech

        client = texttospeech.TextToSpeechClient()

        # Parse script into Alex and Jamie lines
        lines = script_text.strip().split("\n")
        audio_segments = []

        for line in lines:
            line = line.strip()
            if not line:
                continue

            if line.startswith("Alex:"):
                text = line[5:].strip()
                voice_name = "en-US-Neural2-J"  # Confident male
            elif line.startswith("Jamie:"):
                text = line[6:].strip()
                voice_name = "en-US-Neural2-F"  # Analytical female
            else:
                text = line
                voice_name = "en-US-Neural2-J"

            if not text:
                continue

            voice = texttospeech.VoiceSelectionParams(
                language_code="en-US", name=voice_name
            )
            audio_config = texttospeech.AudioConfig(
                audio_encoding=texttospeech.AudioEncoding.MP3,
                speaking_rate=1.0,
                pitch=0.0,
            )
            response = client.synthesize_speech(
                input=texttospeech.SynthesisInput(text=text),
                voice=voice,
                audio_config=audio_config,
            )
            audio_segments.append(response.audio_content)

        if not audio_segments:
            return None

        # Concatenate MP3 segments (simple concatenation works for MP3)
        os.makedirs("audio", exist_ok=True)
        week_num = datetime.now().strftime("%W")
        filepath = f"audio/podcast_week{week_num}.mp3"

        with open(filepath, "wb") as f:
            for segment in audio_segments:
                f.write(segment)

        if db_cache:
            db_cache.set_tts_cache(script_text[:500], filepath)

        logger.info(f"Generated podcast audio: {filepath}")
        return filepath

    except Exception as e:
        logger.warning(f"Podcast TTS failed: {e}")
        return None


def gather_week_data(geotab_client, fleet_dna):
    """Gather all data needed for the podcast episode."""
    rankings = fleet_dna.rank_fleet()
    entities = fleet_dna.get_entities()

    # Top performers and most anomalous
    top_performers = sorted(rankings, key=lambda x: x["deviation_score"])[:5]
    most_anomalous = sorted(rankings, key=lambda x: x["deviation_score"], reverse=True)[:5]

    # Fleet-wide stats
    total_entities = len(entities)
    entities_with_data = [r for r in rankings if r["deviation_score"] > 0]
    avg_deviation = sum(r["deviation_score"] for r in rankings) / max(len(rankings), 1)

    # Weekly deltas for spotlight entities
    spotlights = {}
    for entity in (top_performers[:2] + most_anomalous[:2]):
        try:
            delta = fleet_dna.get_weekly_delta(entity["entity_id"])
            spotlights[entity["name"]] = delta
        except Exception:
            pass

    # Events summary
    try:
        events = geotab_client.get_live_events()
        event_count = len(events.get("events", []))
    except Exception:
        event_count = 0

    # Faults summary
    try:
        faults = geotab_client.get_active_faults()
    except Exception:
        faults = []

    return {
        "week_number": datetime.now().strftime("%W"),
        "year": datetime.now().year,
        "total_vehicles": total_entities,
        "vehicles_with_data": len(entities_with_data),
        "avg_deviation_score": round(avg_deviation, 1),
        "top_performers": top_performers,
        "most_anomalous": most_anomalous,
        "driver_spotlights": spotlights,
        "total_events_24h": event_count,
        "active_faults": len(faults),
        "fault_samples": faults[:5],
    }


def run_monday_podcast():
    """Main Monday pipeline: gather data → script → audio → publish."""
    cache = DuckDBCache(db_path="geopulse.db")
    cache.initialize()
    client = GeotabClient(db_cache=cache)
    client.authenticate()
    fleet_dna = FleetDNA(client, cache)
    llm_provider = LLMProvider(db_cache=cache)

    # Gather data
    week_data = gather_week_data(client, fleet_dna)

    # Generate script
    script = generate_podcast_script(week_data, llm_provider)

    # Generate audio
    audio_path = generate_podcast_audio(script, cache)

    # Publish to Google services
    week_num = week_data.get("week_number", datetime.now().strftime("%W"))
    summary = script[:300] if script else "Weekly fleet intelligence update"
    publish_result = publish_podcast_episode(
        episode_number=week_num,
        audio_path=audio_path,
        script_text=script,
        week_summary=summary,
    )

    # Also update Sheets with full week data
    publish_to_sheets(week_data, summary)

    cache.close()
    return {
        "script": script,
        "audio_path": audio_path,
        "week_data_summary": {
            "week": week_data["week_number"],
            "vehicles": week_data["total_vehicles"],
            "avg_deviation": week_data["avg_deviation_score"],
        },
        "publish_result": publish_result,
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("🎧 Running Executive Podcast Pipeline (test mode)...")

    cache = DuckDBCache(db_path="geopulse.db")
    cache.initialize()
    client = GeotabClient(db_cache=cache)
    client.authenticate()
    fleet_dna = FleetDNA(client, cache)
    llm_provider = LLMProvider(db_cache=cache)

    week_data = gather_week_data(client, fleet_dna)
    print(f"\n📊 Week {week_data['week_number']} Data:")
    print(f"   Vehicles: {week_data['total_vehicles']}")
    print(f"   Avg deviation: {week_data['avg_deviation_score']}")
    print(f"   Events (24h): {week_data['total_events_24h']}")
    print(f"   Active faults: {week_data['active_faults']}")

    print(f"\n🎙️ Generating podcast script...")
    script = generate_podcast_script(week_data, llm_provider)
    print(f"   Script ({len(script)} chars):")
    print(f"   {script[:300]}...")

    cache.close()

"""
Frequency 1: Driver Feed — Personal Audio + Email Pipeline

Every Friday at 5 PM, each driver gets:
- A personal 90-second audio coaching clip (TTS or text-only with Ollama)
- An HTML email with personalized stats and metric bars

Pipeline: FleetDNA weekly delta → LLM script → TTS audio → HTML email → Gmail send
"""

import os
import sys
import json
import hashlib
import logging
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mcp.duckdb_cache import DuckDBCache
from mcp.geotab_client import GeotabClient
from mcp.fleetdna import FleetDNA
from mcp.llm_provider import LLMProvider
from mcp.email_sender import send_driver_email

logger = logging.getLogger(__name__)

DRIVER_COACH_PROMPT = """You are a warm, encouraging fleet safety coach generating a personal
weekly audio script for a driver. Rules:
- Always use their first name
- Lead with something positive and specific (not generic)
- Mention ONE specific rough moment with exact day, time, and location
  (e.g. "Wednesday morning on the I-95 on-ramp at 8:42 AM")
- Compare to THEIR OWN normal, never to fleet average
  (e.g. "that's not your usual pattern on that stretch")
- Include fleet rank out of total drivers
- End warmly and specifically
- Maximum 150 words. Must sound natural when spoken aloud.
- Never mention data, algorithms, or scores. Just coach.
- Tone: like a trusted colleague, not a corporate report"""


def generate_driver_script(driver_name, weekly_delta, exceptions, llm_provider):
    """Generate a personalized coaching script for one driver."""
    data = {
        "driver_name": driver_name,
        "weekly_summary": weekly_delta,
        "recent_exceptions": exceptions[:5],
    }
    prompt = f"Generate a 90-second personal coaching audio script for this driver:\n{json.dumps(data, indent=2, default=str)}"

    script = llm_provider.generate_cached(
        prompt=prompt,
        system_prompt=DRIVER_COACH_PROMPT,
        cache_key=f"driver_script_{driver_name}_{datetime.now().strftime('%Y_W%W')}",
        ttl_seconds=86400,
        temperature=0.8,
    )
    return script


def generate_driver_audio(script_text, driver_name, db_cache=None):
    """Generate TTS audio from script. Returns file path or None."""
    provider = os.getenv("LLM_PROVIDER", "gemini")

    # Skip TTS if using Ollama (local mode)
    if provider == "ollama":
        logger.info(f"Ollama mode: skipping TTS for {driver_name}")
        return None

    # Check TTS cache
    if db_cache:
        cached = db_cache.get_tts_cache(script_text)
        if cached:
            logger.info(f"TTS cache hit for {driver_name}")
            return cached

    try:
        from google.cloud import texttospeech

        client = texttospeech.TextToSpeechClient()

        synthesis_input = texttospeech.SynthesisInput(text=script_text)
        voice = texttospeech.VoiceSelectionParams(
            language_code="en-US",
            name="en-US-Neural2-D",  # Warm male voice
            ssml_gender=texttospeech.SsmlVoiceGender.MALE,
        )
        audio_config = texttospeech.AudioConfig(
            audio_encoding=texttospeech.AudioEncoding.MP3,
            speaking_rate=0.95,
            pitch=-1.0,
        )

        response = client.synthesize_speech(
            input=synthesis_input, voice=voice, audio_config=audio_config
        )

        os.makedirs("audio", exist_ok=True)
        week_num = datetime.now().strftime("%W")
        safe_name = driver_name.replace(" ", "_").lower()
        filepath = f"audio/{safe_name}_week{week_num}.mp3"

        with open(filepath, "wb") as f:
            f.write(response.audio_content)

        if db_cache:
            db_cache.set_tts_cache(script_text, filepath)

        logger.info(f"Generated audio: {filepath}")
        return filepath

    except Exception as e:
        logger.warning(f"TTS generation failed for {driver_name}: {e}")
        return None


def generate_driver_email_html(driver_name, weekly_delta, audio_url=None, rank_info=None):
    """Generate beautiful HTML email with personalized stats."""
    week_num = datetime.now().strftime("%W")
    metrics = weekly_delta.get("week_vs_baseline", {})

    # Build metric bars
    metric_bars = ""
    for metric, data in metrics.items():
        delta = data.get("delta_pct", 0)
        color = "#3FB950" if delta <= 0 else "#F85149" if delta > 15 else "#D29922"
        label = metric.replace("_", " ").title()
        metric_bars += f"""
        <div style="margin: 8px 0;">
            <div style="display: flex; justify-content: space-between; font-size: 13px; color: #E6EDF3;">
                <span>{label}</span>
                <span style="color: {color};">{delta:+.1f}%</span>
            </div>
            <div style="background: #30363D; border-radius: 4px; height: 8px; margin-top: 4px;">
                <div style="background: {color}; width: {min(abs(delta) * 2, 100):.0f}%; height: 8px; border-radius: 4px;"></div>
            </div>
        </div>"""

    rank_text = ""
    if rank_info:
        rank_text = f'<div style="text-align: center; margin: 16px 0; font-size: 18px; color: #388BFD;">🏆 #{rank_info.get("rank", "?")} of {rank_info.get("total", "?")} drivers</div>'

    audio_button = ""
    if audio_url:
        audio_button = f'''
        <div style="text-align: center; margin: 20px 0;">
            <a href="{audio_url}" style="display: inline-block; background: #388BFD; color: white;
               padding: 12px 32px; border-radius: 8px; text-decoration: none; font-weight: bold;">
                ▶ Listen to Your Weekly Coach
            </a>
        </div>'''

    html = f"""
    <div style="background: #0D1117; color: #E6EDF3; font-family: 'Inter', -apple-system, sans-serif; padding: 32px; max-width: 600px; margin: 0 auto;">
        <div style="background: linear-gradient(135deg, #161B22, #1C2128); border: 1px solid #30363D; border-radius: 12px; padding: 24px;">
            <div style="text-align: center; margin-bottom: 20px;">
                <span style="font-size: 28px;">🎙️</span>
                <h1 style="font-size: 22px; margin: 8px 0 4px;">Your Week {week_num} Summary</h1>
                <p style="color: #7D8590; font-size: 14px; margin: 0;">Hey {driver_name}, here's how your week looked</p>
            </div>
            {rank_text}
            <div style="margin: 20px 0;">
                <h3 style="font-size: 14px; color: #7D8590; text-transform: uppercase; letter-spacing: 1px;">This Week vs Your Normal</h3>
                {metric_bars if metric_bars else '<p style="color: #7D8590;">No comparison data available yet.</p>'}
            </div>
            {audio_button}
            <div style="border-top: 1px solid #30363D; margin-top: 24px; padding-top: 16px;">
                <p style="font-size: 12px; color: #7D8590; text-align: center; margin: 0;">
                    Generated from your actual driving data · GEOPulse
                </p>
            </div>
        </div>
    </div>"""
    return html


def run_friday_driver_feed():
    """
    Main Friday pipeline: generate script + audio + email for all drivers.
    Returns summary of what was generated.
    """
    cache = DuckDBCache(db_path="geopulse.db")
    cache.initialize()
    client = GeotabClient(db_cache=cache)
    client.authenticate()
    fleet_dna = FleetDNA(client, cache)
    llm_provider = LLMProvider(db_cache=cache)

    entities = fleet_dna.get_entities()
    rankings = fleet_dna.rank_fleet()
    rank_lookup = {r["entity_id"]: i + 1 for i, r in enumerate(
        sorted(rankings, key=lambda x: x["deviation_score"]))}

    results = []
    for entity in entities:
        try:
            weekly = fleet_dna.get_weekly_delta(entity["id"])
            exceptions = client.get_driver_exceptions(entity["id"], days_back=7) if not fleet_dna._should_use_devices() else []

            # Generate script
            script = generate_driver_script(entity["name"], weekly, exceptions, llm_provider)

            # Generate audio (skips in Ollama mode)
            audio_path = generate_driver_audio(script, entity["name"], cache)

            # Generate email HTML
            rank = rank_lookup.get(entity["id"], 0)
            email_html = generate_driver_email_html(
                entity["name"], weekly, audio_path,
                {"rank": rank, "total": len(entities)}
            )

            results.append({
                "name": entity["name"],
                "script_length": len(script) if script else 0,
                "audio": audio_path,
                "email_generated": True,
            })

            # Send email if driver email is available
            driver_email = entity.get("email")
            if driver_email:
                email_result = send_driver_email(
                    driver_email, entity["name"], email_html, audio_path
                )
                results[-1]["email_sent"] = email_result.get("success", False)

            logger.info(f"Driver feed complete for {entity['name']}")

        except Exception as e:
            logger.error(f"Driver feed failed for {entity['name']}: {e}")
            results.append({"name": entity["name"], "error": str(e)})

    cache.close()
    return results


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("🎙️ Running Driver Feed Pipeline (test mode — first 3 entities)...")

    cache = DuckDBCache(db_path="geopulse.db")
    cache.initialize()
    client = GeotabClient(db_cache=cache)
    client.authenticate()
    fleet_dna = FleetDNA(client, cache)
    llm_provider = LLMProvider(db_cache=cache)

    entities = fleet_dna.get_entities()[:3]
    for entity in entities:
        print(f"\n📻 {entity['name']}:")
        weekly = fleet_dna.get_weekly_delta(entity["id"])
        script = generate_driver_script(entity["name"], weekly, [], llm_provider)
        print(f"   Script ({len(script)} chars):")
        print(f"   {script[:200]}...")
        print(f"   Audio: {'skipped (Ollama mode)' if os.getenv('LLM_PROVIDER') == 'ollama' else 'would generate TTS'}")

    cache.close()

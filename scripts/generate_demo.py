#!/usr/bin/env python3
"""
GEOPulse Demo Asset Generator

Generates all demo assets needed for the hackathon submission:
  1. Three driver audio coaching clips (top performer, struggling, anomaly)
  2. One complete executive podcast episode
  3. One manager morning brief HTML
  4. Dashboard data snapshots for screenshots

Run from project root:
  python scripts/generate_demo.py
"""

import os
import sys
import json
import logging
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mcp.duckdb_cache import DuckDBCache
from mcp.geotab_client import GeotabClient
from mcp.fleetdna import FleetDNA
from mcp.llm_provider import LLMProvider
from frequencies.driver_feed import generate_driver_script, generate_driver_audio
from frequencies.exec_podcast import generate_podcast_script, generate_podcast_audio, gather_week_data
from frequencies.manager_email import generate_manager_brief, generate_manager_email_html

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

DEMO_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "demo_assets")


def main():
    os.makedirs(DEMO_DIR, exist_ok=True)
    print("🚀 GEOPulse Demo Asset Generator")
    print("=" * 50)

    # Initialize
    cache = DuckDBCache(db_path="geopulse.db")
    cache.initialize()
    client = GeotabClient(db_cache=cache)
    client.authenticate()
    fleet_dna = FleetDNA(client, cache)
    llm = LLMProvider(db_cache=cache)

    # Get entities and rankings
    entities = fleet_dna.get_entities()
    rankings = fleet_dna.rank_fleet()

    print(f"\n📊 Fleet: {len(entities)} entities, {len(rankings)} ranked")

    # Sort for demo scenarios
    ranked_sorted = sorted(rankings, key=lambda x: x["deviation_score"])
    top_performer = ranked_sorted[0] if ranked_sorted else None
    struggling = ranked_sorted[-1] if len(ranked_sorted) > 1 else None
    mid_range = ranked_sorted[len(ranked_sorted) // 2] if len(ranked_sorted) > 2 else None

    # ─── 1. DRIVER AUDIO CLIPS ──────────────────────────────────────
    print("\n🎙️ Generating Driver Coaching Clips...")

    demo_drivers = [
        (top_performer, "top_performer"),
        (struggling, "struggling"),
        (mid_range, "anomaly"),
    ]

    for driver_data, label in demo_drivers:
        if not driver_data:
            continue
        entity_id = driver_data["entity_id"]
        name = driver_data["name"]
        print(f"   {label}: {name} (deviation: {driver_data['deviation_score']})")

        weekly = fleet_dna.get_weekly_delta(entity_id)
        exceptions = []
        try:
            exceptions = client.get_driver_exceptions(entity_id, days_back=7)
        except Exception:
            pass

        script = generate_driver_script(name, weekly, exceptions, llm)
        if script:
            # Save script
            script_path = os.path.join(DEMO_DIR, f"driver_script_{label}.txt")
            with open(script_path, "w") as f:
                f.write(f"Driver: {name}\nLabel: {label}\n")
                f.write(f"Deviation Score: {driver_data['deviation_score']}\n")
                f.write("=" * 50 + "\n\n")
                f.write(script)
            print(f"     ✅ Script saved: {script_path}")

            # Generate audio
            audio_path = generate_driver_audio(script, f"demo_{label}", cache)
            if audio_path:
                print(f"     🔊 Audio saved: {audio_path}")
            else:
                print(f"     ⏩ Audio skipped (no TTS credentials)")

    # ─── 2. EXECUTIVE PODCAST ────────────────────────────────────────
    print("\n🎧 Generating Executive Podcast Episode...")

    week_data = gather_week_data(client, fleet_dna)
    podcast_script = generate_podcast_script(week_data, llm)

    if podcast_script:
        podcast_script_path = os.path.join(DEMO_DIR, "podcast_script.txt")
        with open(podcast_script_path, "w") as f:
            f.write(f"GEOPulse Fleet Intelligence Podcast\n")
            f.write(f"Week {week_data['week_number']}, {week_data['year']}\n")
            f.write("=" * 50 + "\n\n")
            f.write(podcast_script)
        print(f"   ✅ Podcast script saved: {podcast_script_path}")

        podcast_audio = generate_podcast_audio(podcast_script, cache)
        if podcast_audio:
            print(f"   🔊 Podcast audio saved: {podcast_audio}")
        else:
            print(f"   ⏩ Podcast audio skipped (no TTS credentials)")

    # ─── 3. MANAGER BRIEF ────────────────────────────────────────────
    print("\n📡 Generating Manager Morning Brief...")

    fleet_summary = {
        "total_vehicles": len(entities),
        "anomaly_count": len([r for r in rankings if r["deviation_score"] > 40]),
        "event_count": 0,
        "anomalies": [r for r in rankings if r["deviation_score"] > 40][:5],
    }

    try:
        events = client.get_live_events()
        fleet_summary["event_count"] = len(events.get("events", []))
    except Exception:
        pass

    fleet_data = {
        "rankings": rankings[:10],
        "events": [],
        "faults": [],
        "anomalies": fleet_summary["anomalies"],
    }

    brief = generate_manager_brief(fleet_data, llm)
    email_html = generate_manager_email_html(brief, fleet_summary)

    brief_path = os.path.join(DEMO_DIR, "manager_brief.html")
    with open(brief_path, "w") as f:
        f.write(email_html)
    print(f"   ✅ Manager brief saved: {brief_path}")

    # ─── 4. DATA SNAPSHOTS ────────────────────────────────────────────
    print("\n📸 Saving data snapshots...")

    snapshot = {
        "generated_at": datetime.now().isoformat(),
        "fleet_size": len(entities),
        "entities": entities[:10],
        "rankings": rankings[:10],
        "fleet_summary": fleet_summary,
        "week_data": week_data,
    }

    snapshot_path = os.path.join(DEMO_DIR, "data_snapshot.json")
    with open(snapshot_path, "w") as f:
        json.dump(snapshot, f, indent=2, default=str)
    print(f"   ✅ Snapshot saved: {snapshot_path}")

    # ─── SUMMARY ──────────────────────────────────────────────────────
    cache.close()

    print("\n" + "=" * 50)
    print("🎉 Demo assets generated!")
    print(f"   📁 Location: {DEMO_DIR}")
    files = os.listdir(DEMO_DIR)
    for f in sorted(files):
        size = os.path.getsize(os.path.join(DEMO_DIR, f))
        print(f"   📄 {f} ({size:,} bytes)")


if __name__ == "__main__":
    main()

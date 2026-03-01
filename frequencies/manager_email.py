"""
Frequency 2b: Manager Email — Daily Morning Brief

Every day at 6:30 AM, managers receive:
- Fleet health summary (deviation scores, anomalies, faults)
- Top 3 vehicles to watch
- Yesterday's key events with LLM-generated causal analysis
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
from mcp.email_sender import send_manager_brief as send_manager_email

logger = logging.getLogger(__name__)

MANAGER_BRIEF_PROMPT = """You are a professional fleet operations analyst writing a morning brief.
Rules:
- Lead with the single most important thing the manager needs to know TODAY
- Be specific: mention vehicle numbers, driver names, exact metrics
- Include 3 action items ordered by urgency
- Flag any vehicles needing immediate maintenance attention
- Note any drivers whose behavior has changed significantly from baseline
- Keep it under 200 words. Dense, no filler.
- Tone: confident, data-driven, respectful of their time"""


def generate_manager_brief(fleet_data, llm_provider):
    """Generate the morning brief text."""
    prompt = f"Generate a fleet manager morning brief from this data:\n{json.dumps(fleet_data, indent=2, default=str)}"

    brief = llm_provider.generate_cached(
        prompt=prompt,
        system_prompt=MANAGER_BRIEF_PROMPT,
        cache_key=f"manager_brief_{datetime.now().strftime('%Y%m%d')}",
        ttl_seconds=43200,  # 12 hr cache
        temperature=0.6,
    )
    return brief


def generate_manager_email_html(brief_text, fleet_summary):
    """Generate the manager brief HTML email."""
    today = datetime.now().strftime("%A, %B %d")

    alert_cards = ""
    anomalies = fleet_summary.get("anomalies", [])
    for a in anomalies[:3]:
        color = "#F85149" if a["deviation_score"] > 70 else "#D29922"
        alert_cards += f"""
        <div style="background: #1C2128; border-left: 3px solid {color}; padding: 12px; margin: 8px 0; border-radius: 0 6px 6px 0;">
            <strong style="color: {color};">{a['name']}</strong>
            <span style="color: #7D8590; font-size: 12px;"> — {a['anomaly_type']} · {a['deviation_score']}/100</span>
        </div>"""

    html = f"""
    <div style="background: #0D1117; color: #E6EDF3; font-family: 'Inter', -apple-system, sans-serif; padding: 32px; max-width: 600px; margin: 0 auto;">
        <div style="background: #161B22; border: 1px solid #30363D; border-radius: 12px; padding: 24px;">
            <div style="text-align: center; margin-bottom: 20px;">
                <span style="font-size: 24px;">📡</span>
                <h1 style="font-size: 20px; margin: 8px 0 4px;">Fleet Morning Brief</h1>
                <p style="color: #7D8590; font-size: 13px; margin: 0;">{today}</p>
            </div>

            <div style="display: flex; justify-content: space-around; text-align: center; margin: 20px 0; padding: 16px; background: #0D1117; border-radius: 8px;">
                <div>
                    <div style="font-size: 24px; font-weight: bold; color: #3FB950;">{fleet_summary.get('total_vehicles', 0)}</div>
                    <div style="font-size: 11px; color: #7D8590;">VEHICLES</div>
                </div>
                <div>
                    <div style="font-size: 24px; font-weight: bold; color: #F85149;">{fleet_summary.get('anomaly_count', 0)}</div>
                    <div style="font-size: 11px; color: #7D8590;">ANOMALIES</div>
                </div>
                <div>
                    <div style="font-size: 24px; font-weight: bold; color: #D29922;">{fleet_summary.get('event_count', 0)}</div>
                    <div style="font-size: 11px; color: #7D8590;">EVENTS</div>
                </div>
            </div>

            {f'<h3 style="font-size: 13px; color: #7D8590; text-transform: uppercase;">⚠️ Watch List</h3>{alert_cards}' if alert_cards else ''}

            <div style="margin: 20px 0; padding: 16px; background: #0D1117; border-radius: 8px; font-size: 14px; line-height: 1.6;">
                {brief_text.replace(chr(10), '<br>')}
            </div>

            <div style="border-top: 1px solid #30363D; margin-top: 20px; padding-top: 12px;">
                <p style="font-size: 11px; color: #7D8590; text-align: center; margin: 0;">
                    GEOPulse Fleet Intelligence · Auto-generated daily
                </p>
            </div>
        </div>
    </div>"""
    return html


def run_manager_brief():
    """Main daily pipeline: gather fleet state → LLM brief → email."""
    cache = DuckDBCache(db_path="geopulse.db")
    cache.initialize()
    client = GeotabClient(db_cache=cache)
    client.authenticate()
    fleet_dna = FleetDNA(client, cache)
    llm_provider = LLMProvider(db_cache=cache)

    # Gather data
    rankings = fleet_dna.rank_fleet()
    events = client.get_live_events()
    faults = client.get_active_faults()

    anomalies = [r for r in rankings if r["deviation_score"] > 40]

    fleet_summary = {
        "total_vehicles": len(fleet_dna.get_entities()),
        "anomaly_count": len(anomalies),
        "event_count": len(events.get("events", [])),
        "anomalies": anomalies[:5],
        "top_rankings": rankings[:5],
        "active_faults": len(faults),
    }

    fleet_data = {
        "rankings": rankings[:10],
        "events": events.get("events", [])[:10],
        "faults": faults[:5],
        "anomalies": anomalies,
    }

    brief = generate_manager_brief(fleet_data, llm_provider)
    email_html = generate_manager_email_html(brief, fleet_summary)

    # Send email if configured
    manager_email = os.getenv("MANAGER_EMAIL")
    email_sent = False
    if manager_email:
        result = send_manager_email(manager_email, email_html)
        email_sent = result.get("success", False)

    cache.close()
    return {"brief": brief, "email_html": email_html, "summary": fleet_summary, "email_sent": email_sent}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("📡 Running Manager Brief Pipeline (test mode)...")

    result = run_manager_brief()
    print(f"\n📋 Fleet Summary:")
    print(f"   Vehicles: {result['summary']['total_vehicles']}")
    print(f"   Anomalies: {result['summary']['anomaly_count']}")
    print(f"   Events: {result['summary']['event_count']}")
    print(f"\n📝 Brief ({len(result['brief'])} chars):")
    print(f"   {result['brief'][:300]}...")

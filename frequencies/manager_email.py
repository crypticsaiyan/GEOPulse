"""
Frequency 2b: Manager Email — Daily Morning Brief

Every day at 6:30 AM, managers receive:
- Fleet health summary (deviation scores, anomalies)
- Top 3 vehicles to watch
- Yesterday's key events with LLM-generated causal analysis
"""

import os
import sys
import json
import logging
import html as _html
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

    anomalies = fleet_summary.get("anomalies", [])
    top_rankings = fleet_summary.get("top_rankings", [])

    critical_count = sum(1 for a in anomalies if a.get("deviation_score", 0) >= 70)
    moderate_count = sum(1 for a in anomalies if 40 <= a.get("deviation_score", 0) < 70)

    safe_brief = _html.escape((brief_text or "").strip()).replace("\n", "<br>")

    alert_cards = ""
    for index, anomaly in enumerate(anomalies[:5], 1):
        score = anomaly.get("deviation_score", 0)
        level = "Critical" if score >= 70 else "Moderate"
        color = "#F85149" if score >= 70 else "#D29922"
        name = _html.escape(str(anomaly.get("name", "Unknown Vehicle")))
        anomaly_type = _html.escape(str(anomaly.get("anomaly_type", "behavior"))).replace("_", " ").title()
        alert_cards += f"""
        <tr>
            <td style="padding: 10px 8px; border-bottom: 1px solid #2D333B; color: #E6EDF3; font-size: 13px;">{index}. {name}</td>
            <td style="padding: 10px 8px; border-bottom: 1px solid #2D333B; color: #7D8590; font-size: 12px;">{anomaly_type}</td>
            <td style="padding: 10px 8px; border-bottom: 1px solid #2D333B; color: {color}; font-weight: 700; font-size: 12px;">{score}/100</td>
            <td style="padding: 10px 8px; border-bottom: 1px solid #2D333B; color: {color}; font-size: 12px;">{level}</td>
        </tr>"""

    ranking_cards = ""
    for rank_index, ranked in enumerate(top_rankings[:3], 1):
        score = ranked.get("deviation_score", 0)
        color = "#F85149" if score >= 70 else "#D29922" if score >= 50 else "#3FB950"
        name = _html.escape(str(ranked.get("name", "Unknown Vehicle")))
        anomaly_type = _html.escape(str(ranked.get("anomaly_type", "normal")).replace("_", " ").title())
        ranking_cards += f"""
        <div style="background: #11161C; border: 1px solid #30363D; border-radius: 10px; padding: 12px; margin: 8px 0;">
            <div style="display: flex; justify-content: space-between; align-items: center;">
                <div style="font-size: 13px; color: #E6EDF3;"><strong>#{rank_index}</strong> {name}</div>
                <div style="font-size: 12px; color: {color}; font-weight: 700;">{score}/100</div>
            </div>
            <div style="font-size: 11px; color: #7D8590; margin-top: 6px;">Primary signal: {anomaly_type}</div>
        </div>"""

    if critical_count > 0:
        focus_text = f"Prioritize {critical_count} critical vehicles first. Trigger coaching + maintenance checks today."
    elif moderate_count > 0:
        focus_text = f"No critical units. Focus on {moderate_count} moderate-risk vehicles to prevent escalation."
    else:
        focus_text = "Fleet is stable. Focus on preventive coaching and monitor live events for change." 

    html = f"""
    <div style="background: #0D1117; color: #E6EDF3; font-family: 'Inter', -apple-system, sans-serif; padding: 28px; max-width: 680px; margin: 0 auto;">
        <div style="background: linear-gradient(180deg, #161B22 0%, #121820 100%); border: 1px solid #30363D; border-radius: 14px; padding: 24px; box-shadow: 0 12px 30px rgba(0, 0, 0, 0.35);">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px;">
                <div>
                    <div style="font-size: 11px; color: #7D8590; text-transform: uppercase; letter-spacing: 1px;">GEOPulse Daily Digest</div>
                    <h1 style="font-size: 22px; margin: 6px 0 0;">Fleet Morning Brief</h1>
                </div>
                <div style="font-size: 12px; color: #7D8590;">{today}</div>
            </div>

            <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; margin: 18px 0;">
                <div style="text-align: center; padding: 12px; background: #0D1117; border: 1px solid #2D333B; border-radius: 10px;">
                    <div style="font-size: 24px; font-weight: bold; color: #3FB950;">{fleet_summary.get('total_vehicles', 0)}</div>
                    <div style="font-size: 11px; color: #7D8590;">ACTIVE VEHICLES</div>
                </div>
                <div style="text-align: center; padding: 12px; background: #0D1117; border: 1px solid #2D333B; border-radius: 10px;">
                    <div style="font-size: 24px; font-weight: bold; color: #F85149;">{fleet_summary.get('anomaly_count', 0)}</div>
                    <div style="font-size: 11px; color: #7D8590;">ANOMALIES</div>
                </div>
                <div style="text-align: center; padding: 12px; background: #0D1117; border: 1px solid #2D333B; border-radius: 10px;">
                    <div style="font-size: 24px; font-weight: bold; color: #D29922;">{fleet_summary.get('event_count', 0)}</div>
                    <div style="font-size: 11px; color: #7D8590;">LIVE EVENTS</div>
                </div>
            </div>

            <div style="margin: 18px 0; padding: 14px; background: #0D1117; border: 1px solid #2D333B; border-radius: 10px;">
                <div style="font-size: 12px; color: #7D8590; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 6px;">Priority Focus (Next 24h)</div>
                <div style="font-size: 14px; line-height: 1.5; color: #E6EDF3;">{_html.escape(focus_text)}</div>
            </div>

            {f'''
            <div style="margin: 20px 0;">
                <h3 style="font-size: 13px; color: #7D8590; text-transform: uppercase; letter-spacing: 1px; margin: 0 0 8px;">⚠️ Watch List</h3>
                <div style="background: #0D1117; border: 1px solid #2D333B; border-radius: 10px; overflow: hidden;">
                    <table width="100%" cellspacing="0" cellpadding="0" style="border-collapse: collapse;">
                        <thead>
                            <tr style="background: #11161C;">
                                <th align="left" style="padding: 10px 8px; color: #7D8590; font-size: 11px; text-transform: uppercase;">Vehicle</th>
                                <th align="left" style="padding: 10px 8px; color: #7D8590; font-size: 11px; text-transform: uppercase;">Signal</th>
                                <th align="left" style="padding: 10px 8px; color: #7D8590; font-size: 11px; text-transform: uppercase;">Score</th>
                                <th align="left" style="padding: 10px 8px; color: #7D8590; font-size: 11px; text-transform: uppercase;">Risk</th>
                            </tr>
                        </thead>
                        <tbody>
                            {alert_cards}
                        </tbody>
                    </table>
                </div>
            </div>
            ''' if alert_cards else ''}

            {f'''
            <div style="margin: 20px 0;">
                <h3 style="font-size: 13px; color: #7D8590; text-transform: uppercase; letter-spacing: 1px; margin: 0 0 8px;">📈 Top Vehicles to Review</h3>
                {ranking_cards}
            </div>
            ''' if ranking_cards else ''}

            <div style="margin: 20px 0; padding: 16px; background: #0D1117; border: 1px solid #2D333B; border-radius: 10px; font-size: 14px; line-height: 1.65;">
                <div style="font-size: 12px; color: #7D8590; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 8px;">Manager Narrative</div>
                {safe_brief}
            </div>

            <div style="border-top: 1px solid #30363D; margin-top: 20px; padding-top: 12px; display: flex; justify-content: space-between; align-items: center; gap: 8px; flex-wrap: wrap;">
                <p style="font-size: 11px; color: #7D8590; margin: 0;">
                    GEOPulse Fleet Intelligence · Auto-generated daily at 06:30
                </p>
                <p style="font-size: 11px; color: #7D8590; margin: 0;">
                    Critical: <span style="color:#F85149;">{critical_count}</span> · Moderate: <span style="color:#D29922;">{moderate_count}</span>
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

    anomalies = [r for r in rankings if r["deviation_score"] > 40]

    fleet_summary = {
        "total_vehicles": len(fleet_dna.get_entities()),
        "anomaly_count": len(anomalies),
        "event_count": len(events.get("events", [])),
        "anomalies": anomalies[:5],
        "top_rankings": rankings[:5],
    }

    fleet_data = {
        "rankings": rankings[:10],
        "events": events.get("events", [])[:10],
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

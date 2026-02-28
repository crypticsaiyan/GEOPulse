"""
GEOPulse Scheduler — Automated Job Scheduling

Runs all frequency pipelines on their schedules:
- Every 60s: refresh live data cache
- Daily 6:30 AM: manager morning brief
- Friday 5 PM: driver feed (audio + email)
- Monday 5 AM: executive podcast

Run: python -m scheduler.cron_jobs
"""

import os
import sys
import logging
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_EXECUTED

from mcp.duckdb_cache import DuckDBCache
from mcp.geotab_client import GeotabClient
from mcp.fleetdna import FleetDNA

logger = logging.getLogger(__name__)


def refresh_live_data():
    """Refresh live vehicle positions and events in DuckDB cache."""
    try:
        cache = DuckDBCache(db_path="geopulse.db")
        cache.initialize()
        client = GeotabClient(db_cache=cache)
        client.authenticate()

        positions = client.get_live_positions()
        events = client.get_live_events()

        logger.debug(f"Live refresh: {len(positions)} positions, {len(events.get('events', []))} events")
        cache.close()
    except Exception as e:
        logger.error(f"Live refresh failed: {e}")


def run_daily_manager_brief():
    """6:30 AM daily — Manager morning brief."""
    try:
        from frequencies.manager_email import run_manager_brief
        result = run_manager_brief()
        logger.info(f"Manager brief generated: {len(result.get('brief', ''))} chars")
    except Exception as e:
        logger.error(f"Manager brief failed: {e}")


def run_friday_driver_feed():
    """Friday 5 PM — Personal driver audio + email."""
    try:
        from frequencies.driver_feed import run_friday_driver_feed as feed
        results = feed()
        success = sum(1 for r in results if "error" not in r)
        logger.info(f"Driver feed: {success}/{len(results)} drivers processed")
    except Exception as e:
        logger.error(f"Driver feed failed: {e}")


def run_monday_podcast():
    """Monday 5 AM — Executive two-host podcast."""
    try:
        from frequencies.exec_podcast import run_monday_podcast as podcast
        result = podcast()
        logger.info(f"Podcast generated: {len(result.get('script', ''))} chars")
    except Exception as e:
        logger.error(f"Podcast failed: {e}")


def job_listener(event):
    """Log job execution results."""
    if event.exception:
        logger.error(f"Job {event.job_id} failed: {event.exception}")
    else:
        logger.debug(f"Job {event.job_id} completed successfully")


def create_scheduler():
    """Create and configure the scheduler with all jobs."""
    scheduler = BlockingScheduler()

    # Live data refresh — every 60 seconds
    scheduler.add_job(
        func=refresh_live_data,
        trigger="interval",
        seconds=60,
        id="live_refresh",
        name="Live Data Refresh",
    )

    # Manager morning brief — daily at 6:30 AM
    scheduler.add_job(
        func=run_daily_manager_brief,
        trigger="cron",
        hour=6, minute=30,
        id="manager_brief",
        name="Manager Morning Brief",
    )

    # Driver feed — Friday at 5 PM
    scheduler.add_job(
        func=run_friday_driver_feed,
        trigger="cron",
        day_of_week="fri",
        hour=17, minute=0,
        id="driver_feed",
        name="Friday Driver Feed",
    )

    # Executive podcast — Monday at 5 AM
    scheduler.add_job(
        func=run_monday_podcast,
        trigger="cron",
        day_of_week="mon",
        hour=5, minute=0,
        id="exec_podcast",
        name="Monday Executive Podcast",
    )

    scheduler.add_listener(job_listener, EVENT_JOB_ERROR | EVENT_JOB_EXECUTED)
    return scheduler


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    print("⏰ GEOPulse Scheduler")
    print("=" * 40)
    print("   📡 Live refresh:    every 60s")
    print("   📋 Manager brief:   daily 6:30 AM")
    print("   🎙️ Driver feed:     Friday 5:00 PM")
    print("   🎧 Exec podcast:    Monday 5:00 AM")
    print("=" * 40)
    print(f"   Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("   Press Ctrl+C to stop\n")

    scheduler = create_scheduler()
    try:
        scheduler.start()
    except KeyboardInterrupt:
        print("\n⏹️ Scheduler stopped.")

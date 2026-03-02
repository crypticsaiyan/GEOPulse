"""
GEOPulse Write-Back Manager

Centralizes all Geotab write-back operations triggered by frequency pipelines.
Creates Groups and Rules in Geotab based on AI analysis results.

Methods:
    after_morning_analysis() → Groups for welfare checks
    after_driver_feed()     → Top performer + welfare check groups + coaching rules
    after_exec_podcast()    → Archive old groups, create fresh ones
    on_welfare_flag()       → Immediate welfare check group
"""

import logging
from datetime import datetime, date

logger = logging.getLogger(__name__)


class WritebackManager:
    """Manages all write-back operations to Geotab."""

    def __init__(self, geotab_client, db_cache=None):
        self.geotab = geotab_client
        self.cache = db_cache

    def after_morning_analysis(self, analysis_results):
        """
        Called after daily Gemini causality analysis.
        Creates groups for high deviation drivers and welfare checks.
        """
        actions = []
        today = date.today().isoformat()

        # High deviation drivers
        anomalies = analysis_results.get("high_deviation", [])
        high_dev = [a for a in anomalies if a.get("deviation_score", 0) > 80]
        if high_dev:
            vehicle_ids = [a.get("entity_id", "") for a in high_dev]
            try:
                group_id = self.geotab.create_group(
                    f"Welfare Check {today}", vehicle_ids
                )
                actions.append({"type": "group", "name": f"Welfare Check {today}", "id": group_id, "vehicles": len(vehicle_ids)})
            except Exception as e:
                logger.error(f"Failed to create welfare group: {e}")

        logger.info(f"Morning write-back: {len(actions)} actions")
        return actions

    def after_driver_feed(self, weekly_rankings):
        """
        Called after Friday driver processing.
        Creates champion and welfare check groups + coaching rules.
        """
        actions = []
        week_num = datetime.now().strftime("%W")

        # Top 5 performers
        if len(weekly_rankings) >= 5:
            top_ids = [r["entity_id"] for r in weekly_rankings[:5]]
            try:
                group_id = self.geotab.create_group(
                    f"Week {week_num} Champions", top_ids
                )
                actions.append({"type": "group", "name": f"Week {week_num} Champions", "id": group_id})
            except Exception as e:
                logger.error(f"Failed to create champions group: {e}")

        # Welfare check for high deviation
        welfare = [r for r in weekly_rankings if r.get("deviation_score", 0) > 70]
        if welfare:
            welfare_ids = [r["entity_id"] for r in welfare]
            try:
                group_id = self.geotab.create_group(
                    f"Welfare Check Week {week_num}", welfare_ids
                )
                actions.append({"type": "group", "name": f"Welfare Check Week {week_num}", "id": group_id})
            except Exception as e:
                logger.error(f"Failed to create welfare group: {e}")

        # Coaching rules for bottom performers
        bottom = weekly_rankings[-3:] if len(weekly_rankings) > 3 else []
        for r in bottom:
            try:
                rule_id = self.geotab.create_rule(
                    f"Coaching Triggered — {r.get('name', r['entity_id'])}",
                    rule_type="harsh_braking",
                    driver_id=r["entity_id"],
                )
                if rule_id:
                    actions.append({"type": "rule", "name": f"Coaching for {r.get('name', '')}", "id": rule_id})
            except Exception as e:
                logger.error(f"Failed to create coaching rule: {e}")

        logger.info(f"Driver feed write-back: {len(actions)} actions")
        return actions

    def after_exec_podcast(self, week_summary):
        """
        Called after Monday podcast generation.
        Archives last week's groups and creates fresh ones.
        """
        actions = []
        logger.info("Exec podcast write-back: archiving would happen here")
        # Note: Geotab Group rename requires Get → modify → Set pattern
        # In a production system, we'd rename old groups with [ARCHIVED] prefix
        return actions

    def on_welfare_flag(self, entity_id, entity_name, reason):
        """
        Immediate write-back when sportscaster or FleetDNA flags someone.
        Creates a welfare check group instantly.
        """
        today = date.today().isoformat()
        try:
            group_id = self.geotab.create_group(
                f"Welfare Check {today} — {entity_name}",
                [entity_id],
            )
            logger.info(f"Welfare flag: created group for {entity_name} (reason: {reason})")

            # Log in DuckDB
            if self.cache:
                self.cache.store_anomaly(entity_id, today, 100, "welfare_flag",
                                         {"reason": reason, "group_id": group_id})

            return {"success": True, "group_id": group_id}
        except Exception as e:
            logger.error(f"Welfare flag write-back failed: {e}")
            return {"success": False, "error": str(e)}

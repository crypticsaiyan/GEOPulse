"""
FleetDNA — Behavioral Fingerprinting Engine

Builds statistical baselines per driver and detects anomalies by
comparing today's behavior to their personal 90-day normal.

Classes:
    FleetDNA:
        build_baseline(driver_id) -> BaselineProfile
        score_today(driver_id, today_data) -> deviation dict
        rank_fleet(date) -> ranked driver list
        get_weekly_delta(driver_id) -> weekly comparison dict
"""

# TODO: Implement FleetDNA class - Step 3
# Reference: PLAN.md Step 3 for full spec

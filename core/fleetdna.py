"""
FleetDNA — Behavioral Fingerprinting Engine

Builds statistical baselines per driver (or per-vehicle in demo DBs)
and detects anomalies by comparing today's behavior to their personal
90-day normal using Z-score deviation scoring.

In demo databases, drivers are often "UnknownDriverId", so FleetDNA
falls back to per-device analysis.

Classes:
    FleetDNA:
        build_baseline(entity_id) -> BaselineProfile dict
        score_today(entity_id) -> deviation dict (0-100)
        rank_fleet(date) -> ranked list by deviation score
        get_weekly_delta(entity_id) -> weekly comparison dict
"""

import statistics
import logging
from datetime import datetime, timedelta, timezone, date
from collections import defaultdict

logger = logging.getLogger(__name__)

# Metrics used for fingerprinting
METRICS = [
    "avg_speed",        # Average speed per trip (km/h)
    "max_speed",        # Max speed per trip (km/h)
    "trip_distance",    # Distance per trip (km)
    "trip_duration",    # Duration per trip (seconds)
    "idle_ratio",       # Idle time / total trip time
    "daily_distance",   # Total daily distance (km)
    "daily_trips",      # Number of trips per day
]

# Weights for composite deviation score
METRIC_WEIGHTS = {
    "avg_speed": 1.5,
    "max_speed": 2.0,
    "trip_distance": 1.0,
    "trip_duration": 0.8,
    "idle_ratio": 1.2,
    "daily_distance": 1.0,
    "daily_trips": 0.5,
}


class FleetDNA:
    """Behavioral fingerprinting engine for fleet anomaly detection."""

    def __init__(self, geotab_client, db_cache):
        """
        Args:
            geotab_client: GeotabClient instance for data fetching
            db_cache: DuckDBCache instance for storing baselines
        """
        self.geotab = geotab_client
        self.cache = db_cache
        self._use_devices = None  # True if demo DB (no real drivers)

    def _should_use_devices(self):
        """Check if we should use per-device analysis (demo DB fallback)."""
        if self._use_devices is None:
            drivers = self.geotab.get_all_drivers()
            real_drivers = [d for d in drivers if d.get("isDriver")]
            self._use_devices = len(real_drivers) == 0
            if self._use_devices:
                logger.info("Demo DB detected: using per-device analysis instead of per-driver")
        return self._use_devices

    def get_entities(self):
        """Get the list of entities to analyze (drivers or devices)."""
        if self._should_use_devices():
            devices = self.geotab.get_all_devices()
            return [{"id": d["id"], "name": d["name"], "type": "device"} for d in devices]
        else:
            drivers = self.geotab.get_all_drivers()
            return [
                {
                    "id": d["id"],
                    "name": f"{d.get('firstName', '')} {d.get('lastName', '')}".strip() or d.get("name", ""),
                    "type": "driver",
                }
                for d in drivers if d.get("isDriver")
            ]

    def _get_trips_for_entity(self, entity_id, days_back=90):
        """Get trips for an entity. Uses device-based query for demo DBs."""
        if self._should_use_devices():
            # Per-device: get all trips and filter by device
            now = datetime.now(timezone.utc)
            from_date = (now - timedelta(days=days_back)).isoformat()
            params = {
                "typeName": "Trip",
                "search": {
                    "deviceSearch": {"id": entity_id},
                    "fromDate": from_date,
                    "toDate": now.isoformat(),
                },
            }
            raw_trips = self.geotab._cached_call(
                f"device_trips_{entity_id}_{days_back}", 3600, "Get", params
            )
            # Parse durations
            formatted = []
            for t in (raw_trips or []):
                device_ref = t.get("device", {})
                device_id = device_ref.get("id", "") if isinstance(device_ref, dict) else str(device_ref)
                start = t.get("dateTime", t.get("start", ""))
                formatted.append({
                    "trip_id": t.get("id", ""),
                    "device_id": device_id,
                    "driver_id": entity_id,
                    "start_time": str(start),
                    "distance": t.get("distance", 0),
                    "max_speed": t.get("maximumSpeed", 0),
                    "average_speed": t.get("averageSpeed", 0),
                    "duration_seconds": self.geotab._parse_duration(t.get("drivingDuration", 0)),
                    "idle_duration_seconds": self.geotab._parse_duration(t.get("idlingDuration", 0)),
                    "trip_date": str(start)[:10] if start else "",
                })
            return formatted
        else:
            return self.geotab.get_driver_trips(entity_id, days_back)

    def _compute_stats_from_trips(self, trips):
        """Compute baseline statistics from a list of trips (no caching)."""
        if not trips:
            return {}

        trip_metrics = defaultdict(list)
        daily_data = defaultdict(lambda: {"distance": 0, "trips": 0})

        for t in trips:
            distance = t.get("distance", 0)
            duration = t.get("duration_seconds", 0)
            idle = t.get("idle_duration_seconds", 0)
            avg_speed = t.get("average_speed", 0)
            max_speed = t.get("max_speed", 0)
            trip_date = t.get("trip_date", "")

            if distance > 0:
                trip_metrics["avg_speed"].append(avg_speed)
                trip_metrics["max_speed"].append(max_speed)
                trip_metrics["trip_distance"].append(distance)
                trip_metrics["trip_duration"].append(duration)
                trip_metrics["idle_ratio"].append(idle / max(duration, 1))

            if trip_date:
                daily_data[trip_date]["distance"] += distance
                daily_data[trip_date]["trips"] += 1

        for day, data in daily_data.items():
            trip_metrics["daily_distance"].append(data["distance"])
            trip_metrics["daily_trips"].append(data["trips"])

        baseline = {}
        for metric, values in trip_metrics.items():
            if len(values) < 2:
                continue

            mean = statistics.mean(values)
            std_dev = statistics.stdev(values) if len(values) > 1 else 0.01
            sorted_vals = sorted(values)
            p95_idx = int(len(sorted_vals) * 0.95)
            p95 = sorted_vals[min(p95_idx, len(sorted_vals) - 1)]

            baseline[metric] = {
                "mean": round(mean, 4),
                "std_dev": round(max(std_dev, 0.01), 4),
                "p95": round(p95, 4),
                "samples": len(values),
            }

        return baseline

    def build_baseline(self, entity_id):
        """
        Build a 90-day statistical baseline for an entity.

        Returns: dict of {metric: {mean, std_dev, p95, samples}}
        """
        trips = self._get_trips_for_entity(entity_id, days_back=90)

        if not trips:
            logger.warning(f"No trips found for {entity_id}")
            return {}

        baseline = self._compute_stats_from_trips(trips)

        # Store in DuckDB
        for metric, stats in baseline.items():
            self.cache.store_baseline(
                entity_id, metric,
                stats["mean"], stats["std_dev"], stats["p95"], stats["samples"]
            )

        logger.info(f"Built baseline for {entity_id}: {len(baseline)} metrics, {len(trips)} trips")
        return baseline

    def score_today(self, entity_id, today_date=None):
        """
        Compare recent behavior to the entity's personal baseline.

        Key: we EXCLUDE the scoring day(s) from the baseline so
        z-scores reflect real deviation instead of comparing a day
        against the average that includes itself (which yields ~0).

        Returns: {
            deviation_score: 0-100 (0=normal, 100=completely anomalous),
            anomaly_type: main anomaly category,
            confidence: 0-100,
            details: {metric: {today, baseline_mean, z_score}},
        }
        """
        if today_date is None:
            today_date = date.today()

        # Get all trips in the 90-day window
        trips = self._get_trips_for_entity(entity_id, days_back=90)
        if not trips:
            return {"deviation_score": 0, "anomaly_type": "no_data", "confidence": 0, "details": {}}

        today_str = str(today_date)
        today_trips = [t for t in trips if t.get("trip_date", "") == today_str]
        scoring_date = today_str

        # If no trips today, fall back to the most recent active day
        if not today_trips:
            all_dates = sorted(set(
                t.get("trip_date", "") for t in trips if t.get("trip_date", "")
            ))
            if all_dates:
                scoring_date = all_dates[-1]
                today_trips = [t for t in trips if t.get("trip_date", "") == scoring_date]
                logger.info(f"No trips for {today_date} on {entity_id}, using recent: {scoring_date}")

        if not today_trips:
            return {"deviation_score": 0, "anomaly_type": "no_data", "confidence": 0, "details": {}}

        # --- Build baseline EXCLUDING the scoring day ---
        baseline_trips = [t for t in trips if t.get("trip_date", "") != scoring_date]
        if len(baseline_trips) < 3:
            # Not enough history without scoring day — use all but add noise floor
            baseline_trips = trips

        baseline = self._compute_stats_from_trips(baseline_trips)
        if not baseline:
            # Fallback: try the full stored baseline
            baseline = self.cache.get_baseline(entity_id)
            if not baseline:
                baseline = self.build_baseline(entity_id)
        if not baseline:
            return {"deviation_score": 0, "anomaly_type": "none", "confidence": 0, "details": {}}

        # --- Compute today's metrics ---
        today_metrics = {}
        speeds = [t.get("average_speed", 0) for t in today_trips if t.get("average_speed", 0) > 0]
        max_speeds = [t.get("max_speed", 0) for t in today_trips if t.get("max_speed", 0) > 0]
        distances = [t.get("distance", 0) for t in today_trips if t.get("distance", 0) > 0]
        durations = [t.get("duration_seconds", 0) for t in today_trips]
        idles = [t.get("idle_duration_seconds", 0) for t in today_trips]

        if speeds:
            today_metrics["avg_speed"] = statistics.mean(speeds)
        if max_speeds:
            today_metrics["max_speed"] = max(max_speeds)
        if distances:
            today_metrics["trip_distance"] = statistics.mean(distances)
            today_metrics["daily_distance"] = sum(distances)
        if durations:
            today_metrics["trip_duration"] = statistics.mean(durations)
        if durations and idles:
            total_dur = sum(durations)
            total_idle = sum(idles)
            today_metrics["idle_ratio"] = total_idle / max(total_dur, 1)
        today_metrics["daily_trips"] = len(today_trips)

        # --- Compute Z-scores ---
        details = {}
        z_scores = {}
        for metric, today_val in today_metrics.items():
            if metric not in baseline:
                continue
            bl = baseline[metric]
            z = (today_val - bl["mean"]) / max(bl["std_dev"], 0.01)
            z_scores[metric] = abs(z)
            details[metric] = {
                "today": round(today_val, 2),
                "baseline_mean": round(bl["mean"], 2),
                "baseline_std": round(bl["std_dev"], 2),
                "z_score": round(z, 2),
            }

        if not z_scores:
            return {"deviation_score": 0, "anomaly_type": "no_data", "confidence": 0, "details": {}}

        # Weighted composite score → 0-100 scale
        weighted_sum = sum(
            abs_z * METRIC_WEIGHTS.get(m, 1.0) for m, abs_z in z_scores.items()
        )
        total_weight = sum(METRIC_WEIGHTS.get(m, 1.0) for m in z_scores.keys())
        weighted_avg = weighted_sum / max(total_weight, 1)

        # A vehicle with ONE extreme metric IS anomalous — don't let the
        # average of 7 metrics dilute a genuine outlier.  Blend the weighted
        # average with the single-worst z-score so spikes show through.
        max_z = max(z_scores.values())
        raw_score = 0.5 * weighted_avg + 0.5 * max_z

        # Sigmoid-like mapping with moderate sensitivity:
        #   z≈0.3 → ~20 (green)   z≈1 → ~44 (yellow)
        #   z≈2   → ~62 (yellow)  z≈3 → ~71 (red)
        deviation_score = min(100, int(100 * (1 - 1 / (1 + raw_score * 0.8))))

        # Find the most anomalous metric
        anomaly_metric = max(z_scores, key=z_scores.get) if z_scores else "none"
        anomaly_type_map = {
            "avg_speed": "speed", "max_speed": "speed",
            "trip_distance": "route", "daily_distance": "route",
            "trip_duration": "time", "daily_trips": "time",
            "idle_ratio": "idle",
        }
        anomaly_type = anomaly_type_map.get(anomaly_metric, "multi")

        # Confidence based on sample size
        min_samples = min(
            (baseline.get(m, {}).get("samples", 0) for m in z_scores), default=0
        )
        confidence = min(100, int(min_samples / 30 * 100))

        result = {
            "deviation_score": deviation_score,
            "anomaly_type": anomaly_type,
            "confidence": confidence,
            "details": details,
        }

        # Log anomaly
        self.cache.store_anomaly(
            entity_id, today_date, deviation_score, anomaly_type, details
        )

        return result

    def rank_fleet(self, target_date=None):
        """
        Score all entities for a given day.
        Returns: ranked list sorted by deviation_score descending.
        """
        if target_date is None:
            target_date = date.today()

        # Check cache first — but skip cached results where all scores are 0
        # (they may have been stored before baselines were ready)
        cached = self.cache.get_rankings(target_date)
        if cached and any(r.get("deviation_score", 0) > 0 for r in cached):
            scores = [r.get("deviation_score", 0) for r in cached]
            if len(set(scores)) > 2:
                return cached
            logger.info("rank_fleet: cached rankings have low variation, recomputing")
        elif cached:
            logger.info("rank_fleet: cached rankings are all 0, recomputing with fresh baselines")

        entities = self.get_entities()
        rankings = []

        for entity in entities:
            try:
                score_result = self.score_today(entity["id"], target_date)
                rankings.append({
                    "entity_id": entity["id"],
                    "name": entity["name"],
                    "type": entity["type"],
                    "deviation_score": score_result["deviation_score"],
                    "anomaly_type": score_result["anomaly_type"],
                    "confidence": score_result["confidence"],
                })
            except Exception as e:
                logger.warning(f"Failed to score {entity['name']}: {e}")

        # Sort by deviation_score descending (most anomalous first)
        rankings.sort(key=lambda x: x["deviation_score"], reverse=True)

        # --- Fleet-relative normalization ---
        # When all scores compress into a narrow band (common in demo/synthetic
        # databases where vehicles behave very similarly), stretch them into a
        # visually useful range so the dashboard shows green/yellow/red variety.
        # This has NO effect when real anomalies create natural spread (>25pt).
        nonzero = [r["deviation_score"] for r in rankings if r["deviation_score"] > 0]
        if len(nonzero) > 5:
            mn, mx = min(nonzero), max(nonzero)
            spread = mx - mn
            if spread < 25:
                logger.info(
                    f"rank_fleet: scores compressed ({mn}-{mx}, spread={spread}), "
                    "applying fleet-relative normalization"
                )
                for r in rankings:
                    if r["deviation_score"] > 0 and spread > 0:
                        pct = (r["deviation_score"] - mn) / spread  # 0.0 → 1.0
                        # Map: bottom of fleet → 15, top → 75
                        r["deviation_score"] = int(15 + pct * 60)
                    elif r["deviation_score"] > 0:
                        r["deviation_score"] = 35  # all identical → fleet midpoint
                # Re-sort after remapping
                rankings.sort(key=lambda x: x["deviation_score"], reverse=True)

        # Only cache if we have meaningful scores — skip caching all-zero results
        # so they get recomputed on the next call (baselines may not have been ready)
        has_real_scores = any(r["deviation_score"] > 0 for r in rankings)
        if has_real_scores:
            self.cache.store_rankings(target_date, rankings)
        else:
            logger.info("rank_fleet: all scores are 0 — skipping cache so baselines can be built")

        return rankings

    def get_weekly_delta(self, entity_id):
        """
        Compare this week vs the entity's historical baseline.

        Returns: {
            best_day, worst_day, week_vs_baseline,
            fleet_rank, improvement_areas, positive_highlights
        }
        """
        baseline = self.cache.get_baseline(entity_id)
        if not baseline:
            baseline = self.build_baseline(entity_id)

        # Get this week's trips
        trips = self._get_trips_for_entity(entity_id, days_back=7)

        # Group by day
        daily_scores = {}
        daily_data = defaultdict(lambda: {"trips": [], "distance": 0})

        for t in trips:
            day = t.get("trip_date", "")
            if day:
                daily_data[day]["trips"].append(t)
                daily_data[day]["distance"] += t.get("distance", 0)

        for day, data in daily_data.items():
            day_trips = data["trips"]
            if not day_trips:
                continue
            # Simple daily score: average deviation of key metrics
            scores = []
            for t in day_trips:
                if "avg_speed" in baseline and t.get("average_speed", 0) > 0:
                    z = abs(t["average_speed"] - baseline["avg_speed"]["mean"]) / max(baseline["avg_speed"]["std_dev"], 0.01)
                    scores.append(z)
            daily_scores[day] = statistics.mean(scores) if scores else 0

        # Find best and worst days
        best_day = min(daily_scores, key=daily_scores.get) if daily_scores else None
        worst_day = max(daily_scores, key=daily_scores.get) if daily_scores else None

        # Week vs baseline comparison
        week_comparison = {}
        if trips:
            week_speeds = [t.get("average_speed", 0) for t in trips if t.get("average_speed", 0) > 0]
            week_distances = [t.get("distance", 0) for t in trips if t.get("distance", 0) > 0]

            if week_speeds and "avg_speed" in baseline:
                week_avg = statistics.mean(week_speeds)
                bl_avg = baseline["avg_speed"]["mean"]
                week_comparison["avg_speed"] = {
                    "this_week": round(week_avg, 1),
                    "baseline": round(bl_avg, 1),
                    "delta_pct": round((week_avg - bl_avg) / max(bl_avg, 0.01) * 100, 1),
                }
            if week_distances and "trip_distance" in baseline:
                week_avg = statistics.mean(week_distances)
                bl_avg = baseline["trip_distance"]["mean"]
                week_comparison["trip_distance"] = {
                    "this_week": round(week_avg, 1),
                    "baseline": round(bl_avg, 1),
                    "delta_pct": round((week_avg - bl_avg) / max(bl_avg, 0.01) * 100, 1),
                }

        # Identify improvements and highlights
        improvements = []
        highlights = []
        for metric, comp in week_comparison.items():
            if comp["delta_pct"] > 10:
                improvements.append(f"{metric}: {comp['delta_pct']:+.1f}% above baseline")
            elif comp["delta_pct"] < -10:
                highlights.append(f"{metric}: {abs(comp['delta_pct']):.1f}% improved from baseline")

        return {
            "entity_id": entity_id,
            "best_day": {"date": best_day, "score": daily_scores.get(best_day, 0)} if best_day else None,
            "worst_day": {"date": worst_day, "score": daily_scores.get(worst_day, 0)} if worst_day else None,
            "week_vs_baseline": week_comparison,
            "total_trips": len(trips),
            "days_active": len(daily_data),
            "improvement_areas": improvements,
            "positive_highlights": highlights,
        }


# Quick test when run directly
if __name__ == "__main__":
    from core.duckdb_cache import DuckDBCache
    from core.geotab_client import GeotabClient

    cache = DuckDBCache(db_path="geopulse.db")
    cache.initialize()

    client = GeotabClient(db_cache=cache)
    client.authenticate()

    dna = FleetDNA(client, cache)

    # Get entities
    entities = dna.get_entities()
    print(f"✅ FleetDNA initialized — analyzing {len(entities)} {'devices' if dna._should_use_devices() else 'drivers'}")

    if entities:
        # Build baseline for first entity
        entity = entities[0]
        print(f"\n📊 Building baseline for {entity['name']} ({entity['id']})...")
        baseline = dna.build_baseline(entity["id"])
        for metric, stats in baseline.items():
            print(f"   {metric}: mean={stats['mean']:.2f}, std={stats['std_dev']:.2f}, p95={stats['p95']:.2f} ({stats['samples']} samples)")

        # Score today
        print(f"\n🎯 Scoring today's behavior...")
        score = dna.score_today(entity["id"])
        print(f"   Deviation: {score['deviation_score']}/100")
        print(f"   Anomaly type: {score['anomaly_type']}")
        print(f"   Confidence: {score['confidence']}%")

        # Rank fleet (first 5)
        print(f"\n🏆 Fleet rankings:")
        rankings = dna.rank_fleet()
        for i, r in enumerate(rankings[:5]):
            icon = "🔴" if r["deviation_score"] > 70 else "🟡" if r["deviation_score"] > 40 else "🟢"
            print(f"   {i+1}. {icon} {r['name']}: {r['deviation_score']}/100 ({r['anomaly_type']})")

    cache.close()

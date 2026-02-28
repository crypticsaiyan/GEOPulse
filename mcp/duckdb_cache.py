"""
DuckDB Analytics Cache — Extended

Local database for caching fleet data, LLM responses, API responses,
and storing computed FleetDNA results.

Tables:
    - driver_baselines: per-driver statistical baselines
    - trip_cache: cached trip data with metrics
    - anomaly_log: daily deviation scores and anomaly types
    - fleet_rankings: daily ranked driver lists
    - llm_cache: LLM response cache (Gemini/Ollama)
    - api_cache: Geotab API response cache with TTL
    - tts_cache: TTS audio file cache by text hash
"""

import json
import time
import hashlib
import logging
import duckdb

logger = logging.getLogger(__name__)


class DuckDBCache:
    """Manages the local DuckDB analytics cache."""

    def __init__(self, db_path="geopulse.db"):
        self.db_path = db_path
        self.conn = None

    def initialize(self):
        """Create all tables if they don't exist."""
        self.conn = duckdb.connect(self.db_path)

        # === FleetDNA Tables ===
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS driver_baselines (
                driver_id VARCHAR,
                metric VARCHAR,
                mean DOUBLE,
                std_dev DOUBLE,
                p95 DOUBLE,
                sample_count INTEGER DEFAULT 0,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (driver_id, metric)
            )
        """)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS trip_cache (
                driver_id VARCHAR,
                trip_id VARCHAR PRIMARY KEY,
                trip_date DATE,
                distance DOUBLE,
                max_speed DOUBLE,
                average_speed DOUBLE,
                duration_seconds DOUBLE,
                idle_duration_seconds DOUBLE,
                device_id VARCHAR,
                metrics JSON,
                cached_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS anomaly_log (
                driver_id VARCHAR,
                log_date DATE,
                deviation_score DOUBLE,
                anomaly_type VARCHAR,
                details JSON,
                PRIMARY KEY (driver_id, log_date)
            )
        """)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS fleet_rankings (
                ranking_date DATE PRIMARY KEY,
                rankings JSON
            )
        """)

        # === Caching Tables ===
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS llm_cache (
                cache_key VARCHAR PRIMARY KEY,
                response TEXT,
                model VARCHAR,
                created_at DOUBLE
            )
        """)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS api_cache (
                cache_key VARCHAR PRIMARY KEY,
                response TEXT,
                ttl_seconds INTEGER,
                cached_at DOUBLE
            )
        """)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS tts_cache (
                text_hash VARCHAR PRIMARY KEY,
                audio_path VARCHAR,
                created_at DOUBLE
            )
        """)
        return True

    def _ensure_conn(self):
        """Ensure we have an active connection."""
        if self.conn is None:
            self.initialize()

    # === LLM Cache ===

    def get_llm_cache(self, cache_key, ttl_seconds=3600):
        """Get cached LLM response if fresh."""
        self._ensure_conn()
        try:
            result = self.conn.execute(
                "SELECT response, created_at FROM llm_cache WHERE cache_key = ?",
                [cache_key]
            ).fetchone()
            if result and (time.time() - result[1]) < ttl_seconds:
                return result[0]
        except Exception:
            pass
        return None

    def set_llm_cache(self, cache_key, response, model="unknown"):
        """Store LLM response in cache."""
        self._ensure_conn()
        self.conn.execute(
            """INSERT OR REPLACE INTO llm_cache (cache_key, response, model, created_at)
               VALUES (?, ?, ?, ?)""",
            [cache_key, response, model, time.time()]
        )

    # === API Cache ===

    def get_api_cache(self, endpoint, params_hash, ttl_seconds=60):
        """Get cached API response if fresh."""
        self._ensure_conn()
        cache_key = f"{endpoint}:{params_hash}"
        try:
            result = self.conn.execute(
                "SELECT response, cached_at, ttl_seconds FROM api_cache WHERE cache_key = ?",
                [cache_key]
            ).fetchone()
            if result:
                ttl = result[2] if result[2] else ttl_seconds
                if (time.time() - result[1]) < ttl:
                    return json.loads(result[0])
        except Exception:
            pass
        return None

    def set_api_cache(self, endpoint, params_hash, response, ttl_seconds=60):
        """Store API response in cache."""
        self._ensure_conn()
        cache_key = f"{endpoint}:{params_hash}"
        self.conn.execute(
            """INSERT OR REPLACE INTO api_cache (cache_key, response, ttl_seconds, cached_at)
               VALUES (?, ?, ?, ?)""",
            [cache_key, json.dumps(response), ttl_seconds, time.time()]
        )

    # === TTS Cache ===

    def get_tts_cache(self, text):
        """Get cached TTS audio path if it exists."""
        self._ensure_conn()
        text_hash = hashlib.sha256(text.encode()).hexdigest()[:32]
        try:
            result = self.conn.execute(
                "SELECT audio_path FROM tts_cache WHERE text_hash = ?",
                [text_hash]
            ).fetchone()
            if result:
                import os
                if os.path.exists(result[0]):
                    return result[0]
        except Exception:
            pass
        return None

    def set_tts_cache(self, text, audio_path):
        """Store TTS audio path in cache."""
        self._ensure_conn()
        text_hash = hashlib.sha256(text.encode()).hexdigest()[:32]
        self.conn.execute(
            """INSERT OR REPLACE INTO tts_cache (text_hash, audio_path, created_at)
               VALUES (?, ?, ?)""",
            [text_hash, audio_path, time.time()]
        )

    # === FleetDNA Data Methods ===

    def store_baseline(self, driver_id, metric, mean, std_dev, p95, sample_count):
        """Store or update a driver baseline metric."""
        self._ensure_conn()
        self.conn.execute(
            """INSERT OR REPLACE INTO driver_baselines
               (driver_id, metric, mean, std_dev, p95, sample_count, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)""",
            [driver_id, metric, mean, std_dev, p95, sample_count]
        )

    def get_baseline(self, driver_id):
        """Get all baseline metrics for a driver."""
        self._ensure_conn()
        results = self.conn.execute(
            "SELECT metric, mean, std_dev, p95, sample_count FROM driver_baselines WHERE driver_id = ?",
            [driver_id]
        ).fetchall()
        return {row[0]: {"mean": row[1], "std_dev": row[2], "p95": row[3], "samples": row[4]}
                for row in results}

    def store_anomaly(self, driver_id, log_date, deviation_score, anomaly_type, details):
        """Log a daily anomaly score."""
        self._ensure_conn()
        self.conn.execute(
            """INSERT OR REPLACE INTO anomaly_log
               (driver_id, log_date, deviation_score, anomaly_type, details)
               VALUES (?, ?, ?, ?, ?)""",
            [driver_id, str(log_date), deviation_score, anomaly_type, json.dumps(details)]
        )

    def store_rankings(self, ranking_date, rankings):
        """Store daily fleet rankings."""
        self._ensure_conn()
        self.conn.execute(
            """INSERT OR REPLACE INTO fleet_rankings (ranking_date, rankings)
               VALUES (?, ?)""",
            [str(ranking_date), json.dumps(rankings)]
        )

    def get_rankings(self, ranking_date):
        """Get rankings for a specific date."""
        self._ensure_conn()
        result = self.conn.execute(
            "SELECT rankings FROM fleet_rankings WHERE ranking_date = ?",
            [str(ranking_date)]
        ).fetchone()
        return json.loads(result[0]) if result else None

    def store_trips(self, trips_data):
        """Bulk insert trips into the cache."""
        self._ensure_conn()
        for t in trips_data:
            self.conn.execute(
                """INSERT OR REPLACE INTO trip_cache
                   (driver_id, trip_id, trip_date, distance, max_speed, average_speed,
                    duration_seconds, idle_duration_seconds, device_id, metrics)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                [
                    t.get("driver_id", ""),
                    t.get("trip_id", t.get("id", "")),
                    t.get("trip_date", ""),
                    t.get("distance", 0),
                    t.get("max_speed", 0),
                    t.get("average_speed", 0),
                    t.get("duration_seconds", 0),
                    t.get("idle_duration_seconds", 0),
                    t.get("device_id", ""),
                    json.dumps(t.get("metrics", {})),
                ]
            )

    def get_driver_trips(self, driver_id, days_back=90):
        """Get cached trips for a driver."""
        self._ensure_conn()
        results = self.conn.execute(
            """SELECT trip_id, trip_date, distance, max_speed, average_speed,
                      duration_seconds, idle_duration_seconds, device_id
               FROM trip_cache
               WHERE driver_id = ?
               AND trip_date >= CURRENT_DATE - INTERVAL ? DAY
               ORDER BY trip_date DESC""",
            [driver_id, days_back]
        ).fetchall()
        return [
            {
                "trip_id": r[0], "trip_date": str(r[1]), "distance": r[2],
                "max_speed": r[3], "average_speed": r[4],
                "duration_seconds": r[5], "idle_duration_seconds": r[6],
                "device_id": r[7]
            }
            for r in results
        ]

    def get_anomaly_history(self, driver_id, days_back=30):
        """Get anomaly history for a driver."""
        self._ensure_conn()
        results = self.conn.execute(
            """SELECT log_date, deviation_score, anomaly_type, details
               FROM anomaly_log
               WHERE driver_id = ?
               AND log_date >= CURRENT_DATE - INTERVAL ? DAY
               ORDER BY log_date DESC""",
            [driver_id, days_back]
        ).fetchall()
        return [
            {
                "date": str(r[0]), "deviation_score": r[1],
                "anomaly_type": r[2], "details": json.loads(r[3]) if r[3] else {}
            }
            for r in results
        ]

    def clear_stale_cache(self, max_age_hours=24):
        """Remove old cached API/LLM responses."""
        self._ensure_conn()
        cutoff = time.time() - (max_age_hours * 3600)
        self.conn.execute("DELETE FROM api_cache WHERE cached_at < ?", [cutoff])
        self.conn.execute("DELETE FROM llm_cache WHERE created_at < ?", [cutoff])

    def execute_sql(self, sql, params=None):
        """Execute raw SQL for the query_fleet_data MCP tool."""
        self._ensure_conn()
        if params:
            return self.conn.execute(sql, params).fetchall()
        return self.conn.execute(sql).fetchall()

    def close(self):
        """Close the database connection."""
        if self.conn:
            self.conn.close()
            self.conn = None


# Quick test when run directly
if __name__ == "__main__":
    cache = DuckDBCache(db_path="/tmp/geopulse_test.db")
    try:
        cache.initialize()
        print("✅ DuckDB initialized with all 7 tables!")
        tables = cache.conn.execute("SHOW TABLES").fetchall()
        for t in tables:
            count = cache.conn.execute(f"SELECT COUNT(*) FROM {t[0]}").fetchone()[0]
            print(f"   📋 {t[0]}: {count} rows")

        # Test caching
        cache.set_llm_cache("test_key", "Hello from cache", "test-model")
        cached = cache.get_llm_cache("test_key", ttl_seconds=60)
        print(f"   🔄 LLM cache test: {'✅ hit' if cached else '❌ miss'}")

        cache.set_api_cache("test_endpoint", "hash123", {"data": [1, 2, 3]}, ttl_seconds=60)
        api_cached = cache.get_api_cache("test_endpoint", "hash123", ttl_seconds=60)
        print(f"   🔄 API cache test: {'✅ hit' if api_cached else '❌ miss'}")

        cache.close()
        import os
        os.remove("/tmp/geopulse_test.db")
    except Exception as e:
        print(f"❌ DuckDB test failed: {e}")

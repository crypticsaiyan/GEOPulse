"""
DuckDB Analytics Cache

Local database for caching fleet data and storing computed results.

Tables:
    - driver_baselines: per-driver statistical baselines
    - trip_cache: cached trip data with metrics
    - anomaly_log: daily deviation scores and anomaly types
    - fleet_rankings: daily ranked driver lists
"""

import duckdb


class DuckDBCache:
    """Manages the local DuckDB analytics cache."""

    def __init__(self, db_path="geopulse.db"):
        self.db_path = db_path
        self.conn = None

    def initialize(self):
        """Create tables if they don't exist."""
        self.conn = duckdb.connect(self.db_path)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS driver_baselines (
                driver_id VARCHAR,
                metric VARCHAR,
                mean DOUBLE,
                std_dev DOUBLE,
                p95 DOUBLE,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (driver_id, metric)
            )
        """)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS trip_cache (
                driver_id VARCHAR,
                trip_id VARCHAR PRIMARY KEY,
                trip_date DATE,
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
        return True

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
        print("✅ DuckDB initialized successfully!")
        # Verify tables exist
        tables = cache.conn.execute("SHOW TABLES").fetchall()
        for t in tables:
            print(f"   📋 Table: {t[0]}")
        cache.close()
    except Exception as e:
        print(f"❌ DuckDB init failed: {e}")

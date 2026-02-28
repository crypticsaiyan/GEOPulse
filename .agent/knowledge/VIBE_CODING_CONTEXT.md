# Vibe Coding Context — GEOPulse Quick Reference

## .env File (Required)

```
GEOTAB_DATABASE=your_database
GEOTAB_USERNAME=your_email
GEOTAB_PASSWORD=your_password
GEOTAB_SERVER=my.geotab.com
GEMINI_API_KEY=your_key
GOOGLE_MAPS_API_KEY=your_key
```

## API Call Pattern

```python
# All Geotab API calls follow this pattern:
response = requests.post(url, json={
    "method": "Get",  # or Add, Set, Remove, GetFeed
    "params": {
        "typeName": "Device",
        "credentials": creds,
        # optional: search, fromDate, toDate
    }
})
data = response.json()["result"]
```

## Common TypeNames

`Device` · `Trip` · `User` · `DeviceStatusInfo` · `LogRecord` ·
`StatusData` · `ExceptionEvent` · `FaultData` · `Zone` · `Group` · `Rule`

## GEOPulse Components

| Component | Path | Next Step |
|-----------|------|-----------|
| MCP Server | `mcp/mcp_server.py` | Implement 10 tools (Step 4) |
| Geotab Client | `mcp/geotab_client.py` | Implement data functions (Step 2) |
| FleetDNA | `mcp/fleetdna.py` | Build baseline engine (Step 3) |
| DuckDB Cache | `mcp/duckdb_cache.py` | ✅ Schema ready |
| Dashboard | `addin/index.html` | Implement map + sportscaster (Step 6) |
| Driver Feed | `frequencies/driver_feed.py` | Implement audio pipeline (Step 5) |
| Exec Podcast | `frequencies/exec_podcast.py` | Implement podcast pipeline (Step 7) |
| API Server | `server/server.py` | Implement FastAPI endpoints (Step 6f) |
| Scheduler | `scheduler/cron_jobs.py` | Wire up APScheduler (Step 8) |

## Critical Rules

1. Never hardcode credentials — `.env` + `load_dotenv()`
2. Test auth ONCE — failed auth locks account 15-30 min
3. Use `User` with `isDriver: True` — never `Driver` type
4. Always use date ranges for Trip queries
5. Activate venv: `source .venv/bin/activate.fish`

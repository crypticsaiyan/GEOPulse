---
name: geotab-docs
description: Geotab API reference and patterns for GEOPulse development. Auto-loads on any Geotab-related task including API calls, Add-In development, MCP server, Data Connector queries, and fleet data analysis.
license: Apache-2.0
metadata:
  author: GEOPulse Team
  version: "1.0"
---

# Geotab Docs Skill

## When to Use This Skill

- Any task involving Geotab API calls (Get, Add, Set, Remove)
- Building or modifying the MCP server
- Working with FleetDNA behavioral fingerprinting
- Creating the MyGeotab Add-In dashboard
- Querying the Data Connector OData endpoint
- Writing driver/manager/executive frequency pipelines

## Key References (Load on Demand)

The full Geotab vibe-coding guide lives at `../geotab-vibe-guide/` relative to this project root. Load these files based on the task at hand:

### Always Start With
- `../geotab-vibe-guide/VIBE_CODING_CONTEXT.md` — Auth pattern, .env format, API methods, critical rules (~400 tokens)

### By Task Type

| Task | Load This File |
|------|---------------|
| Python API calls | `../geotab-vibe-guide/skills/geotab/references/API_QUICKSTART.md` |
| MyGeotab Add-In | `../geotab-vibe-guide/skills/geotab/references/ADDINS.md` |
| MCP server | `../geotab-vibe-guide/skills/geotab-custom-mcp/SKILL.md` |
| Data Connector / OData | `../geotab-vibe-guide/skills/geotab/references/DATA_CONNECTOR.md` |
| Geotab Ace AI queries | `../geotab-vibe-guide/skills/geotab/references/ACE_API.md` |
| Add-In styling (Zenith) | `../geotab-vibe-guide/skills/geotab/references/ZENITH_STYLING.md` |

### Project-Specific Context
- `./PLAN.md` — Full 11-step build plan for GEOPulse
- `./.env.example` — All credential placeholders

## Authentication Pattern (Python)

```python
from dotenv import load_dotenv
import os, requests

load_dotenv()

url = f"https://{os.getenv('GEOTAB_SERVER')}/apiv1"
auth = requests.post(url, json={"method": "Authenticate", "params": {
    "database": os.getenv('GEOTAB_DATABASE'),
    "userName": os.getenv('GEOTAB_USERNAME'),
    "password": os.getenv('GEOTAB_PASSWORD')
}})
creds = auth.json()["result"]["credentials"]
```

Or using the `mygeotab` library:

```python
import mygeotab
from dotenv import load_dotenv
import os

load_dotenv()

api = mygeotab.API(
    username=os.getenv('GEOTAB_USERNAME'),
    password=os.getenv('GEOTAB_PASSWORD'),
    database=os.getenv('GEOTAB_DATABASE'),
    server=os.getenv('GEOTAB_SERVER', 'my.geotab.com')
)
api.authenticate()
```

## Critical Rules

1. **Never hardcode credentials** — use `.env` + `python-dotenv`
2. **Test auth ONCE before loops** — failed auth locks account 15-30 min
3. **Never use `typeName: "Driver"`** — use `User` with `search: {isDriver: True}`
4. **Always use date ranges for trips** — never fetch all trips without time bounds
5. **Add `.env` to `.gitignore`** — security first
6. **Call `load_dotenv()` first** — before any `os.getenv()`

## Common TypeNames

`Device` · `Trip` · `User` · `DeviceStatusInfo` · `LogRecord` · `StatusData` · `ExceptionEvent` · `FaultData` · `Zone` · `Group` · `Rule` · `Diagnostic`

## GEOPulse Architecture

```
                    ┌──────────────────┐
                    │   MCP Server     │
                    │  (AI Brain)      │
                    │  10 tools        │
                    └────────┬─────────┘
                             │
              ┌──────────────┼──────────────┐
              │              │              │
    ┌─────────▼──┐  ┌───────▼────┐  ┌──────▼─────┐
    │ Freq 1     │  │ Freq 2     │  │ Freq 3     │
    │ Drivers    │  │ Managers   │  │ Executives │
    │ Audio+Email│  │ Dashboard  │  │ Podcast    │
    │ Weekly Fri │  │ Live 24/7  │  │ Weekly Mon │
    └────────────┘  └────────────┘  └────────────┘
```

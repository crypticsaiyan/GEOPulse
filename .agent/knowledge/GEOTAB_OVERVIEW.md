# Geotab Platform Overview (GEOPulse Context)

## What is Geotab?

World's leading fleet management platform — 5M+ vehicles, 163 countries.
Provides real-time telematics data: GPS, diagnostics, driver behavior, fuel.

## Key Entities for GEOPulse

| Entity | TypeName | Use in GEOPulse |
|--------|----------|-----------------|
| Vehicles | `Device` | Fleet inventory, map markers |
| Live positions | `DeviceStatusInfo` | Real-time map, sportscaster |
| Trips | `Trip` | FleetDNA baseline building |
| Safety events | `ExceptionEvent` | Anomaly detection, ticker, coaching |
| Fault codes | `FaultData` | Predictive maintenance |
| Drivers | `User` (isDriver:true) | All frequency outputs |
| Groups | `Group` | Write-back: "Welfare Check", "Top Performers" |
| Rules | `Rule` | Write-back: coaching alerts |

## API Methods

- `Get` — Read entities (most common)
- `Add` — Create new entity (groups, rules, zones)
- `Set` — Update existing entity
- `Remove` — Delete entity
- `GetFeed` — Streaming feed with version token (for live events)
- `Authenticate` — Get session credentials

## Authentication Pattern

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

## Write-Back Capabilities (Critical for Hackathon Points)

GEOPulse writes back to Geotab to demonstrate live automation:
1. **Groups** — "Welfare Check Week N", "Week N Champions"
2. **Rules** — Per-driver coaching alerts when deviation > threshold

## Data Connector (OData)

Pre-aggregated KPIs via `https://odata-connector-{N}.geotab.com/odata/v4/svc/`.
HTTP Basic Auth with `database/username` as username.
Tables: `VehicleKpi_Daily`, `DriverSafety_Daily`, `FaultMonitoring`, etc.

## Critical Rules

1. Never hardcode credentials — use .env
2. Test auth ONCE before loops (lockout: 15-30 min)
3. Use `User` with `isDriver: True`, never `Driver` type
4. Always use date ranges for Trip queries
5. ExceptionEvent has NO GPS — use LogRecord for coordinates

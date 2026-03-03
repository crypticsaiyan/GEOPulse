# 📡 GEOPulse

**One Fleet Brain. Every Stakeholder Gets Their Own Signal.**

> GEOPulse reads your Geotab fleet data through an MCP server, builds a behavioral fingerprint for every driver using 90 days of history, then broadcasts **three personalized intelligence streams** — a weekly driver coaching clip, a live sportscaster dashboard, and a Monday executive podcast — so that every person in your organization hears their fleet in their own format, on their own schedule.

[▶ Watch the 3-Minute Demo](./demo/GEOPulse-3min-demo.mp4)

Quick submission assets:
- [3-Minute Video Script](./DEMO_VIDEO_SCRIPT.md)
- [README Walkthrough Script](./README_WALKTHROUGH_SCRIPT.md)
- [Prompts Used While Vibe Coding](./PROMPTS_USED_WHILE_VIBE_CODING.md)
- [Architecture Deep-Dive](./ARCHITECTURE.md)

---

## 🎬 Demo Submission Assets

- **Video script:** [DEMO_VIDEO_SCRIPT.md](./DEMO_VIDEO_SCRIPT.md)
- **README walkthrough script:** [README_WALKTHROUGH_SCRIPT.md](./README_WALKTHROUGH_SCRIPT.md)
- **Prompt library:** [PROMPTS_USED_WHILE_VIBE_CODING.md](./PROMPTS_USED_WHILE_VIBE_CODING.md)
- **Architecture deep-dive:** [ARCHITECTURE.md](./ARCHITECTURE.md)
- **Tip:** Keep the video exactly 3:00 and use real demo-database names/vehicle IDs from your run.

---

## 🏗️ Architecture

```
                    ┌────────────────────────────┐
                    │      Geotab API            │
                    │  (Devices, Trips, Events,  │
                    │   Faults, DeviceStatusInfo) │
                    └────────────┬───────────────┘
                                 │
                    ┌────────────▼───────────────┐
                    │   geotab_client.py          │
                    │   9 API functions + cache   │
                    └────────────┬───────────────┘
                                 │
              ┌──────────────────┼──────────────────┐
              │                  │                   │
    ┌─────────▼────────┐ ┌──────▼──────────┐ ┌──────▼──────┐
    │   FleetDNA       │ │  DuckDB Cache   │ │ LLM Provider│
    │  Behavioral      │ │  7 tables       │ │ Gemini/     │
    │  Fingerprinting  │ │  API + TTS +    │ │ Ollama      │
    │  Z-Score Engine  │ │  LLM cache      │ │             │
    └────────┬─────────┘ └───────┬─────────┘ └──────┬──────┘
             │                   │                   │
    ┌────────▼───────────────────▼───────────────────▼──────┐
    │              MCP Server (9 Tools)                      │
    │  The AI Brain — Claude chains tools to answer queries  │
    └──────┬──────────────────┬────────────────────┬────────┘
           │                  │                    │
  ┌────────▼──────┐  ┌───────▼────────┐  ┌───────▼────────┐
  │ 🎙️ Frequency 1 │  │ 📡 Frequency 2 │  │ 🎧 Frequency 3 │
  │  Driver Feed   │  │  Manager       │  │  Executive     │
  │  Friday 5 PM   │  │  Dashboard     │  │  Podcast       │
  │  Audio + Email  │  │  Live Map +    │  │  Monday 5 AM   │
  │  per driver     │  │  Sportscaster  │  │  Two-host AI   │
  └────────────────┘  └────────────────┘  └────────────────┘
```

---

## 📸 Screenshots

> Add screenshots to a `screenshots/` folder and update the paths below.

### Manager Dashboard — Live Map & Sportscaster
![Manager Dashboard](./screenshots/dashboard-live-map.png)

### Driver Feed — Personalized Coaching Email
![Driver Feed Email](./screenshots/driver-feed-email.png)

### FleetDNA Anomaly Panel
![FleetDNA Anomaly Panel](./screenshots/fleetdna-anomaly-panel.png)

### Executive Podcast — Monday Morning Briefing
![Executive Podcast](./screenshots/executive-podcast.png)

### Ace AI Chat — Natural Language Fleet Queries
![Ace AI Chat](./screenshots/ace-ai-chat.png)

---

## ✨ Features

### 🧬 FleetDNA — Behavioral Fingerprinting
- Builds a 90-day statistical baseline per driver **or per vehicle** (auto-detects demo databases with no real driver IDs)
- 7 weighted metrics: `avg_speed` (×1.5), `max_speed` (×2.0), `trip_distance` (×1.0), `trip_duration` (×0.8), `idle_ratio` (×1.2), `daily_distance` (×1.0), `daily_trips` (×0.5)
- Compares today to *their own normal* using Z-score per metric, combined into a weighted deviation score
- Scale: 0 (perfectly normal) → 100 (completely anomalous)
- Detects stress, fatigue, or medical events — not just rule violations
- Persists baselines and daily scores in DuckDB for trend analysis and weekly delta reporting

### 🎙️ Frequency 1: Driver Feed (Friday 5 PM)
- Personalized 90-second audio coaching clip per driver
- HTML email with metric bars (this week vs their personal average)
- Fleet rank badge, coaching tips, audio play button

### 📡 Frequency 2: Manager Dashboard (Live)
- Dark-themed real-time map — **Leaflet 1.9.4** + CartoDB Dark Matter tiles + `leaflet.heat` heatmap plugin (no API key required)
- Live sportscaster audio commentary (ESPN-style, Gemini-generated + Google Cloud TTS, auto-refreshes every 60s)
- Event ticker with real-time exception events (GetFeed streaming, per-vehicle deduplication)
- FleetDNA anomaly panel with pulsing alerts + deviation score badges
- Detail drawer: radar chart (Today vs Normal), metric breakdown, coaching tip
- One-click Welfare Check → creates Geotab Group instantly (live write-back to MyGeotab)
- **Ace AI chat**: natural-language fleet questions answered live via Geotab Ace (`GetAceResults`)
- **Report generator**: one-click AI incident or coaching report in structured Markdown
- **Trip replay**: GPS breadcrumb animation for any vehicle's most recent trip

### 🎧 Frequency 3: Executive Podcast (Monday 5 AM)
- 5-minute two-host podcast (Alex & Jamie)
- Uses real fleet data: vehicle numbers, driver names, percentages
- Structure: Cold open → Top story → Safety dive → Driver spotlight → Prediction

### 🤖 MCP Server (9 Tools)
AI-chainable tools that let Claude reason about your fleet:

| # | Tool | Purpose |
|---|------|---------|
| 1 | `get_fleet_overview` | All vehicles + live positions + FleetDNA deviation scores |
| 2 | `get_driver_dna` | Full 90-day baseline + today's score + weekly delta for one entity |
| 3 | `find_anomalous_drivers` | All entities above a deviation threshold, ranked worst-first |
| 4 | `get_fuel_analysis` | Distance/idle rankings — identifies fuel-inefficient routes |
| 5 | `get_safety_events` | Exception events grouped by driver + rule type for last N hours |
| 6 | `query_fleet_data` | Freeform SQL against DuckDB — trips, baselines, anomaly log |
| 7 | `create_group` | Write-back: Add Geotab Group + assign vehicles in one call |
| 8 | `create_coaching_rule` | Write-back: create exception alert rule for a specific driver |
| 9 | `generate_fleet_narrative` | Gemini narrative scoped to `driver`, `manager`, or `executive` audience |

### 🗣️ Ace AI Integration
- Natural-language queries routed to Geotab Ace API (`GetAceResults`)
- Uses async create-chat → send-prompt → poll pattern via `ace_client.py`
- Falls back to local Gemini with cached fleet context when Ace is unavailable
- Exposed at `/api/ace-query` (dashboard chat panel) and as MCP context

### 📋 Report Generation
- `/api/generate-report` produces structured Markdown incident or coaching reports
- Source data: entity's 90-day baseline + today's Z-scores + recent exception events
- Two modes: `incident` (risk assessment table, contributing factors) and `coaching` (positive reinforcement, action items)

### 🔁 Trip Replay
- `/api/trip-replay/{device_id}` fetches GPS `LogRecord` breadcrumbs for the latest trip
- Dashboard animates vehicle movement over the route with speed-based colour coding

### ✍️ Write-Back Automation
GEOPulse doesn't just read — it writes back to Geotab:
- **Morning analysis** → "Needs Attention" + "Welfare Check" groups
- **Friday driver feed** → "Week N Champions" group + coaching rules for bottom performers
- **Monday podcast** → Archive previous week's groups
- **Real-time** → Instant welfare-check group created from the dashboard anomaly panel

---

## 🔧 Geotab API Calls

| Method | typeName / Endpoint | Key Filters | Used In |
|--------|---------------------|-------------|---------|
| `Authenticate` | — | database, userName, password | `geotab_client.py` |
| `Get` | `DeviceStatusInfo` | — | `get_live_positions()` — live positions, speed, bearing |
| `GetFeed` | `ExceptionEvent` | `fromVersion` | `get_live_events()` — streaming events + version token |
| `Get` | `ExceptionEvent` | `fromDate`, `userSearch` | `get_driver_exceptions()` — per-entity exception history |
| `Get` | `Trip` | `fromDate`, `deviceSearch` | `get_driver_trips()` — trip metrics (distance, speed, idle) |
| `Get` | `LogRecord` | `deviceSearch`, `fromDate`, `toDate` | `trip_replay()` endpoint — GPS breadcrumbs |
| `Get` | `FaultData` | `faultState: Active`, `fromDate` | `get_active_faults()` — deduped active faults per device |
| `Get` | `User` | `isDriver: true` → fallback to all | `get_all_drivers()` — driver list (demo DB safe) |
| `Get` | `Device` | — | `get_all_devices()` — all vehicles |
| `Add` | `Group` | `name`, `parent` | `create_group()` — welfare check / champions groups |
| `Add` | `Rule` | `name`, `condition` | `create_rule()` — coaching exception rules |
| `GetAceResults` | — | `functionName`, `functionParameters` | `ace_client.py` — natural-language SQL via Ace AI |
| OData | `VehicleKpi_Daily` | `$filter=Date ge …` | `get_kpi_data()` — weekly KPI aggregates via Data Connector |

---

## 🌐 FastAPI Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/` | Landing page (serves `index.html`) |
| `GET` | `/dashboard` | Dashboard static files |
| `GET` | `/api/live-positions` | All vehicles enriched with FleetDNA deviation scores |
| `GET` | `/api/live-events` | Exception event feed with version token for polling |
| `GET` | `/api/driver/{entity_id}` | Full FleetDNA profile: baseline + today's score + weekly delta |
| `GET` | `/api/anomalies?threshold=60` | All entities above the deviation threshold |
| `POST` | `/api/generate-commentary` | Gemini sportscaster narration + Google TTS audio (base64 MP3) |
| `POST` | `/api/tts` | Text → speech via Google Cloud TTS (Journey-D default, Neural2-D fallback) |
| `POST` | `/api/write-back/group` | Create a Geotab group + assign vehicle IDs live |
| `POST` | `/api/send-mail` | Manager brief email with optional audio attachment via Gmail |
| `POST` | `/api/ace-query` | Natural-language question → Geotab Ace (falls back to Gemini) |
| `POST` | `/api/generate-report` | AI incident or coaching report in Markdown |
| `GET` | `/api/trip-replay/{device_id}` | GPS breadcrumbs from `LogRecord` for trip animation |
| `GET` | `/health` | Server status, LLM provider, Ace availability |

---

## 🤖 AI Prompts (Verbatim)

### Driver Coach (Frequency 1)
```
You are a warm, encouraging fleet safety coach generating a personal
weekly audio script for a driver. Rules:
- Always use their first name
- Lead with something positive and specific (not generic)
- Mention ONE specific rough moment with exact day, time, and location
  (e.g. "Wednesday morning on the I-95 on-ramp at 8:42 AM")
- Compare to THEIR OWN normal, never to fleet average
  (e.g. "that's not your usual pattern on that stretch")
- Include fleet rank out of total drivers
- End warmly and specifically
- Maximum 150 words. Must sound natural when spoken aloud.
- Never mention data, algorithms, or scores. Just coach.
- Tone: like a trusted colleague, not a corporate report
```

### Sportscaster Commentary (Frequency 2)
```
You are an energetic but professional fleet safety sportscaster.
Rules:
- Voice: match the tone perfectly.
- Celebrate good driving if tone allows: 'Marcus is having an absolute clinic today'.
- Flag concerns with urgency: 'that's the third harsh brake this morning'.
- Mention specific vehicle numbers and driver names.
- When FleetDNA flags an anomaly, note it with the deviation percentage.
- Keep each commentary update to 3-4 sentences max.
- Never use corporate/robotic language. You're having fun with this.
Return ONLY the spoken text, no formatting.
```

### Manager Morning Brief (Frequency 2b)
```
You are a professional fleet operations analyst writing a morning brief.
Rules:
- Lead with the single most important thing the manager needs to know TODAY
- Be specific: mention vehicle numbers, driver names, exact metrics
- Include 3 action items ordered by urgency
- Flag any vehicles needing immediate maintenance attention
- Note any drivers whose behavior has changed significantly from baseline
- Keep it under 200 words. Dense, no filler.
- Tone: confident, data-driven, respectful of their time
```

### Executive Podcast (Frequency 3)
```
You are writing a script for a two-host fleet analytics podcast.
Host 1 name: Alex. Host 2 name: Jamie.
Rules:
- Alex leads, Jamie provides depth and counterpoints
- Structure: Cold open hook → Week's top story → Safety deep dive
             → Driver spotlight (one good, one improving)
             → Prediction for next week → Sign-off
- Each episode: 600-700 words (5 min when spoken at natural pace)
- Make specific references to real data: vehicle numbers, driver names,
  percentages, dollar amounts. No vague statements.
- Jamie should challenge Alex at least once ("But Alex, isn't the real
  story here...") — it makes it feel real
- One "story of the week" — the most interesting fleet narrative from the data
- End with one specific prediction for next week based on trends
- Format: Alex: [text] \n Jamie: [text] — no stage directions
```

### Fleet Narrative Generator (MCP Tool)
```
Audience-specific system prompts:
- driver:    "You are a supportive fleet coach. Be warm, specific, encouraging."
- manager:   "You are a fleet operations analyst. Be data-driven, concise, actionable."
- executive: "You are a fleet strategy advisor. Focus on trends, costs, risks."
```

---

## 🔵 Google Products Used

| # | Product | Exact Role in GEOPulse |
|---|---------|----------------------|
| 1 | **Gemini 2.0 Flash** | All LLM generation: driver scripts, sportscaster commentary, manager briefs, narratives |
| 2 | **Gemini 2.0 Flash (podcast)** | Executive podcast script — same model, higher token budget, richer prompting |
| 3 | **Google Cloud TTS** | Driver clips (Neural2-D), sportscaster (Journey-D, Neural2-D fallback), podcast dual-voice (Neural2-J + Neural2-F) |
| 4 | **Gmail API** | Driver weekly coaching emails + manager daily morning briefs (OAuth2 + SMTP fallback) |
| 5 | **Google Sheets API** | Fleet Intelligence Dashboard — weekly KPI rows appended after each podcast episode |
| 6 | **Google Drive API** | Podcast MP3 + script stored per-episode; shared link embedded in executive email |
| 7 | **Google Cloud IAM** | Service account credentials for TTS, Sheets, and Drive integrations |
| 8 | **Google Fonts** | Inter (UI text) + JetBrains Mono (metric values) loaded in dashboard |

> **Not Google:** The fleet map uses open-source **Leaflet 1.9.4** with CartoDB Dark Matter tiles + `leaflet.heat` heatmap plugin. No API key required.

---

## 🚀 How to Run

### Prerequisites
- Python 3.10+
- [Geotab demo database](https://my.geotab.com/registration.html) (click "Create a Demo Database")
- [Gemini API key](https://aistudio.google.com/apikey) (free tier works)
- Optional: [Ollama](https://ollama.ai) for local LLM (no API key needed)

### 1. Clone and setup
```bash
git clone https://github.com/yourusername/GEOPulse.git
cd GEOPulse
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure credentials
```bash
cp .env.example .env
# Fill in your values in .env
```

Required `.env` variables:
| Variable | Required | Source |
|----------|----------|--------|
| `GEOTAB_DATABASE` | ✅ | Your demo database name |
| `GEOTAB_USERNAME` | ✅ | Your Geotab account |
| `GEOTAB_PASSWORD` | ✅ | Your Geotab password |
| `GEOTAB_SERVER` | ✅ | `my.geotab.com` |
| `GEMINI_API_KEY` | ✅ (or use Ollama) | Google AI Studio |
| `GOOGLE_MAPS_API_KEY` | Unused | `map.js` exists but is not loaded — Leaflet runs without a key |
| `GOOGLE_APPLICATION_CREDENTIALS` | Optional | For TTS, Sheets, and Drive |
| `LLM_PROVIDER` | Optional | `gemini` (default) or `ollama` |

### 3. Test Geotab connection
```bash
python -m mcp.geotab_client
```

### 4. Start the dashboard server
```bash
python -m server.server
# Dashboard: http://localhost:8000
# API docs: http://localhost:8000/docs
```

### 5. Run the MCP server (for Claude Desktop)
```bash
python -m mcp.mcp_server
```

Add to Claude Desktop's `claude_desktop_config.json`:
```json
{
  "mcpServers": {
    "geopulse": {
      "command": "/path/to/GEOPulse/.venv/bin/python",
      "args": ["-m", "mcp.mcp_server"],
      "cwd": "/path/to/GEOPulse"
    }
  }
}
```

### 6. Run frequency pipelines manually
```bash
# Driver feed (generates coaching scripts + emails)
python -m frequencies.driver_feed

# Manager morning brief
python -m frequencies.manager_email

# Executive podcast
python -m frequencies.exec_podcast
```

### 7. Start the scheduler (runs everything automatically)
```bash
python -m scheduler.cron_jobs
```

---

## 📁 Project Structure

```
GEOPulse/
├── mcp/                          # The AI Brain
│   ├── mcp_server.py             # MCP server — 9 tools for Claude
│   ├── geotab_client.py          # Geotab API wrapper (10 functions + cache)
│   ├── fleetdna.py               # Behavioral fingerprinting engine
│   ├── duckdb_cache.py           # Analytics cache (7 tables)
│   ├── llm_provider.py           # Gemini/Ollama abstraction
│   ├── ace_client.py             # Geotab Ace AI query client
│   ├── google_publisher.py       # Sheets + Drive publishing
│   ├── email_sender.py           # Gmail API + SMTP fallback
│   └── writeback_manager.py      # Centralized Geotab write-backs
├── addin/                        # Manager Dashboard (MyGeotab Add-In)
│   ├── config.json               # Add-In manifest
│   ├── index.html                # Dashboard layout
│   ├── css/dashboard.css         # Dark glassmorphism theme
│   └── js/
│       ├── main.js               # Entry point + live polling
│       ├── map.js                # Google Maps alternative (unused — not loaded)
│       ├── sportscaster.js       # Live commentary engine
│       ├── ticker.js             # Event ticker
│       └── anomaly.js            # FleetDNA anomaly panel
├── dashboard/                    # Mirror of addin/ used by FastAPI server
│   └── (same structure as addin/)
├── frequencies/                  # Output Pipelines
│   ├── driver_feed.py            # Frequency 1: Friday driver audio + email
│   ├── manager_email.py          # Frequency 2b: Daily manager morning brief
│   └── exec_podcast.py           # Frequency 3: Monday two-host podcast
├── scheduler/
│   └── cron_jobs.py              # APScheduler — 4 automated jobs
├── server/
│   └── server.py                 # FastAPI backend for dashboard
├── audio/                        # Generated audio clips (gitignored)
├── tests/
│   └── test_connection.py        # Geotab auth + data pipeline tests
├── .env.example                  # Credentials template
├── requirements.txt              # Python dependencies
└── README.md                     # This file
```

---

## 🏆 Prize Targeting

| Prize | What Judges Score | GEOPulse's Edge |
|-------|-------------------|-----------------|
| 🤖 **The Innovator ($5K)** | Technical AI creativity | FleetDNA personal baselines + visible MCP tool chains |
| 💥 **The Disruptor ($2.5K)** | Most surprising idea | Live sportscaster audio — nobody else submits audio |
| 🔵 **Google Tools ($2.5K)** | Best use of Google products | 8 products, TTS dual-voice podcast, Gemini reasoning |
| 🤝 **Collaborative ($2.5K)** | Community activity | Open-source, shared prompts, daily progress posts |

---

## 📄 License

MIT License — built for the [Geotab Vibe Coding Hackathon](https://geotab.com).

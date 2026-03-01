# 📡 GEOPulse

**One Fleet Brain. Every Stakeholder Gets Their Own Signal.**

> GEOPulse reads your Geotab fleet data through an MCP server, builds a behavioral fingerprint for every driver using 90 days of history, then broadcasts **three personalized intelligence streams** — a weekly driver coaching clip, a live sportscaster dashboard, and a Monday executive podcast — so that every person in your organization hears their fleet in their own format, on their own schedule.

<!-- [▶ Watch the 3-Minute Demo](link-to-demo-video) -->

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
    │              MCP Server (10 Tools)                     │
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

## ✨ Features

### 🧬 FleetDNA — Behavioral Fingerprinting
- Builds a 90-day statistical baseline per driver (speed, braking, idle, distance, routes)
- Compares today to *their own normal* using Z-score deviations
- Deviation scale: 0 (normal) → 100 (completely anomalous)
- Detects stress, fatigue, or medical events — not just rule violations

### 🎙️ Frequency 1: Driver Feed (Friday 5 PM)
- Personalized 90-second audio coaching clip per driver
- HTML email with metric bars (this week vs their personal average)
- Fleet rank badge, coaching tips, audio play button

### 📡 Frequency 2: Manager Dashboard (Live)
- Dark-themed real-time map with color-coded vehicle markers
- Live sportscaster audio commentary (ESPN-style, AI-generated)
- Event ticker with real-time exception events
- FleetDNA anomaly panel with pulsing alerts
- Detail drawer with radar chart (Today vs Normal)
- One-click Welfare Check → creates Geotab Group instantly

### 🎧 Frequency 3: Executive Podcast (Monday 5 AM)
- 5-minute two-host podcast (Alex & Jamie)
- Uses real fleet data: vehicle numbers, driver names, percentages
- Structure: Cold open → Top story → Safety dive → Driver spotlight → Prediction

### 🤖 MCP Server (10 Tools)
AI-chainable tools that let Claude reason about your fleet:

| Tool | Purpose |
|------|---------|
| `get_fleet_overview` | All vehicles + live positions + deviation scores |
| `get_driver_dna` | Full baseline + today's score + weekly delta |
| `find_anomalous_drivers` | Drivers above deviation threshold, ranked |
| `get_fuel_analysis` | Fuel consumption ranked + idle correlation |
| `get_fault_report` | Active faults with severity + patterns |
| `get_safety_events` | Exception events grouped by driver + type |
| `query_fleet_data` | Custom SQL against DuckDB analytics cache |
| `create_group` | Write-back: create Geotab group + assign vehicles |
| `create_coaching_rule` | Write-back: create exception rule for driver |
| `generate_fleet_narrative` | LLM narrative for any audience |

### ✍️ Write-Back Automation
GEOPulse doesn't just read — it writes back to Geotab:
- **Morning analysis** → "Needs Attention" + "Welfare Check" groups
- **Friday driver feed** → "Week N Champions" group + coaching rules for bottom performers
- **Monday podcast** → Archive last week's groups
- **Real-time** → Instant welfare check group on anomaly flag

---

## 🔧 Geotab API Calls

| Method | typeName | Filters | Returns |
|--------|----------|---------|---------|
| `Get` | `DeviceStatusInfo` | — | Live positions, speed, bearing, driving state |
| `GetFeed` | `ExceptionEvent` | `fromVersion` | Streaming events with version token |
| `Get` | `Trip` | `fromDate`, `deviceSearch`/`driverSearch` | Trip metrics: distance, speed, duration, idle |
| `Get` | `ExceptionEvent` | `fromDate`, `driverSearch` | Per-driver exception history |
| `Get` | `FaultData` | `activeFrom = now - 7d` | Active faults with codes and source |
| `Get` | `Driver` / `User` | — | All drivers list |
| `Get` | `Device` | — | All vehicles list |
| `Add` | `Group` | `name`, `parent` | Creates group, returns ID |
| `Set` | `Device` | `groups` | Assigns vehicles to groups |
| `Add` | `Rule` | `name`, `conditions` | Creates exception rule |
| OData | `VehicleKpi_Daily` | `$filter=date` | Daily KPI data via Data Connector |

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
| 1 | **Gemini Flash** | All LLM generation: driver scripts, commentary, briefs, narratives |
| 2 | **Gemini Pro** | Executive podcast script generation (deeper reasoning) |
| 3 | **Google Cloud TTS** | Driver audio clips (Neural2-D), sportscaster (Neural2-J), podcast (Neural2-J + Neural2-F dual-voice) |
| 4 | **Google Maps** | Dark-mode fleet map with directional markers, heatmap layer |
| 5 | **Gmail API** | Driver weekly emails, manager morning briefs |
| 6 | **Google Sheets** | Fleet Intelligence Dashboard — weekly KPI tracking |
| 7 | **Google Sites** | Podcast player page — executives listen here |
| 8 | **Google Drive** | Podcast script storage and sharing |
| 9 | **Google Cloud** | Project infrastructure, service accounts, IAM |
| 10 | **Google Fonts** | Inter + JetBrains Mono for dashboard UI |

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
| `GOOGLE_MAPS_API_KEY` | Optional | Google Cloud Console |
| `GOOGLE_APPLICATION_CREDENTIALS` | Optional | For TTS/Sheets/Sites |
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
│   ├── mcp_server.py             # MCP server — 10 tools for Claude
│   ├── geotab_client.py          # Geotab API wrapper (9 functions + cache)
│   ├── fleetdna.py               # Behavioral fingerprinting engine
│   ├── duckdb_cache.py           # Analytics cache (7 tables)
│   ├── llm_provider.py           # Gemini/Ollama abstraction
│   └── writeback_manager.py      # Centralized Geotab write-backs
├── addin/                        # Manager Dashboard (MyGeotab Add-In)
│   ├── config.json               # Add-In manifest
│   ├── index.html                # Dashboard layout
│   ├── css/dashboard.css         # Dark glassmorphism theme
│   └── js/
│       ├── main.js               # Entry point + live polling
│       ├── map.js                # Fleet map + markers
│       ├── sportscaster.js       # Live commentary engine
│       ├── ticker.js             # Event ticker
│       └── anomaly.js            # FleetDNA anomaly panel
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
| 🔵 **Google Tools ($2.5K)** | Best use of Google products | 10 products, TTS dual-voice podcast, Gemini reasoning |
| 🤝 **Collaborative ($2.5K)** | Community activity | Open-source, shared prompts, daily progress posts |

---

## 📄 License

MIT License — built for the [Geotab Vibe Coding Hackathon](https://geotab.com).

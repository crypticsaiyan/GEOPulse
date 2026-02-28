# 🚀 GEOPulse — Complete AI Build Prompt
### Copy this entire prompt into Claude Code, Cursor, or any AI coding assistant

---

> **IMPORTANT INSTRUCTION TO AI:**
> Before writing any code, read the local folder at `./geotab-vibe-guide/` on this machine.
> Specifically read these files first, in this order:
> 1. `./geotab-vibe-guide/AGENT_SUMMARY.md`
> 2. `./geotab-vibe-guide/GEOTAB_OVERVIEW.md`
> 3. `./geotab-vibe-guide/VIBE_CODING_CONTEXT.md`
> 4. `./geotab-vibe-guide/guides/HACKATHON_IDEAS.md`
> 5. `./geotab-vibe-guide/guides/DATA_CONNECTOR.md`
> 6. `./geotab-vibe-guide/guides/GEOTAB_ADDINS.md`
> 7. `./geotab-vibe-guide/examples/` — read all example files
> 8. `./geotab-vibe-guide/skills/` — read all skill files
>
> These files contain the official Geotab API patterns, authentication methods,
> Add-In manifest format, and working code examples. Use them as your primary
> reference for ALL Geotab API calls. Do not guess API method names — look them
> up in the guide first.

---

## PROJECT: GEOPulse
**Tagline:** One Fleet Brain. Every Stakeholder Gets Their Own Signal.

You are building **GEOPulse** — a Geotab Hackathon submission targeting
three prize categories simultaneously: The Innovator ($5K), The Disruptor ($2.5K),
and Best Use of Google Tools ($2.5K). Total target: $10,000.

The system has one AI brain (an MCP server) that reads fleet data from Geotab,
performs behavioral fingerprinting per driver, and broadcasts three personalized
output streams:
- 🎙️ **Frequency 1 (Drivers):** Weekly personal audio clip + email
- 📡 **Frequency 2 (Managers):** Live sportscaster dashboard with map
- 🎧 **Frequency 3 (Executives):** Weekly auto-generated podcast

Build this step by step. Complete each step fully before moving to the next.
After each step, tell me what was built and what the next step is.

---

## CREDENTIALS & SETUP

```
Geotab Demo Database: [USER WILL FILL IN]
Geotab Username: [USER WILL FILL IN]
Geotab Password: [USER WILL FILL IN]
Geotab Server: my.geotab.com

Google Cloud Project: [USER WILL FILL IN]
Google Gemini API Key: [USER WILL FILL IN]
Google Maps API Key: [USER WILL FILL IN]
Google Cloud TTS enabled: Yes
Gmail API enabled: Yes
```

---

## STEP 1 — Project Scaffold
**Goal:** Create the full folder structure and verify Geotab auth works.

Create this exact folder structure:

```
geopulse/
├── mcp/
│   ├── mcp_server.py          # The AI brain (MCP server)
│   ├── geotab_client.py       # Geotab API wrapper
│   ├── fleetdna.py            # Behavioral fingerprinting engine
│   ├── duckdb_cache.py        # Local analytics cache
│   └── requirements.txt
├── addin/                     # MyGeotab Add-In (manager dashboard)
│   ├── config.json            # Add-In manifest
│   ├── index.html             # Main dashboard
│   ├── css/
│   │   └── dashboard.css      # Dark theme styles
│   └── js/
│       ├── main.js            # Entry point
│       ├── map.js             # Google Maps + vehicle plotting
│       ├── sportscaster.js    # Live audio commentary
│       ├── ticker.js          # Event ticker
│       └── anomaly.js         # FleetDNA anomaly panel
├── frequencies/
│   ├── driver_feed.py         # Friday driver audio + email pipeline
│   ├── manager_email.py       # Daily 6:30 AM manager brief
│   └── exec_podcast.py        # Monday executive podcast pipeline
├── scheduler/
│   └── cron_jobs.py           # All scheduled triggers
├── .env                       # All credentials (never commit)
├── .env.example               # Template for credentials
└── README.md
```

Then write a `geotab_client.py` that:
1. Authenticates with the Geotab API using credentials from `.env`
2. Has a `call(method, params)` wrapper function
3. Tests the connection by calling `Get` with `typeName: "Device"` and printing
   the count of vehicles returned
4. Run it and confirm authentication succeeds

Reference `./geotab-vibe-guide/VIBE_CODING_CONTEXT.md` for the exact
authentication pattern.

---

## STEP 2 — Geotab Data Pipeline
**Goal:** Pull all the raw data GEOPulse needs from the Geotab API.

In `geotab_client.py`, implement these data-fetching functions.
Reference `./geotab-vibe-guide/guides/DATA_CONNECTOR.md` for OData endpoints
and `./geotab-vibe-guide/GEOTAB_OVERVIEW.md` for entity names.

```python
# 2a. Live vehicle positions (for the map)
def get_live_positions():
    # Call: Get, typeName: DeviceStatusInfo
    # Returns: [{device_id, device_name, latitude, longitude,
    #            speed, bearing, is_driving, last_communication}]

# 2b. Live event stream (for sportscaster ticker)
def get_live_events(from_version=None):
    # Call: GetFeed, typeName: ExceptionEvent
    # Returns: [{vehicle_id, rule_name, timestamp, latitude, longitude}]
    # Store and return the toVersion token for next poll

# 2c. Per-driver historical trips (last 90 days, for FleetDNA baseline)
def get_driver_trips(driver_id, days_back=90):
    # Call: Get, typeName: Trip
    # Filter: fromDate = today - 90 days, driverSearch: {id: driver_id}
    # Returns: [{trip_id, start_time, stop_time, distance,
    #            max_speed, average_speed, driver_id, device_id}]

# 2d. Per-driver exception events (for behavioral fingerprinting)
def get_driver_exceptions(driver_id, days_back=90):
    # Call: Get, typeName: ExceptionEvent
    # Filter: fromDate, driverSearch
    # Returns: [{rule_name, timestamp, duration, driver_id}]

# 2e. Active fault codes (for predictive maintenance)
def get_active_faults():
    # Call: Get, typeName: FaultData
    # Filter: activeFrom = now - 7 days
    # Returns: [{device_id, code, timestamp, source_name, failure_mode}]

# 2f. All drivers list
def get_all_drivers():
    # Call: Get, typeName: Driver
    # Returns: [{id, name, keys}]

# 2g. Write-back: Create a group
def create_group(name, vehicle_ids, parent_id="GroupCompanyId"):
    # Call: Add, typeName: Group
    # Then: Set each Device's groups field to include new group
    # Returns: new group id

# 2h. Write-back: Create a rule (coaching alert)
def create_rule(name, conditions, driver_id):
    # Call: Add, typeName: Rule
    # Returns: new rule id

# 2i. Data Connector OData pull (for executive podcast data)
def get_kpi_data(entity="VehicleKpi_Daily", days_back=7):
    # OData endpoint: https://[server]/apiv1/dataconnector/odata/[entity]
    # Auth: same session token
    # Returns: parsed JSON list
```

After writing all functions, create a `test_data_pipeline.py` that calls each
one and prints a summary. Run it. Show me the output.

---

## STEP 3 — FleetDNA Behavioral Fingerprinting Engine
**Goal:** Build the AI brain that knows what's "normal" for each driver.

In `fleetdna.py`, build a class `FleetDNA` that:

```python
class FleetDNA:

    def build_baseline(self, driver_id):
        """
        Pull 90 days of trips + exceptions for this driver.
        Compute statistical baseline:
        - speed: mean, std_dev, p95
        - braking_events_per_trip: mean, std_dev
        - acceleration_events_per_trip: mean, std_dev
        - idle_time_per_trip: mean, std_dev
        - daily_distance: mean, std_dev
        - typical_hours: most common hours of driving (histogram)
        - route_consistency: how often they repeat the same routes (0-1)
        
        Store baseline in DuckDB via duckdb_cache.py.
        Return: BaselineProfile object
        """

    def score_today(self, driver_id, today_data):
        """
        Compare today's driving data to their personal baseline.
        For each metric, compute Z-score: (today - mean) / std_dev
        
        deviation_score = weighted average of absolute Z-scores
        Convert to 0-100 scale (0 = normal, 100 = completely anomalous)
        
        Return: {
            deviation_score: 0-100,
            anomaly_type: "speed" | "braking" | "route" | "time" | "multi",
            confidence: 0-100,
            details: {metric: {today, baseline_mean, z_score}},
            narrative: "string explaining what's different in plain English"
        }
        """

    def rank_fleet(self, date=None):
        """
        Score all drivers for a given day.
        Return ranked list: [{driver_id, name, deviation_score, anomaly_type}]
        Sorted by deviation_score descending (most anomalous first).
        """

    def get_weekly_delta(self, driver_id):
        """
        Compare this week vs driver's personal historical average.
        Return: {
            best_day: {date, score, highlight},
            worst_day: {date, score, issue},
            week_vs_baseline: {metric: {this_week, their_avg, delta_pct}},
            fleet_rank: {rank, total_drivers},
            improvement_areas: ["specific thing to work on"],
            positive_highlights: ["specific thing they did well"]
        }
        """
```

In `duckdb_cache.py`:

```python
# Initialize DuckDB with tables:
# - driver_baselines (driver_id, metric, mean, std_dev, p95, updated_at)
# - trip_cache (driver_id, trip_id, date, metrics JSON, cached_at)
# - anomaly_log (driver_id, date, deviation_score, anomaly_type, details JSON)
# - fleet_rankings (date, rankings JSON)
```

Test it: run `FleetDNA().build_baseline(driver_id)` for one driver from your
demo database. Print their baseline profile. Then call `score_today()` with
today's data and print the deviation score.

---

## STEP 4 — MCP Server (The Reasoning Core)
**Goal:** Build the MCP server that lets Claude chain Geotab API calls.

In `mcp/mcp_server.py`, build a fully working MCP server using the
`mcp` Python library. Implement these 10 tools:

```python
@server.tool("get_fleet_overview")
"""Returns: all vehicles with live positions + deviation scores.
   Chains: get_live_positions() + FleetDNA.rank_fleet()
   Use for: "What's happening in the fleet right now?" """

@server.tool("get_driver_dna")
"""Input: driver_name_or_id (string)
   Returns: full baseline profile + today's deviation score + weekly delta
   Chains: FleetDNA.build_baseline() + FleetDNA.score_today() + get_weekly_delta()
   Use for: "Is Driver X behaving normally?" """

@server.tool("find_anomalous_drivers")
"""Input: threshold (int, default 70), date (optional)
   Returns: all drivers above deviation threshold, ranked
   Chains: FleetDNA.rank_fleet() + filter
   Use for: "Who is acting unlike themselves today?" """

@server.tool("get_fuel_analysis")
"""Returns: fuel consumption ranked by driver + vehicle,
            idle time correlation, week-over-week delta
   Chains: get_driver_trips() + get_kpi_data("VehicleKpi_Daily")
   Use for: "Who is burning the most fuel and why?" """

@server.tool("get_fault_report")
"""Returns: active faults with severity + historical pattern match
            (how many vehicles with this fault eventually failed)
   Chains: get_active_faults() + DuckDB historical lookup
   Use for: "Which vehicles need maintenance?" """

@server.tool("get_safety_events")
"""Input: hours_back (int, default 24)
   Returns: all exception events grouped by driver + rule type
   Chains: get_live_events() + group_by_driver
   Use for: "What safety events happened today?" """

@server.tool("query_fleet_data")
"""Input: sql_query (string) — natural language converted to SQL by Claude
   Runs SQL against DuckDB cache of fleet data
   Returns: query results as structured JSON
   Use for: analytical questions that need custom slicing """

@server.tool("create_group")
"""Input: group_name (string), vehicle_ids or driver_ids (list), reason (string)
   WRITE-BACK: Creates group in Geotab + assigns vehicles
   Returns: {group_id, url_to_view_in_mygeotab}
   Use for: "Flag these drivers for coaching" """

@server.tool("create_coaching_rule")
"""Input: driver_id, rule_type ("harsh_braking"|"speeding"|"idle"|"welfare")
   WRITE-BACK: Creates exception rule in Geotab for that driver
   Returns: {rule_id, description}
   Use for: "Set up a coaching alert for Driver X" """

@server.tool("generate_fleet_narrative")
"""Input: data_summary (dict), audience ("driver"|"manager"|"executive")
   Calls Gemini Flash with the data + audience-specific system prompt
   Returns: plain-English narrative text
   Use for: converting raw numbers into human-readable insights """
```

Connect this MCP server to Claude Desktop by generating the correct
`claude_desktop_config.json` entry and printing instructions.

Test the MCP server by running 3 chained queries:
1. "Which driver is most unlike themselves today?"
2. "Which vehicle is burning the most fuel and why?"
3. "Flag all anomalous drivers for welfare check and create the Geotab group"

Show me the full tool call chain for each query.

---

## STEP 5 — Frequency 1: Driver Feed (Personal Audio + Email)
**Goal:** Every Friday, each driver gets a personal 90-second audio clip + email.

In `frequencies/driver_feed.py`:

```python
def generate_driver_script(driver_id):
    """
    1. Call FleetDNA.get_weekly_delta(driver_id) to get full week summary
    2. Call geotab_client.get_driver_exceptions(driver_id, days_back=7)
       to get specific events with timestamps and locations
    3. Call geotab_client.get_driver_trips(driver_id, days_back=7)
       to find best and worst specific trips
    4. Send to Gemini Flash with this EXACT system prompt:

    SYSTEM PROMPT:
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
    
    5. Return the script text
    """

def generate_driver_audio(script_text, driver_name):
    """
    Call Google Cloud TTS with:
    - Voice: en-US-Neural2-D (warm male) or en-US-Neural2-F (warm female)
    - Speaking rate: 0.95 (slightly slower = more personal)
    - Pitch: -1.0 (slightly lower = more authoritative warmth)
    Save as: ./audio/{driver_name}_{week_number}.mp3
    Return: file path
    """

def generate_driver_email_html(driver_id, audio_url):
    """
    Generate beautiful HTML email with:
    - Dark header with GEOPulse branding
    - Driver name + week number
    - 5 metric bars (speed, braking, fuel, route, idle)
      each showing: this week vs their personal average
      color coded: green if better, red if worse
    - ASCII-style sparkline for 7-day trend
    - Big play button linking to audio clip
    - Fleet rank badge (e.g. "#4 of 18 drivers")
    - One specific coaching tip (from Gemini)
    - Footer: "Generated from your actual driving data"
    """

def send_driver_email(driver_email, driver_name, html_content):
    """
    Use Gmail API with OAuth2 to send the email
    Subject: "Your Week {N} Summary, {first_name} 🚗"
    From: GEOPulse <noreply@geopulse.app>
    """

def run_friday_driver_feed():
    """
    Main function — run every Friday at 5 PM:
    1. Get all drivers from Geotab
    2. For each driver: generate_script → generate_audio → generate_email → send
    3. Write-back to Geotab:
       - Top 5 drivers → create_group("Week {N} Top Performers", [...])
       - Drivers with deviation_score > 70 → create_group("Welfare Check Week {N}")
       - Drivers 2+ std deviations below baseline → create_coaching_rule(driver_id)
    4. Log: how many emails sent, groups created, errors
    """
```

Generate 3 sample driver audio clips from your demo database.
Play them back and iterate the Gemini prompt until the tone sounds
genuinely warm and specific (not corporate). Show me the final prompt
and 3 generated scripts.

---

## STEP 6 — Frequency 2: Manager Dashboard (Live Sportscaster)
**Goal:** Build the MyGeotab Add-In with dark map, live sportscaster, event ticker.

### 6a. Add-In Manifest

In `addin/config.json`, create a valid MyGeotab Add-In manifest.
Reference `./geotab-vibe-guide/guides/GEOTAB_ADDINS.md` for the exact
manifest format and required fields.

```json
{
  "name": "GEOPulse",
  "supportEmail": "your@email.com",
  "items": [{
    "page": "map",
    "title": "GEOPulse",
    "menuName": { "en": "GEOPulse" },
    "icon": "https://[your-host]/addin/icon.svg",
    "url": "https://[your-host]/addin/index.html"
  }],
  "isSigned": false
}
```

### 6b. Dashboard HTML Structure

In `addin/index.html`, build a single-page dashboard with this layout:

```html
<!DOCTYPE html>
<html>
<head>
  <title>GEOPulse</title>
  <!-- Google Fonts: Inter -->
  <!-- Chart.js for radar + sparklines -->
  <!-- Google Maps API -->
  <link rel="stylesheet" href="css/dashboard.css">
</head>
<body>
  <!-- TOP BAR -->
  <header class="topbar">
    <div class="brand">🎙️ GEOPulse</div>
    <div class="broadcast-status">
      <span class="live-dot"></span> LIVE BROADCAST
    </div>
    <div class="fleet-summary">
      <!-- 3 numbers: Total Vehicles | Anomalies | Events Today -->
    </div>
  </header>

  <!-- MAIN GRID -->
  <main class="grid">
    
    <!-- LEFT: GOOGLE MAP (60% width) -->
    <section class="map-panel">
      <div id="map"></div>
      <div class="map-controls">
        <!-- Toggle buttons: Heatmap | Trip Trails | Geofences | Anomaly Only -->
      </div>
    </section>

    <!-- RIGHT: BROADCAST PANEL (40% width) -->
    <section class="broadcast-panel">
      
      <!-- SPORTSCASTER AUDIO PLAYER -->
      <div class="sportscaster-card">
        <div class="sc-header">🎙️ LIVE BROADCAST</div>
        <div class="sc-waveform"><!-- animated waveform SVG --></div>
        <div class="sc-text" id="current-commentary">
          <!-- Latest sportscaster line shown as text too -->
        </div>
        <audio id="sc-audio" autoplay></audio>
      </div>

      <!-- EVENT TICKER -->
      <div class="ticker-card">
        <div class="ticker-header">📡 LIVE EVENTS</div>
        <div class="ticker-list" id="event-ticker">
          <!-- Events slide in from top, auto-scroll -->
        </div>
      </div>

      <!-- ANOMALY PANEL -->
      <div class="anomaly-card" id="anomaly-panel">
        <div class="anomaly-header">⚠️ ANOMALIES (FleetDNA)</div>
        <!-- Per-anomaly: driver name, deviation score, type, action buttons -->
        <!-- Pulsing red border animation -->
      </div>

    </section>

  </main>

  <!-- DETAIL DRAWER (slides in from right when vehicle clicked) -->
  <aside class="detail-drawer" id="detail-drawer">
    <!-- Vehicle/Driver details -->
    <!-- Radar chart: Today vs Their Normal -->
    <!-- 7-day sparkline -->
    <!-- Fault timeline -->
    <!-- Action buttons: Welfare Check, Coaching Flag, Watch & Wait -->
  </aside>

  <script src="js/main.js"></script>
</body>
</html>
```

### 6c. Dark Theme CSS

In `addin/css/dashboard.css`:

```css
/* === DESIGN TOKENS === */
:root {
  --bg-primary:    #0D1117;
  --bg-secondary:  #161B22;
  --bg-card:       #1C2128;
  --border:        #30363D;
  --text-primary:  #E6EDF3;
  --text-muted:    #7D8590;
  --green:         #3FB950;
  --yellow:        #D29922;
  --red:           #F85149;
  --blue:          #388BFD;
  --font:          'Inter', -apple-system, sans-serif;
}

/* === LAYOUT === */
body {
  background: var(--bg-primary);
  color: var(--text-primary);
  font-family: var(--font);
  margin: 0;
  height: 100vh;
  display: flex;
  flex-direction: column;
}

.grid {
  display: grid;
  grid-template-columns: 60fr 40fr;
  flex: 1;
  gap: 0;
  overflow: hidden;
}

/* === CARDS === */
.card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 16px;
}

/* === LIVE DOT === */
.live-dot {
  display: inline-block;
  width: 8px; height: 8px;
  background: var(--red);
  border-radius: 50%;
  animation: blink 1.2s infinite;
}
@keyframes blink {
  0%, 100% { opacity: 1; }
  50%       { opacity: 0.2; }
}

/* === ANOMALY PULSE === */
.anomaly-active {
  border-color: var(--red) !important;
  animation: pulse-border 2s infinite;
}
@keyframes pulse-border {
  0%, 100% { box-shadow: 0 0 0 0   rgba(248, 81, 73, 0.4); }
  50%       { box-shadow: 0 0 0 8px rgba(248, 81, 73, 0); }
}

/* === EVENT TICKER === */
.ticker-item {
  padding: 8px 12px;
  border-bottom: 1px solid var(--border);
  display: flex;
  align-items: center;
  gap: 10px;
  animation: slide-in 0.35s ease;
  font-size: 13px;
}
@keyframes slide-in {
  from { transform: translateY(-32px); opacity: 0; }
  to   { transform: translateY(0);     opacity: 1; }
}

/* === VEHICLE STATUS COLORS === */
.status-green  { color: var(--green); }
.status-yellow { color: var(--yellow); }
.status-red    { color: var(--red); }

/* === DETAIL DRAWER === */
.detail-drawer {
  position: fixed;
  right: -400px;
  top: 0; bottom: 0;
  width: 400px;
  background: var(--bg-secondary);
  border-left: 1px solid var(--border);
  transition: right 0.3s ease;
  z-index: 100;
  overflow-y: auto;
  padding: 24px;
}
.detail-drawer.open { right: 0; }

/* === ACTION BUTTONS === */
.btn {
  padding: 8px 16px;
  border-radius: 6px;
  border: none;
  cursor: pointer;
  font-size: 13px;
  font-weight: 500;
  transition: opacity 0.2s;
}
.btn:hover      { opacity: 0.8; }
.btn-red        { background: var(--red);    color: white; }
.btn-yellow     { background: var(--yellow); color: #000;  }
.btn-outline    { background: transparent;   color: var(--text-primary);
                  border: 1px solid var(--border); }

/* === WAVEFORM ANIMATION === */
.waveform { display: flex; align-items: center; gap: 3px; height: 32px; }
.waveform-bar {
  width: 3px;
  background: var(--blue);
  border-radius: 2px;
  animation: wave 1.2s ease-in-out infinite;
}
.waveform-bar:nth-child(2) { animation-delay: 0.1s; }
.waveform-bar:nth-child(3) { animation-delay: 0.2s; }
/* add 8-10 bars total */
@keyframes wave {
  0%, 100% { height: 6px; }
  50%       { height: 28px; }
}
```

### 6d. Google Maps Integration

In `addin/js/map.js`:

```javascript
const DARK_MAP_STYLE = [
  { elementType: "geometry",
    stylers: [{ color: "#1a1a2e" }] },
  { elementType: "labels.text.fill",
    stylers: [{ color: "#8ec3b9" }] },
  { featureType: "road", elementType: "geometry",
    stylers: [{ color: "#304a7d" }] },
  { featureType: "water", elementType: "geometry",
    stylers: [{ color: "#0e1626" }] },
  { featureType: "poi",
    stylers: [{ visibility: "off" }] }
];

class FleetMap {
  
  init(elementId) { /* Initialize dark-mode Google Map */ }

  plotVehicles(vehicles) {
    /* For each vehicle:
       - Determine color from deviation_score:
         score > 70 → red (#F85149)
         score > 40 → yellow (#D29922)  
         else       → green (#3FB950)
       - Draw directional arrow marker (rotated by vehicle.bearing)
       - On click → open detail drawer with driver info + radar chart
    */
  }

  addHeatmapLayer(exceptionEvents) {
    /* Plot harsh braking + speeding events as heatmap
       Use google.maps.visualization.HeatmapLayer
       Gradient: transparent → yellow → red
    */
  }

  addTripTrail(tripCoordinates, vehicleId) {
    /* Draw polyline for today's route
       Color: blue (#388BFD), opacity 0.7, weight 3
    */
  }

  fitBoundsToFleet() { /* Auto-zoom to show all vehicles */ }

  highlightAnomaly(vehicleId) {
    /* Make the anomalous vehicle marker pulse with red ring
       Use a custom overlay or animated circle
    */
  }

  startLiveUpdates() {
    /* Poll /api/live-positions every 10 seconds
       Smoothly animate markers to new positions using
       requestAnimationFrame interpolation
    */
  }
}
```

### 6e. Sportscaster Engine

In `addin/js/sportscaster.js`:

```javascript
class Sportscaster {

  constructor() {
    this.lastEventVersion = null;
    this.isSpeaking = false;
    this.eventQueue = [];
  }

  async startBroadcast() {
    /* Poll /api/live-events every 60 seconds
       For new events, call generateCommentary(events)
       Play audio, update ticker, update anomaly panel
    */
  }

  async generateCommentary(newEvents) {
    /* POST to your backend which calls Gemini Flash with:
    
       SYSTEM PROMPT FOR GEMINI (send this to your backend):
       You are an energetic but professional fleet safety sportscaster.
       Rules:
       - Voice: like ESPN radio, but for fleet operations
       - Celebrate good driving: "Marcus is having an absolute clinic today"
       - Flag concerns with urgency: "that's the third harsh brake this morning"
       - Mention specific vehicle numbers and driver names
       - When FleetDNA flags an anomaly, note it: "FleetDNA is flagging this
         as 87% unlike Driver 8's normal Thursday pattern — worth checking on"
       - Keep each commentary update to 3-4 sentences max
       - Transition naturally from vehicle to vehicle like covering multiple games
       - Never use corporate/robotic language. You're having fun with this.
       
       Return ONLY the spoken text, no formatting.
    */
  }

  async speak(text) {
    /* Call Google Cloud TTS API with:
       voice: en-US-Neural2-J (energetic male sports voice)
       speaking_rate: 1.1 (slightly fast = energy)
       pitch: 0.5 (slightly higher = enthusiasm)
       
       Play via HTML5 Audio, show waveform animation while playing
       Show text in #current-commentary div simultaneously
    */
  }

  addToTicker(event) {
    /* Create a ticker item:
       [timestamp] [colored dot] [vehicle #] [event type] [driver name]
       Prepend to #event-ticker list
       Remove items older than 20
    */
  }
}
```

### 6f. Backend API Endpoints

Create a simple `server.js` (Node.js / Express) or `server.py` (FastAPI)
that the Add-In calls:

```
GET  /api/live-positions   → calls geotab_client.get_live_positions()
                             + FleetDNA.rank_fleet() for today
                             Returns: [{id, name, lat, lng, bearing, speed,
                                        deviation_score, anomaly_type}]

GET  /api/live-events      → calls geotab_client.get_live_events(from_version)
                             Returns: {events: [...], next_version: "..."}

GET  /api/driver/:id       → full driver DNA + weekly delta
                             Returns: {baseline, today_score, weekly_delta}

GET  /api/anomalies        → all drivers with deviation_score > 60
                             Returns: [{driver_id, name, score, type, details}]

POST /api/generate-commentary → body: {events: [...]}
                                 calls Gemini Flash, returns {text: "..."}

POST /api/write-back/group → body: {name, vehicle_ids}
                              calls geotab_client.create_group()
                              Returns: {group_id, success}
```

Host this on Google Firebase (Path: `firebase deploy`) or any free host.

---

## STEP 7 — Frequency 3: Executive Podcast (NotebookLM Pipeline)
**Goal:** Every Monday, a 5-minute two-host podcast about the fleet's week.

In `frequencies/exec_podcast.py`:

```python
def generate_podcast_script(week_data):
    """
    Call Gemini Pro (not Flash — we need the deeper reasoning) with:
    
    SYSTEM PROMPT:
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
    
    INPUT DATA:
    {week_data}  ← JSON with all fleet KPIs, anomalies, events, rankings
    
    Return ONLY the formatted script.
    """

def generate_podcast_audio(script_text):
    """
    1. Save script to a temp .txt file
    2. Upload to NotebookLM via browser automation (Playwright/Selenium)
       OR: Use Gemini's audio generation if NotebookLM API not available
       FALLBACK: Use Google Cloud TTS with two different voices:
         - Alex voice: en-US-Neural2-J (male, confident)  
         - Jamie voice: en-US-Neural2-F (female, analytical)
         Parse script line by line, alternate voices, concatenate audio
    3. Return: .mp3 file path
    """

def publish_to_sites(episode_number, audio_path, script, week_summary):
    """
    Update Google Sites podcast page:
    - Add new episode card at top: Episode #, date, 3-sentence summary
    - Embed audio player
    - Link to full script (Google Drive)
    - Update episode archive list
    
    Update Google Sheets "Fleet Intelligence Dashboard":
    - New row: week, key metrics, links to audio + script
    - Gemini-generated one-paragraph executive summary in Column A
    """

def run_monday_podcast():
    """
    Main Monday 5 AM function:
    1. Pull last 7 days of data via Data Connector OData
    2. Pull anomaly log from DuckDB
    3. Pull weekly driver rankings
    4. Gemini Pro → podcast script
    5. Generate audio (NotebookLM or TTS fallback)
    6. Publish to Google Sites + Google Sheets
    7. Send email to exec list with: episode player link + 3-bullet summary
    """
```

Create a test run: generate one podcast episode from demo database data.
Share the script and a sample audio clip.

---

## STEP 8 — Scheduler (Automate Everything)
**Goal:** The entire system runs itself with no human intervention.

In `scheduler/cron_jobs.py`:

```python
from apscheduler.schedulers.background import BackgroundScheduler

scheduler = BackgroundScheduler()

# Every 60 seconds: refresh live data for manager dashboard
scheduler.add_job(
    func=refresh_live_data,   # → update DuckDB cache with latest positions + events
    trigger='interval',
    seconds=60,
    id='live_refresh'
)

# Every day at 6:30 AM: manager morning email
scheduler.add_job(
    func=send_manager_email,  # → Gemini causality brief → Gmail API
    trigger='cron',
    hour=6, minute=30,
    id='manager_brief'
)

# Every Friday at 5 PM: driver feed
scheduler.add_job(
    func=run_friday_driver_feed,  # → audio + email for all drivers
    trigger='cron',
    day_of_week='fri',
    hour=17, minute=0,
    id='driver_feed'
)

# Every Monday at 5 AM: executive podcast
scheduler.add_job(
    func=run_monday_podcast,  # → script + audio + Sites publish
    trigger='cron',
    day_of_week='mon',
    hour=5, minute=0,
    id='exec_podcast'
)

scheduler.start()
```

Also generate an `n8n_workflow.json` export that replicates these 4 schedules
using n8n (visual workflow) as an alternative. Reference
`./geotab-vibe-guide/guides/AGENTIC_QUICKSTART_N8N.md` for the n8n pattern.

---

## STEP 9 — Write-Back Automation (The 10% That Wins Prizes)
**Goal:** Every frequency triggers live changes in Geotab.

Build `writeback_manager.py` that centralizes all write-backs:

```python
class WritebackManager:

    def after_morning_analysis(self, analysis_results):
        """ Called after daily Gemini analysis:
            - Vehicles with active critical faults → Group "Needs Attention {date}"
            - Drivers with deviation_score > 80 → Group "Welfare Check {date}"
        """

    def after_driver_feed(self, weekly_rankings):
        """ Called after Friday driver processing:
            - Top 5 drivers → Group "Week {N} Champions"
            - Bottom 3 drivers (below their own baseline) → Rule "Coaching Triggered"
            - Any driver 2+ std devs from baseline → Group "Welfare Check Week {N}"
        """

    def after_exec_podcast(self, week_summary):
        """ Called after Monday podcast:
            - Archive last week's groups (rename with [ARCHIVED] prefix)
            - Create fresh groups for new week
        """

    def on_welfare_flag(self, driver_id, reason):
        """ Immediate write-back when sportscaster or FleetDNA flags someone:
            - Add.Group("Welfare Check {today}", [vehicle_id])
            - Log in DuckDB
            - Send Slack/email notification to manager immediately
        """
```

---

## STEP 10 — Demo Prep
**Goal:** Record a 3-minute video demo that wins prizes.

### Generate Demo Assets

1. **3 driver audio clips** from demo database:
   - Clip 1: Top performer — warm, specific praise
   - Clip 2: Struggling driver — constructive, specific coaching
   - Clip 3: Anomaly driver — concerned, welfare-check tone

2. **1 complete executive podcast episode** (5 min):
   - Full two-host dialogue
   - Uses real demo database vehicle numbers and patterns

3. **Live dashboard screenshot sequence**:
   - Dashboard on load with all vehicles on dark map
   - One vehicle clicked → detail drawer open with radar chart
   - Anomaly panel pulsing red with a flagged driver
   - Ticker showing 5 real events

4. **MCP reasoning chain log**:
   - Save full Claude Desktop conversation showing tool call chains
   - Export as clean screenshot for README

### Demo Script (3 minutes exactly)

```
00:00–00:10  [BLACK SCREEN] 
             Sportscaster audio plays. No narration. Let it run.
             "Vehicle 7 is flying down I-95 — smooth as silk..."

00:10–00:35  [CUT TO DASHBOARD]
             "This is your fleet. Right now. It's talking."
             Show live map with colored markers.
             Point to red marker: "This vehicle is 94% unlike itself today."

00:35–01:05  [SHOW ANOMALY PANEL]
             Click on anomalous vehicle → detail drawer opens.
             Show radar chart: today (red) vs their normal (teal).
             "This isn't a speeding alert. This driver isn't breaking any rules.
              FleetDNA noticed they're behaving completely unlike themselves.
              That could mean stress, a family emergency, or a medical issue."
             Click "Welfare Check" → watch Geotab Group created live.

01:05–01:35  [SWITCH TO DRIVER EMAIL]
             "Every Friday, each driver gets this in their inbox."
             Show email: personalized stats, colored metric bars.
             Click play on Marcus's audio clip. Let 30 seconds play.
             "Named. Specific. Compared to his own 90-day normal.
              Not a fleet rule. Not a generic warning. A coaching conversation."

01:35–02:05  [SWITCH TO PODCAST PAGE]
             "And every Monday, this lands in the executive inbox."
             Press play on podcast. Let 30 seconds of two-host dialogue play.
             "Alex and Jamie discuss your fleet like sports analysts.
              Same data. Their format. Their commute."

02:05–02:30  [SWITCH TO CLAUDE DESKTOP / MCP]
             Type: "Which driver is most unlike themselves this week?"
             Watch tool calls chain: build_dna → score_today → rank → narrate
             "One question. Five API calls. The answer. 
              This is the brain behind every broadcast."

02:30–02:50  [FLASH STATS]
             "10 Google products. 3 personalized feeds. 
              Live write-back to Geotab. Automated. Every week."
             Flash the product list fast.

02:50–03:00  [LOGO CARD]
             "One fleet brain. Every stakeholder, their own signal.
              GEOPulse."
```

---

## STEP 11 — GitHub README
**Goal:** Write a README that judges read before watching the video.

Write a `README.md` that includes:

1. **One-paragraph pitch** (what it does, why it matters, who it's for)
2. **Architecture diagram** (ASCII art showing Brain → 3 Frequencies)
3. **All Gemini prompts used** — every single one, verbatim
4. **All Geotab API calls** — typeName, filters, what they return
5. **Google products used** — table with product + exact role
6. **How to run it** — step by step from scratch
7. **Demo video link** at the top
8. **Screenshots** of dashboard, driver email, podcast player page
9. **Write-back demonstration** — screenshots of Groups created in MyGeotab

---

## FINAL CHECKLIST (Before Submission)

Before recording the demo, confirm ALL of these work:

- [ ] Geotab auth works with demo database
- [ ] `DeviceStatusInfo` returns live vehicle positions
- [ ] Vehicles plot on dark Google Maps with correct colors
- [ ] Colors change based on FleetDNA deviation score
- [ ] Sportscaster generates new audio commentary every 60 seconds
- [ ] Event ticker updates with new events
- [ ] Anomaly panel shows drivers flagged by FleetDNA
- [ ] Clicking a vehicle opens detail drawer with radar chart
- [ ] "Welfare Check" button creates a Group in MyGeotab (LIVE)
- [ ] Driver email generates with personalized stats + audio
- [ ] Audio clip is warm, specific, mentions driver by name
- [ ] Executive podcast script has two distinct host voices
- [ ] Podcast is published to a publicly accessible URL
- [ ] MCP server chains 3+ tool calls for complex queries
- [ ] At least 3 write-backs demonstrated (Groups + Rules)
- [ ] All 10 Google products are visibly used somewhere
- [ ] Scheduler is configured for all 4 automated jobs
- [ ] README has every prompt verbatim
- [ ] Demo video is exactly 3 minutes

---

## PRIZE TARGETING SUMMARY

| Prize | What Judges Score | Your Winning Element |
|---|---|---|
| 🤖 **Innovator $5K** | Technical AI creativity | FleetDNA personal baselines + visible MCP reasoning chains |
| 💥 **Disruptor $2.5K** | Most surprising idea | Live sportscaster audio — nobody else submits audio |
| 🔵 **Google Tools $2.5K** | Best use of Google products | 10 products, NotebookLM podcast, Gemini causality reasoning |
| 🤝 **Collaborative $2.5K** | Community activity | Post daily progress on r/geotab + share prompts on GitHub |

**Total target: $12,500**

---

*Now start with Step 1. Read the geotab-vibe-guide folder first.
Build one step at a time. Show me output after each step before proceeding.**   **📈 Real-Time Market Data**: Connects directly to **Yahoo Finance** and **Binance** (WebSocket) to stream live prices. No staleness here.
*   **🧠 12-Agent Swarm**: From `Technical Analyst` to `Risk Manager`, specialized agents debate every trade. One agent wants to buy? The Risk agent checks the volatility first.
*   **� Multi-Channel Global Notifications**: Never miss a beat. The system pushes alerts to where you actually live:
    *   **Slack & Discord**: Get trade confirmations, price spikes, and agent debates in your channels.
    *   **SMS & WhatsApp**: Urgent margin calls or crash alerts sent directly to your phone.
    *   **Email**: Daily portfolio summaries and audit reports.
*   **�🛡️ Automated Risk Guardrails**: The Risk Server enforces position limits (max 5%) and stop-losses automatically. It rejects trades that violate your safety policy.
*   **⚖️ Smart Strategy Manager**: Automatically allocates capital **40% to long-term investing** and **60% to active trading**, and auto-rebalances when drift exceeds 5%.
*   **💬 Natural Language Interface**: improved `copilot` CLI integration lets you "chat" with your portfolio. "Hey, sell half my Bitcoin if RSI > 80."
*   **� Comprehensive Analysis**:
    *   **Technical**: RSI, MACD, Bollinger Bands on live data.
    *   **Fundamental**: P/E, ROE, Growth metrics.
    *   **Sentiment**: Analyzes news headlines to gauge market mood.
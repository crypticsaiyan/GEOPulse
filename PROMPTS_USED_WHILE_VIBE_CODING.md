# GEOPulse — Prompts Used While Vibe Coding

This file centralizes the prompts used during GEOPulse development, based on:
- `PLAN.md` (build-time orchestration prompt)
- `README.md` (runtime generation prompts used by the app)
- `geotab-vibe-guide` references used during implementation

Use this as the judge-facing prompt artifact for reproducibility.

---

## 1) Master Build Prompt (used to scaffold GEOPulse)

> Source: `PLAN.md`

```text
You are building GEOPulse — a Geotab Hackathon submission targeting
three prize categories simultaneously: The Innovator ($5K), The Disruptor ($2.5K),
and Best Use of Google Tools ($2.5K).

Before writing any code, read:
1. ./geotab-vibe-guide/AGENT_SUMMARY.md
2. ./geotab-vibe-guide/GEOTAB_OVERVIEW.md
3. ./geotab-vibe-guide/VIBE_CODING_CONTEXT.md
4. ./geotab-vibe-guide/guides/HACKATHON_IDEAS.md
5. ./geotab-vibe-guide/guides/DATA_CONNECTOR.md
6. ./geotab-vibe-guide/guides/GEOTAB_ADDINS.md
7. ./geotab-vibe-guide/examples/
8. ./geotab-vibe-guide/skills/

Use those files as primary reference for API patterns. Do not guess API methods.

Build step by step and complete each step before moving on:
- Geotab client + auth
- Data pipeline functions
- FleetDNA baseline and anomaly scoring
- MCP server tools
- Add-In dashboard
- Driver/manager/executive frequencies
- Scheduler and demo prep
```

---

## 2) Build Iteration Prompts (used while coding)

These were repeatedly used to drive feature implementation and fixes.

### 2.1 Geotab client implementation prompt

```text
Implement geotab_client.py using Geotab JSON-RPC patterns from geotab-vibe-guide.
Requirements:
- Read credentials from .env (never hardcode)
- Authenticate once, reuse credentials
- Add call(method, params) wrapper
- Implement: get_live_positions, get_live_events, get_driver_trips,
  get_driver_exceptions, get_active_faults, get_all_drivers,
  create_group, create_rule, get_kpi_data
- Add caching where appropriate
- Include robust handling for demo database quirks
```

### 2.2 FleetDNA behavior-scoring prompt

```text
Build FleetDNA to compare today's behavior against each entity's 90-day baseline.
Use z-scores per metric, combine into 0-100 deviation score,
and return anomaly type + confidence + plain-English narrative.
Fallback gracefully to per-device analysis when demo DB lacks real drivers.
```

### 2.3 Dashboard integration prompt

```text
Build a dark live operations dashboard that polls FastAPI endpoints,
renders vehicle markers on map, shows event ticker, anomaly panel,
detail drawer, and triggers one-click welfare-check write-back.
Prioritize smooth updates and clear anomaly visibility.
```

### 2.4 MCP toolchain prompt

```text
Expose MCP tools for fleet reasoning:
overview, driver DNA, anomaly ranking, fuel/fault/safety analysis,
SQL analytics query, write-back actions, and narrative generation.
Tools must be composable so one user question can chain multiple calls.
```

### 2.5 Demo-prep prompt

```text
Prepare a 3-minute demo with this sequence:
dashboard live map -> anomaly deep dive -> welfare write-back ->
driver audio/email -> executive podcast -> MCP tool chain -> closing card.
Keep claims tied to real demo database outputs.
```

---

## 3) Runtime LLM Prompts (used by GEOPulse features)

> Source: `README.md` section “AI Prompts (Verbatim)”

### 3.1 Driver Coach (Frequency 1)

```text
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

### 3.2 Sportscaster Commentary (Frequency 2)

```text
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

### 3.3 Manager Morning Brief (Frequency 2b)

```text
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

### 3.4 Executive Podcast (Frequency 3)

```text
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

### 3.5 Audience Narrative prompts (MCP tool)

```text
- driver:    "You are a supportive fleet coach. Be warm, specific, encouraging."
- manager:   "You are a fleet operations analyst. Be data-driven, concise, actionable."
- executive: "You are a fleet strategy advisor. Focus on trends, costs, risks."
```

---

## 4) Suggested Prompting Pattern for Future Iterations

```text
Context
- Project: GEOPulse
- Data source: Geotab demo database via authenticated JSON-RPC
- Constraint: never hardcode credentials; use .env

Task
- [single concrete feature]

Acceptance Criteria
- [3-5 testable bullets]

Output
- code changes only in listed files
- short validation steps
```

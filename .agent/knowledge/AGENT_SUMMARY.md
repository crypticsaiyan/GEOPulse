# GEOPulse — Agent Summary

## What is GEOPulse?

**GEOPulse** is a Geotab Hackathon submission targeting three prize categories:
The Innovator ($5K), The Disruptor ($2.5K), and Best Use of Google Tools ($2.5K).

**Tagline:** One Fleet Brain. Every Stakeholder Gets Their Own Signal.

## Architecture

One AI brain (MCP server) reads fleet data from Geotab, performs behavioral
fingerprinting per driver via FleetDNA, and broadcasts three personalized streams:

| Frequency | Audience   | Output                        | Schedule      |
|-----------|------------|-------------------------------|---------------|
| 1         | Drivers    | Personal audio clip + email   | Friday 5 PM   |
| 2         | Managers   | Live sportscaster dashboard   | Real-time     |
| 3         | Executives | Two-host podcast              | Monday 5 AM   |

## Key Components

- `mcp/` — MCP server (10 tools), Geotab client, FleetDNA engine, DuckDB cache
- `addin/` — MyGeotab Add-In dashboard (dark map, sportscaster, ticker)
- `frequencies/` — Driver feed, manager email, executive podcast pipelines
- `scheduler/` — APScheduler cron jobs for all automated triggers
- `server/` — FastAPI backend API for Add-In

## Tech Stack

- **Geotab API** — Fleet data, write-back (Groups, Rules)
- **Google Gemini** — AI narrative generation (Flash + Pro)
- **Google Cloud TTS** — Audio generation
- **Google Maps** — Dark-mode vehicle map
- **DuckDB** — Local analytics cache
- **MCP** — AI tool protocol for Claude Desktop
- **FastAPI** — REST API server

## Entry Points

| Task | Start Here |
|------|-----------|
| Full build plan | `PLAN.md` |
| Add credentials | `.env` (copy from `.env.example`) |
| Test connections | `python tests/test_connection.py` |
| Geotab API patterns | `.agent/skills/geotab-docs/SKILL.md` |

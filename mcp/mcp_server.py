"""
GEOPulse MCP Server — The Reasoning Core

Exposes 10 MCP tools for fleet intelligence:
1. get_fleet_overview - Live positions + deviation scores
2. get_driver_dna - Full baseline + today's score + weekly delta
3. find_anomalous_drivers - Drivers above deviation threshold
4. get_fuel_analysis - Fuel consumption ranked by driver/vehicle
5. get_fault_report - Active faults with severity + pattern match
6. get_safety_events - Exception events grouped by driver
7. query_fleet_data - Natural language → SQL against DuckDB
8. create_group - Write-back: create group in Geotab
9. create_coaching_rule - Write-back: create exception rule
10. generate_fleet_narrative - Gemini-powered plain-English insights
"""

# TODO: Implement MCP server using the `mcp` Python library
# Reference: ../geotab-vibe-guide/skills/geotab-custom-mcp/SKILL.md

"""
GEOPulse MCP Server — The AI Reasoning Core

Exposes 10 MCP tools that let Claude (or any MCP client) query and
act on Geotab fleet data through the FleetDNA behavioral engine.

Tools:
    1. get_fleet_overview — vehicles + positions + deviation scores
    2. get_driver_dna — full baseline + today's score + weekly delta
    3. find_anomalous_drivers — drivers above deviation threshold
    4. get_fuel_analysis — fuel/distance rankings
    5. get_safety_events — exception events grouped by driver
    7. query_fleet_data — raw SQL on DuckDB cache
    8. create_group — write-back: create Geotab group
    9. create_coaching_rule — write-back: create coaching rule
   10. generate_fleet_narrative — LLM narrative from data

Run: python -m core.mcp_server
"""

import json
import asyncio
import logging
from datetime import date

# pip's mcp library is now directly importable (no naming collision)
from mcp.server import Server as MCPServer
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.duckdb_cache import DuckDBCache
from core.geotab_client import GeotabClient
from core.fleetdna import FleetDNA
from core.llm_provider import LLMProvider

logger = logging.getLogger(__name__)

# Initialize all components
cache = DuckDBCache(db_path="geopulse.db")
cache.initialize()
geotab = GeotabClient(db_cache=cache)
dna = FleetDNA(geotab, cache)
llm = LLMProvider(db_cache=cache)

server = MCPServer("geopulse")


@server.list_tools()
async def list_tools():
    return [
        Tool(
            name="get_fleet_overview",
            description="Returns all vehicles with live positions and FleetDNA deviation scores. "
                        "Use for: 'What's happening in the fleet right now?'",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        Tool(
            name="get_driver_dna",
            description="Returns full baseline profile + today's deviation score + weekly delta for a driver/vehicle. "
                        "Use for: 'Is Driver X behaving normally?'",
            inputSchema={
                "type": "object",
                "properties": {"entity_name_or_id": {"type": "string", "description": "Driver name or vehicle ID"}},
                "required": ["entity_name_or_id"],
            },
        ),
        Tool(
            name="find_anomalous_drivers",
            description="Returns all drivers/vehicles above a deviation threshold, ranked. "
                        "Use for: 'Who is acting unlike themselves today?'",
            inputSchema={
                "type": "object",
                "properties": {"threshold": {"type": "integer", "default": 70, "description": "Deviation threshold 0-100"}},
                "required": [],
            },
        ),
        Tool(
            name="get_fuel_analysis",
            description="Returns fuel/distance consumption ranked by driver/vehicle with idle time correlation. "
                        "Use for: 'Who is burning the most fuel and why?'",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        Tool(
            name="get_safety_events",
            description="Returns exception events grouped by driver for the last N hours. "
                        "Use for: 'What safety events happened today?'",
            inputSchema={
                "type": "object",
                "properties": {"hours_back": {"type": "integer", "default": 24}},
                "required": [],
            },
        ),
        Tool(
            name="query_fleet_data",
            description="Execute a SQL query against the DuckDB fleet analytics cache. "
                        "Tables: driver_baselines, trip_cache, anomaly_log, fleet_rankings. "
                        "Use for: analytical questions needing custom data slicing.",
            inputSchema={
                "type": "object",
                "properties": {"sql_query": {"type": "string", "description": "SQL query to run"}},
                "required": ["sql_query"],
            },
        ),
        Tool(
            name="create_group",
            description="WRITE-BACK: Create a group in Geotab and assign vehicles. "
                        "Use for: 'Flag these drivers for coaching'",
            inputSchema={
                "type": "object",
                "properties": {
                    "group_name": {"type": "string"},
                    "vehicle_ids": {"type": "array", "items": {"type": "string"}},
                    "reason": {"type": "string"},
                },
                "required": ["group_name"],
            },
        ),
        Tool(
            name="create_coaching_rule",
            description="WRITE-BACK: Create a coaching alert rule in Geotab. "
                        "Use for: 'Set up alerts for harsh braking on Driver X'",
            inputSchema={
                "type": "object",
                "properties": {
                    "driver_id": {"type": "string"},
                    "rule_type": {
                        "type": "string",
                        "enum": ["harsh_braking", "speeding", "idle", "welfare"],
                    },
                },
                "required": ["driver_id", "rule_type"],
            },
        ),
        Tool(
            name="generate_fleet_narrative",
            description="Generate a plain-English narrative from fleet data for a specific audience. "
                        "Use for: converting raw numbers into human-readable insights.",
            inputSchema={
                "type": "object",
                "properties": {
                    "data_summary": {"type": "string", "description": "JSON data to narrate"},
                    "audience": {
                        "type": "string",
                        "enum": ["driver", "manager", "executive"],
                    },
                },
                "required": ["data_summary", "audience"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict):
    try:
        if name == "get_fleet_overview":
            return await _get_fleet_overview()
        elif name == "get_driver_dna":
            return await _get_driver_dna(arguments.get("entity_name_or_id", ""))
        elif name == "find_anomalous_drivers":
            return await _find_anomalous(arguments.get("threshold", 70))
        elif name == "get_fuel_analysis":
            return await _get_fuel_analysis()
        elif name == "get_safety_events":
            return await _get_safety_events(arguments.get("hours_back", 24))
        elif name == "query_fleet_data":
            return await _query_fleet_data(arguments.get("sql_query", ""))
        elif name == "create_group":
            return await _create_group(
                arguments.get("group_name", ""),
                arguments.get("vehicle_ids", []),
                arguments.get("reason", ""),
            )
        elif name == "create_coaching_rule":
            return await _create_coaching_rule(
                arguments.get("driver_id", ""),
                arguments.get("rule_type", "harsh_braking"),
            )
        elif name == "generate_fleet_narrative":
            return await _generate_narrative(
                arguments.get("data_summary", ""),
                arguments.get("audience", "manager"),
            )
        else:
            return [TextContent(type="text", text=f"Unknown tool: {name}")]
    except Exception as e:
        return [TextContent(type="text", text=f"Error: {str(e)}")]


# === Tool Implementations ===

async def _get_fleet_overview():
    positions = geotab.get_live_positions()
    rankings = dna.rank_fleet()
    rank_map = {r["entity_id"]: r for r in rankings}

    overview = []
    for p in positions:
        rank_info = rank_map.get(p["device_id"], {})
        overview.append({
            **p,
            "deviation_score": rank_info.get("deviation_score", 0),
            "anomaly_type": rank_info.get("anomaly_type", "none"),
        })

    return [TextContent(type="text", text=json.dumps({
        "total_vehicles": len(positions),
        "anomalies": sum(1 for o in overview if o["deviation_score"] > 70),
        "vehicles": overview,
    }, indent=2))]


async def _get_driver_dna(entity_name_or_id):
    # Try to find by name or ID
    entities = dna.get_entities()
    entity = None
    for e in entities:
        if e["id"] == entity_name_or_id or entity_name_or_id.lower() in e["name"].lower():
            entity = e
            break

    if not entity:
        return [TextContent(type="text", text=f"Entity not found: {entity_name_or_id}")]

    baseline = dna.build_baseline(entity["id"])
    today_score = dna.score_today(entity["id"])
    weekly = dna.get_weekly_delta(entity["id"])

    return [TextContent(type="text", text=json.dumps({
        "entity": entity,
        "baseline": baseline,
        "today_score": today_score,
        "weekly_delta": weekly,
    }, indent=2, default=str))]


async def _find_anomalous(threshold):
    rankings = dna.rank_fleet()
    anomalous = [r for r in rankings if r["deviation_score"] >= threshold]
    return [TextContent(type="text", text=json.dumps({
        "threshold": threshold,
        "total_checked": len(rankings),
        "anomalous_count": len(anomalous),
        "entities": anomalous,
    }, indent=2))]


async def _get_fuel_analysis():
    entities = dna.get_entities()
    fuel_data = []
    for entity in entities[:20]:  # Limit to avoid API overload
        trips = dna._get_trips_for_entity(entity["id"], days_back=7)
        if trips:
            total_dist = sum(t.get("distance", 0) for t in trips)
            total_idle = sum(t.get("idle_duration_seconds", 0) for t in trips)
            total_dur = sum(t.get("duration_seconds", 0) for t in trips)
            fuel_data.append({
                "name": entity["name"],
                "entity_id": entity["id"],
                "total_distance_km": round(total_dist, 1),
                "total_idle_seconds": round(total_idle),
                "idle_ratio": round(total_idle / max(total_dur, 1), 3),
                "trips": len(trips),
            })

    fuel_data.sort(key=lambda x: x["total_distance_km"], reverse=True)
    return [TextContent(type="text", text=json.dumps({
        "period": "last 7 days",
        "vehicles": fuel_data,
    }, indent=2))]


async def _get_safety_events(hours_back):
    events_result = geotab.get_live_events()
    events = events_result.get("events", [])

    # Group by driver/device
    from collections import defaultdict
    grouped = defaultdict(list)
    for e in events:
        key = e.get("driver_name", "Unknown") or e.get("device_name", "Unknown")
        grouped[key].append(e)

    return [TextContent(type="text", text=json.dumps({
        "hours_back": hours_back,
        "total_events": len(events),
        "by_driver": {k: v for k, v in sorted(grouped.items(), key=lambda x: -len(x[1]))},
    }, indent=2, default=str))]


async def _query_fleet_data(sql_query):
    # Safety: only allow SELECT queries
    if not sql_query.strip().upper().startswith("SELECT"):
        return [TextContent(type="text", text="Only SELECT queries are allowed.")]

    try:
        results = cache.execute_sql(sql_query)
        return [TextContent(type="text", text=json.dumps({
            "query": sql_query,
            "row_count": len(results),
            "results": [list(r) for r in results[:100]],
        }, indent=2, default=str))]
    except Exception as e:
        return [TextContent(type="text", text=f"SQL error: {str(e)}")]


async def _create_group(group_name, vehicle_ids, reason):
    group_id = geotab.create_group(group_name, vehicle_ids)
    return [TextContent(type="text", text=json.dumps({
        "success": True,
        "group_id": group_id,
        "group_name": group_name,
        "vehicles_assigned": len(vehicle_ids or []),
        "reason": reason,
    }, indent=2))]


async def _create_coaching_rule(driver_id, rule_type):
    rule_name = f"GEOPulse Coaching: {rule_type} — {driver_id}"
    rule_id = geotab.create_rule(rule_name, rule_type, driver_id)
    return [TextContent(type="text", text=json.dumps({
        "success": rule_id is not None,
        "rule_id": rule_id,
        "rule_name": rule_name,
        "rule_type": rule_type,
    }, indent=2))]


async def _generate_narrative(data_summary, audience):
    prompts = {
        "driver": "You are a warm, encouraging fleet safety coach. Summarize this data personally.",
        "manager": "You are a professional fleet operations analyst. Provide actionable insights.",
        "executive": "You are a strategic fleet advisor. Focus on trends, costs, and business impact.",
    }
    system_prompt = prompts.get(audience, prompts["manager"])

    narrative = llm.generate_cached(
        prompt=f"Generate a brief narrative from this fleet data:\n{data_summary}",
        system_prompt=system_prompt,
        cache_key=f"narrative_{audience}_{hash(data_summary) % 100000}",
        ttl_seconds=1800,
    )
    return [TextContent(type="text", text=narrative)]


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    print("🎙️ GEOPulse MCP Server")
    print("   Tools: 9")
    print(f"   LLM: {llm.get_info()['provider']} ({llm.get_info()['model']})")
    print(f"   Vehicles: {len(geotab.get_all_devices())}")
    print("")
    print("   To connect to Claude Desktop, add to claude_desktop_config.json:")
    import sys
    python_path = sys.executable
    print(f'   {{"command": "{python_path}", "args": ["-m", "core.mcp_server"]}}')
    print("")
    print("   Starting MCP server on stdio...")
    asyncio.run(main())

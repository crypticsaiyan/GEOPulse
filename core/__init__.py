"""
GEOPulse Core Module — The AI Brain

This package contains:
- mcp_server.py: MCP server exposing 10 fleet intelligence tools
- geotab_client.py: Geotab API wrapper with data-fetching functions
- fleetdna.py: Behavioral fingerprinting engine (FleetDNA)
- duckdb_cache.py: Local DuckDB analytics cache
- llm_provider.py: Unified LLM interface (Gemini + Ollama)

Note: Renamed from mcp/ to core/ to avoid shadowing pip's 'mcp' library.
"""

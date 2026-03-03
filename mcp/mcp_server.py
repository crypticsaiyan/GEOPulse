"""
Compatibility wrapper for legacy module path: mcp.mcp_server

Use either command:
- python -m core.mcp_server   (preferred)
- python -m mcp.mcp_server    (backward-compatible)
"""

from core.mcp_server import *  # re-export server, tools, and main()

if __name__ == "__main__":
    import asyncio
    import sys

    print("🎙️ GEOPulse MCP Server")
    print("   Tools: 9")
    print(f"   LLM: {llm.get_info()['provider']} ({llm.get_info()['model']})")
    print(f"   Vehicles: {len(geotab.get_all_devices())}")
    print("")
    print("   To connect MCP clients, use:")
    python_path = sys.executable
    print(f'   {{"command": "{python_path}", "args": ["-m", "core.mcp_server"]}}')
    print("")
    print("   Starting MCP server on stdio...")
    asyncio.run(main())

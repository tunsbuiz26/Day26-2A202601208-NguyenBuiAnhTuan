"""Smoke test: exercise the server through the MCP stdio protocol."""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


SERVER_DIR = Path(__file__).resolve().parent
REPO_ROOT = SERVER_DIR.parents[1]
SERVER_FILE = SERVER_DIR / "repo_server.py"


async def main() -> None:
    environment = os.environ.copy()
    environment["WORKSPACE_ROOT"] = str(REPO_ROOT)
    environment["MCP_TRANSPORT"] = "stdio"
    params = StdioServerParameters(
        command=sys.executable,
        args=[str(SERVER_FILE)],
        env=environment,
    )

    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            names = {tool.name for tool in tools.tools}
            assert names == {"find_files", "search_in_files"}, names

            files_result = await session.call_tool(
                "find_files", {"name_pattern": "*.py", "max_results": 10}
            )
            files = json.loads(files_result.content[0].text)
            assert any(path.endswith("repo_server.py") for path in files["files"])

            search_result = await session.call_tool(
                "search_in_files",
                {"query": "FastMCP", "file_pattern": "*.py", "max_results": 10},
            )
            matches = json.loads(search_result.content[0].text)
            assert matches["matches"], matches

            limited_result = await session.call_tool(
                "search_in_files",
                {"query": "FastMCP", "file_pattern": "*.py", "max_results": 1},
            )
            limited = json.loads(limited_result.content[0].text)
            assert len(limited["matches"]) == 1
            assert limited["truncated"] is True

            print("MCP smoke test passed")
            print("Discovered tools:", ", ".join(sorted(names)))
            print("find_files matches:", len(files["files"]))
            print("search_in_files matches:", len(matches["matches"]))


if __name__ == "__main__":
    asyncio.run(main())

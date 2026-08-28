"""MCP Client có Authentication — kết nối tới auth_server.py qua HTTP.

Client truyền bearer token thông qua httpx.AsyncClient. MCP SDK tự gắn
token vào mọi request HTTP (POST, GET, DELETE) tới server.

Cách chạy (cần auth_server.py đang chạy ở terminal khác):
    cd 03-production
    # Set MCP_AUTH_TOKEN in both terminals; do not hard-code it in source.
    python auth_server.py            # terminal 1
    python auth_client.py            # terminal 2
"""

from __future__ import annotations

import asyncio
import os

import httpx

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

SERVER_URL = "http://localhost:8000/mcp"
TOKEN = os.environ["MCP_AUTH_TOKEN"]


async def main() -> None:
    http_client = httpx.AsyncClient(
        headers={"Authorization": f"Bearer {TOKEN}"},
    )

    async with http_client:
        async with streamable_http_client(SERVER_URL, http_client=http_client) as (
            read,
            write,
        ):
            async with ClientSession(read, write) as session:
                await session.initialize()

                tools = await session.list_tools()
                print("Tools (có auth):")
                for t in tools.tools:
                    print(f"  - {t.name}: {t.description}")

                result = await session.call_tool("get_weather", {"city": "Hanoi"})
                print(f"\nKết quả: {result.content[0].text}")


if __name__ == "__main__":
    asyncio.run(main())

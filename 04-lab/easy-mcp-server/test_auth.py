"""Integration test for Streamable HTTP authentication."""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


SERVER_DIR = Path(__file__).resolve().parent
REPO_ROOT = SERVER_DIR.parents[1]
SERVER_FILE = SERVER_DIR / "repo_server.py"
PORT = 8765
SERVER_URL = f"http://127.0.0.1:{PORT}/mcp"
VALID_TOKEN = "test-valid-token"
LIMITED_TOKEN = "test-limited-token"

INITIALIZE_REQUEST = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-06-18",
        "capabilities": {},
        "clientInfo": {"name": "repo-helper-auth-test", "version": "1.0"},
    },
}


async def http_status(client: httpx.AsyncClient, token: str | None) -> int:
    headers = {
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
    }
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    response = await client.post(SERVER_URL, headers=headers, json=INITIALIZE_REQUEST)
    return response.status_code


async def wait_until_ready(client: httpx.AsyncClient) -> None:
    for _ in range(50):
        try:
            if await http_status(client, VALID_TOKEN) == 200:
                return
        except httpx.HTTPError:
            pass
        await asyncio.sleep(0.1)
    raise RuntimeError("MCP server did not become ready on port 8765")


async def main() -> None:
    environment = os.environ.copy()
    environment.update(
        {
            "WORKSPACE_ROOT": str(REPO_ROOT),
            "MCP_TRANSPORT": "streamable-http",
            "MCP_AUTH_TOKEN": VALID_TOKEN,
            "MCP_LIMITED_TOKEN": LIMITED_TOKEN,
            "MCP_PUBLIC_URL": f"http://127.0.0.1:{PORT}",
            "PORT": str(PORT),
        }
    )
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        str(SERVER_FILE),
        env=environment,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            await wait_until_ready(client)

            no_token_status = await http_status(client, None)
            wrong_token_status = await http_status(client, "wrong-token")
            limited_token_status = await http_status(client, LIMITED_TOKEN)
            valid_token_status = await http_status(client, VALID_TOKEN)

            assert no_token_status in {401, 403}, no_token_status
            assert wrong_token_status in {401, 403}, wrong_token_status
            assert limited_token_status in {401, 403}, limited_token_status
            assert valid_token_status == 200, valid_token_status

            authenticated_client = httpx.AsyncClient(
                headers={"Authorization": f"Bearer {VALID_TOKEN}"},
                timeout=10.0,
            )
            async with authenticated_client:
                async with streamable_http_client(
                    SERVER_URL, http_client=authenticated_client
                ) as (read, write):
                    async with ClientSession(read, write) as session:
                        await session.initialize()
                        tools = await session.list_tools()
                        tool_names = {tool.name for tool in tools.tools}
                        assert tool_names == {"find_files", "search_in_files"}, tool_names

                        result = await session.call_tool(
                            "find_files", {"name_pattern": "*.md", "max_results": 5}
                        )
                        payload = json.loads(result.content[0].text)
                        assert payload["files"], payload

            print("HTTP auth test passed")
            print(f"No token: {no_token_status}")
            print(f"Wrong token: {wrong_token_status}")
            print(f"Limited token: {limited_token_status}")
            print(f"Valid token: {valid_token_status}")
            print("Authenticated MCP call: passed")
    finally:
        if process.returncode is None:
            process.terminate()
        await process.wait()


if __name__ == "__main__":
    asyncio.run(main())

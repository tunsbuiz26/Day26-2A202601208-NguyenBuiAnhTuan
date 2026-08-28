"""MCP server hỗ trợ tìm kiếm trong một repository local.

Server này biến hai thao tác thủ công thường gặp khi làm việc với repo thành
MCP tools:

* tìm file theo tên/pattern;
* tìm một chuỗi trong nội dung các file.

Mặc định server chạy qua Streamable HTTP để client kết nối qua mạng.
Có thể đặt MCP_TRANSPORT=stdio cho smoke test hoặc môi trường local cũ.
Thư mục được phép đọc được cấu hình bằng biến môi trường WORKSPACE_ROOT.
"""

from __future__ import annotations

import fnmatch
import json
import logging
import os
from pathlib import Path, PurePosixPath
from typing import Iterator

from mcp.server.auth.provider import AccessToken, TokenVerifier
from mcp.server.auth.settings import AuthSettings
from mcp.server.mcpserver import MCPServer


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("repo-helper")

WORKSPACE_ROOT = Path(os.getenv("WORKSPACE_ROOT", os.getcwd())).expanduser().resolve()
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8085"))
TRANSPORT = os.getenv("MCP_TRANSPORT", "streamable-http").lower()
PUBLIC_URL = os.getenv("MCP_PUBLIC_URL", f"http://localhost:{PORT}").rstrip("/")
MAX_RESULTS = 200
MAX_FILE_BYTES = 2 * 1024 * 1024
IGNORED_DIRECTORIES = {
    ".git",
    ".venv",
    "__pycache__",
    "node_modules",
    ".mypy_cache",
    ".pytest_cache",
}

class StaticTokenVerifier(TokenVerifier):
    """Verify demo bearer tokens from environment-backed configuration.

    A production deployment should replace this with JWT validation, OAuth
    introspection, or an identity provider. Tokens are never accepted by the
    tools themselves; the MCP HTTP transport performs this check first.
    """

    async def verify_token(self, token: str) -> AccessToken | None:
        token_info = VALID_TOKENS.get(token)
        if token_info is None:
            return None
        client_id, scopes = token_info
        return AccessToken(token=token, client_id=client_id, scopes=scopes)


AUTH_TOKEN = os.getenv("MCP_AUTH_TOKEN", "repo-dev-token")
LIMITED_TOKEN = os.getenv("MCP_LIMITED_TOKEN", "repo-limited-token")
VALID_TOKENS: dict[str, tuple[str, list[str]]] = {
    AUTH_TOKEN: ("repo-client", ["repo:read"]),
}
if LIMITED_TOKEN != AUTH_TOKEN:
    VALID_TOKENS[LIMITED_TOKEN] = ("limited-client", [])

mcp = MCPServer(
    "repo-helper",
    auth=AuthSettings(
        issuer_url=PUBLIC_URL,
        resource_server_url=PUBLIC_URL,
        required_scopes=["repo:read"],
    ),
    token_verifier=StaticTokenVerifier(),
)


def _validate_root() -> None:
    """Fail clearly when the configured workspace does not exist."""
    if not WORKSPACE_ROOT.is_dir():
        raise ValueError(f"WORKSPACE_ROOT is not a directory: {WORKSPACE_ROOT}")


def _iter_files(include_hidden: bool) -> Iterator[Path]:
    """Yield regular files inside the configured root, safely and predictably."""
    _validate_root()

    for path in WORKSPACE_ROOT.rglob("*"):
        if path.is_symlink() or not path.is_file():
            continue

        relative_parts = path.relative_to(WORKSPACE_ROOT).parts
        if any(part in IGNORED_DIRECTORIES for part in relative_parts):
            continue
        if not include_hidden and any(part.startswith(".") for part in relative_parts):
            continue

        yield path


def _relative_path(path: Path) -> str:
    return path.relative_to(WORKSPACE_ROOT).as_posix()


def _matches(path: Path, pattern: str) -> bool:
    """Match either a filename (``*.py``) or a relative path pattern."""
    relative = _relative_path(path)
    return (
        fnmatch.fnmatchcase(path.name, pattern)
        or fnmatch.fnmatchcase(relative, pattern)
        or PurePosixPath(relative).match(pattern)
    )


def _bounded_limit(value: int) -> int:
    if value < 1:
        raise ValueError("max_results must be at least 1")
    return min(value, MAX_RESULTS)


@mcp.tool()
def find_files(
    name_pattern: str = "*",
    max_results: int = 50,
    include_hidden: bool = False,
) -> str:
    """Find files in the workspace by filename or relative path pattern.

    Args:
        name_pattern: Pattern such as ``*.py``, ``README*`` or
            ``04-lab/**/*.md``.
        max_results: Maximum number of paths to return (1-200).
        include_hidden: Include dotfiles and dot-directories when true.

    Returns:
        JSON containing workspace-relative file paths and a truncation flag.
    """
    pattern = name_pattern.strip()
    if not pattern:
        raise ValueError("name_pattern must not be empty")
    limit = _bounded_limit(max_results)

    matches = sorted(
        (_relative_path(path) for path in _iter_files(include_hidden) if _matches(path, pattern)),
        key=str.casefold,
    )
    result = {
        "workspace": str(WORKSPACE_ROOT),
        "pattern": pattern,
        "files": matches[:limit],
        "truncated": len(matches) > limit,
    }
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
def search_in_files(
    query: str,
    file_pattern: str = "*",
    max_results: int = 50,
    include_hidden: bool = False,
) -> str:
    """Search a text string in real files inside the workspace.

    Args:
        query: Text to search for, case-sensitive.
        file_pattern: Restrict files, for example ``*.py`` or ``*.md``.
        max_results: Maximum number of matching lines to return (1-200).
        include_hidden: Include dotfiles and dot-directories when true.

    Returns:
        JSON with each matching relative path, line number and line content.
        Binary files and files larger than 2 MB are skipped.
    """
    query = query.strip()
    pattern = file_pattern.strip()
    if not query:
        raise ValueError("query must not be empty")
    if not pattern:
        raise ValueError("file_pattern must not be empty")
    limit = _bounded_limit(max_results)

    matches: list[dict[str, object]] = []
    truncated = False
    skipped_files = 0
    for path in sorted(_iter_files(include_hidden), key=lambda item: _relative_path(item).casefold()):
        if not _matches(path, pattern):
            continue
        try:
            if path.stat().st_size > MAX_FILE_BYTES:
                skipped_files += 1
                continue
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            skipped_files += 1
            continue

        for line_number, line in enumerate(content.splitlines(), start=1):
            if query in line:
                if len(matches) >= limit:
                    truncated = True
                    break
                matches.append(
                    {
                        "file": _relative_path(path),
                        "line": line_number,
                        "text": line.strip(),
                    }
                )
        if truncated:
            break

    return json.dumps(
        {
            "workspace": str(WORKSPACE_ROOT),
            "query": query,
            "file_pattern": pattern,
            "matches": matches,
            "truncated": truncated,
            "skipped_files": skipped_files,
        },
        ensure_ascii=False,
        indent=2,
    )


if __name__ == "__main__":
    if TRANSPORT == "stdio":
        logger.info("Starting repo-helper MCP server over stdio for %s", WORKSPACE_ROOT)
        mcp.run(transport="stdio")
    elif TRANSPORT == "streamable-http":
        logger.info(
            "Starting repo-helper MCP server at %s:%s/mcp for %s",
            HOST,
            PORT,
            WORKSPACE_ROOT,
        )
        mcp.run(transport="streamable-http", host=HOST, port=PORT)
    else:
        raise ValueError("MCP_TRANSPORT must be 'streamable-http' or 'stdio'")

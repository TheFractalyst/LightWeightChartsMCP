"""
server.py
------------------------------------------------------------------------------
TradingView Lightweight Charts Complete Reference MCP Server - modular entry point.

Architecture:
  - FastMCP 3.0 with FileSystemProvider for auto-discovery of @tool/@resource
  - Composable lifespans: db | model | cache
  - Auto-build ChromaDB from shipped JSON data on first run
  - Regex-based JS/TS validation for Lightweight Charts code
  - 6 tools + 1 resource, 100% local ChromaDB vector store

Usage:
  lwcmcp                          # Start MCP server (stdio, default)
  lwcmcp build                    # Build ChromaDB from shipped data and exit
  lwcmcp --transport sse --port 8080   # SSE (HTTP) transport
  python server.py                # Direct execution (same args)
"""

from __future__ import annotations

import asyncio
import os
import pathlib as _pl
import sys
from pathlib import Path

from dotenv import load_dotenv

_server_dir = _pl.Path(__file__).resolve().parent
_env_file = _server_dir / ".env"
if _env_file.is_file():
    load_dotenv(str(_env_file), override=False)

from loguru import logger  # noqa: E402

logger.remove()
logger.add(
    sys.stderr,
    format="{time:HH:mm:ss} | {level:<8} | {message}",
    level=os.getenv("LOG_LEVEL", "INFO"),
)

# -----------------------------------------------------------------------------
# HTTP transport runtime setup (stderr + daily rotating file)
# -----------------------------------------------------------------------------
from core.config import _TRANSPORT  # noqa: E402

_LOG_DIR = os.getenv("LOG_DIR", os.path.join(os.path.expanduser("~"), ".lwc_mcp", "logs"))

if _TRANSPORT in ("http", "sse"):
    try:
        _log_path = Path(_LOG_DIR)
        _log_path.mkdir(parents=True, exist_ok=True)
        logger.add(
            str(_log_path / "server_{time:YYYY-MM-DD}.log"),
            format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level:<8} | {name}:{function}:{line} | {message}",
            level=os.getenv("LOG_LEVEL", "INFO"),
            rotation="00:00",
            retention="30 days",
            compression="gz",
            encoding="utf-8",
            enqueue=True,
            backtrace=True,
            diagnose=False,
        )
        logger.debug(f"Log dir: {_log_path}")
    except Exception as _e:
        logger.warning(f"Log dir unavailable: {_e}")

from fastmcp import FastMCP  # noqa: E402, I001
from fastmcp.server.lifespan import lifespan  # noqa: E402
from fastmcp.server.middleware.caching import ResponseCachingMiddleware  # noqa: E402
from fastmcp.server.middleware.response_limiting import ResponseLimitingMiddleware  # noqa: E402
from fastmcp.server.middleware.timing import DetailedTimingMiddleware  # noqa: E402
from fastmcp.server.providers.filesystem import FileSystemProvider  # noqa: E402
from starlette.requests import Request  # noqa: E402
from starlette.responses import JSONResponse  # noqa: E402

from core.config import INSTRUCTIONS, MAX_TOOL_RESPONSE_CHARS, _safe_int  # noqa: E402
from formatters.errors import safe_error  # noqa: E402
from core.build_db import build_db_if_needed  # noqa: E402
from core.db import get_collection, build_name_index  # noqa: E402
from core.embeddings import get_model, _model_executor, _embedding_model_ready  # noqa: E402
from core.hot_cache import build_hot_cache  # noqa: E402
from core.validator import validator_cb  # noqa: E402


# -----------------------------------------------------------------------------
# Composable lifespans
# -----------------------------------------------------------------------------


@lifespan
async def db_lifespan(server):
    """Initialize ChromaDB collection and name index. Auto-builds DB on first run."""
    try:
        await asyncio.get_running_loop().run_in_executor(None, build_db_if_needed)
        logger.info("Preloading ChromaDB collection...")
        get_collection()
        logger.info("ChromaDB collection ready")

        logger.info("Building name index...")
        build_name_index()
        logger.info("Name index ready")
    except Exception as e:
        logger.error(f"ChromaDB init failed: {e}. Search tools will be unavailable.")
    yield


@lifespan
async def model_lifespan(server):
    """Initialize embedding model in thread pool."""
    if os.getenv("LAZY_MODEL", "").lower() in ("1", "true"):
        logger.info("LAZY_MODEL=1 - deferring embedding model load to first query")
        yield
        return
    try:
        logger.info("Preloading embedding model...")
        loop = asyncio.get_running_loop()
        model = await loop.run_in_executor(_model_executor, get_model)
        _embedding_model_ready.set()
        await loop.run_in_executor(_model_executor, lambda: model.encode(["warmup"]))
        logger.info("Embedding model ready (warmed up)")
    except Exception as e:
        logger.error(f"Embedding model load failed: {e}. Semantic search will be unavailable.")
    yield


@lifespan
async def cache_lifespan(server):
    """Build hot cache."""
    logger.info("Building hot cache...")
    success = await build_hot_cache()
    if success:
        logger.info("Hot cache ready")
    else:
        logger.warning("Hot cache build failed - direct DB lookups will be used")
    yield
    _model_executor.shutdown(wait=False)


# -----------------------------------------------------------------------------
# Response caching middleware (complementary to internal LRU caches)
#
# Two-tier MCP-level caching:
#   1. Lookup middleware (1h TTL): deterministic, stable doc entries
#   2. Search middleware (5m TTL): same query = same result within a session
#
# Validation/codegen tools are EXCLUDED - unique code on nearly every call.
# -----------------------------------------------------------------------------

_lookup_cache_mw = ResponseCachingMiddleware(
    call_tool_settings={
        "ttl": 3600,
        "enabled": True,
        "included_tools": [
            "lwc_lookup",
            "lwc_browse",
        ],
    },
)

_search_cache_mw = ResponseCachingMiddleware(
    call_tool_settings={
        "ttl": 300,
        "enabled": True,
        "included_tools": [
            "lwc_search",
        ],
    },
)


# -----------------------------------------------------------------------------
# FastMCP server instance with FileSystemProvider auto-discovery
# -----------------------------------------------------------------------------

_mcp_dir = Path(__file__).parent / "tools"

mcp = FastMCP(
    name="LightWeightChartsMCP",
    instructions=INSTRUCTIONS,
    lifespan=db_lifespan | model_lifespan | cache_lifespan,
    mask_error_details=True,
    providers=[FileSystemProvider(_mcp_dir, reload=False)],
    middleware=[
        _lookup_cache_mw,
        _search_cache_mw,
        ResponseLimitingMiddleware(max_size=MAX_TOOL_RESPONSE_CHARS + 10_000),
    ] + ([DetailedTimingMiddleware()] if os.getenv("LOG_LEVEL", "INFO") == "DEBUG" else []),
)


# -----------------------------------------------------------------------------
# Health check endpoint (no auth required)
# -----------------------------------------------------------------------------


@mcp.custom_route("/health", methods=["GET"])
async def health_check(request: Request) -> JSONResponse:
    """Health endpoint for local development and testing."""
    try:
        col = get_collection()
        return JSONResponse({
            "status": "ok",
            "entries": col.count(),
            "validator_circuit_open": validator_cb.is_open(),
        })
    except Exception as e:
        return JSONResponse(
            {"status": "error", "error": safe_error(e, "health_check")},
            status_code=503,
        )


# -----------------------------------------------------------------------------
# Entry point
# -----------------------------------------------------------------------------


def main():
    """CLI entry point for lwcmcp console script.

    Usage:
        lwcmcp              Start MCP server (stdio, default)
        lwcmcp build        Build ChromaDB from shipped data and exit
        lwcmcp --transport sse --port 8080   Start SSE server
    """
    import argparse

    parser = argparse.ArgumentParser(
        prog="lwcmcp",
        description="Lightweight Charts MCP Server - docs lookup, JS/TS validation, and template generation",
    )
    parser.add_argument(
        "command",
        nargs="?",
        default="serve",
        choices=["serve", "build"],
        help="Command: 'serve' (default) starts the MCP server, 'build' builds ChromaDB and exits",
    )
    parser.add_argument("--transport", default=None, help="Transport: stdio (default) or sse")
    parser.add_argument("--port", type=int, default=None, help="Port for SSE transport")
    args = parser.parse_args()

    if args.command == "build":
        from core.build_db import build_db

        count = build_db(force=True)
        print(f"ChromaDB built: {count} entries")
        return

    logger.info("Starting Lightweight Charts MCP server (6 tools, 100% local)")

    transport = args.transport or _TRANSPORT

    if transport in ("http", "sse"):
        _port = args.port or _safe_int("PORT", 8080)
        logger.info(f"Transport: SSE (HTTP) on 0.0.0.0:{_port}")
        mcp.run(transport="sse", host="0.0.0.0", port=_port)
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()

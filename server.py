"""
server.py
TradingView Lightweight Charts Complete Reference MCP Server.

Architecture:
  - FastMCP 3.0 with FileSystemProvider for auto-discovery of @tool/@resource
  - Composable lifespans: db | model | cache
  - Regex-based JS/TS validation for Lightweight Charts code
  - 6 tools + 1 resource, 100% local ChromaDB vector store

Usage:
  python server.py                 # Start the MCP server (stdio transport)
  TRANSPORT=sse PORT=8080 python server.py  # SSE transport with HTTP
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

from core.config import _TRANSPORT, INSTRUCTIONS, _safe_int  # noqa: E402

_LOG_DIR = os.getenv("LWC_DIAG_DIR", "/var/log/lwc_mcp")

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
    except Exception as _e:
        logger.warning(f"Log dir unavailable: {_e}")

from fastmcp import FastMCP  # noqa: E402, I001
from fastmcp.server.lifespan import lifespan  # noqa: E402
from fastmcp.server.providers.filesystem import FileSystemProvider  # noqa: E402
from starlette.requests import Request  # noqa: E402
from starlette.responses import JSONResponse  # noqa: E402

from formatters.errors import safe_error  # noqa: E402
from core.db import get_collection, build_name_index  # noqa: E402
from core.embeddings import get_model, _model_executor, _embedding_model_ready  # noqa: E402
from core.hot_cache import build_hot_cache  # noqa: E402
from core.validator import validator_cb  # noqa: E402


@lifespan
async def db_lifespan(server):
    try:
        logger.info("Preloading ChromaDB...")
        get_collection()
        build_name_index()
        logger.info("ChromaDB ready")
    except Exception as e:
        logger.error(f"ChromaDB init failed: {e}")
    yield


@lifespan
async def model_lifespan(server):
    if os.getenv("LAZY_MODEL", "").lower() in ("1", "true"):
        yield
        return
    try:
        logger.info("Preloading embedding model...")
        loop = asyncio.get_running_loop()
        model = await loop.run_in_executor(_model_executor, get_model)
        _embedding_model_ready.set()
        await loop.run_in_executor(_model_executor, lambda: model.encode(["warmup"]))
        logger.info("Embedding model ready")
    except Exception as e:
        logger.error(f"Embedding model load failed: {e}")
    yield


@lifespan
async def cache_lifespan(server):
    logger.info("Building hot cache...")
    success = await build_hot_cache()
    if success:
        logger.info("Hot cache ready")
    yield
    _model_executor.shutdown(wait=False)


_mcp_dir = Path(__file__).parent / "tools"

mcp = FastMCP(
    name="Lightweight Charts Complete Reference",
    instructions=INSTRUCTIONS,
    lifespan=db_lifespan | model_lifespan | cache_lifespan,
    mask_error_details=True,
    providers=[FileSystemProvider(_mcp_dir, reload=False)],
)


@mcp.custom_route("/health", methods=["GET"])
async def health_check(request: Request) -> JSONResponse:
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


if __name__ == "__main__":
    logger.info("Starting Lightweight Charts MCP server (6 tools, 100% local)")

    if _TRANSPORT in ("http", "sse"):
        _port = _safe_int("PORT", 8080)
        logger.info(f"Transport: SSE on 0.0.0.0:{_port}")
        mcp.run(transport="sse", host="0.0.0.0", port=_port)
    else:
        mcp.run(transport="stdio")

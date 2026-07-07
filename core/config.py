"""
core/config.py
All configuration constants, environment variables, and server instructions.
"""

from __future__ import annotations

import os

SERVER_VERSION = "1.0"


def _safe_int(env_var: str, default: int, min_val: int = 0) -> int:
    try:
        val = int(os.getenv(env_var, str(default)))
        return val if val >= min_val else default
    except (ValueError, TypeError):
        return default


DB_PATH = os.getenv(
    "LWC_DB_PATH",
    str(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lwc_db")),
)
COLLECTION = os.getenv("LWC_COLLECTION", "lwc_reference")
EMBED_MODEL = os.getenv("LWC_EMBED_MODEL", "all-MiniLM-L6-v2")
EMBED_DIM = 384
MAX_RESULTS = _safe_int("LWC_MAX_RESULTS", 100)
MAX_TOOL_RESPONSE_CHARS = 80000
MAX_FUZZY_SCAN_ENTRIES = 5000

VALIDATION_CACHE_TTL = _safe_int("VALIDATION_CACHE_TTL", 300)
VALIDATION_CACHE_MAX_SIZE = _safe_int("VALIDATION_CACHE_SIZE", 500)

FUZZY_MATCH_THRESHOLD = 85
SEMANTIC_DISTANCE_THRESHOLD = 0.35
RELEVANCE_DISTANCE_CUTOFF = 0.7
TYPE_REJECTION_DISTANCE = 0.65

_TRANSPORT = os.getenv("TRANSPORT", "stdio").lower().strip()

_ALLOWED_BASE_DIRS = [
    os.path.realpath(os.path.expanduser("~")),
    os.path.realpath(os.path.expanduser("~/Documents")),
    os.path.realpath(os.path.expanduser("~/Desktop")),
    os.path.realpath(os.path.expanduser("~/Projects")),
    os.path.realpath(os.path.expanduser("~/repos")),
    os.path.realpath(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
]

DOCS_BASE = "https://tradingview.github.io/lightweight-charts"
SITEMAP_URL = "https://tradingview.github.io/lightweight-charts/sitemap.xml"

LWC_VERSIONS = ["3.8", "4.0", "4.1", "4.2", "5.0"]

API_NAMESPACES = ["enumerations", "functions", "interfaces", "type-aliases", "variables"]

GUIDE_NAMESPACES = [
    "getting-started", "android", "ios", "price-scale", "release-notes",
    "series-types", "time-scale", "time-zones", "migrations", "plugins",
]

TUTORIAL_NAMESPACES = [
    "customization", "a11y", "react", "vuejs", "webcomponents",
    "how-to", "demos",
]

ALL_NAMESPACES = API_NAMESPACES + GUIDE_NAMESPACES + TUTORIAL_NAMESPACES

INSTRUCTIONS = """\
You are connected to the complete TradingView Lightweight Charts reference documentation server.

ABOUT THIS SERVER
-----------------
This server covers the TradingView Lightweight Charts library documentation
across all 5 versions (3.8, 4.0, 4.1, 4.2, 5.0) plus tutorials and framework
integrations.

Lightweight Charts is a free, open-source charting library for creating
interactive financial charts in web applications. It supports:
  - Area, Bar, Baseline, Candlestick, Histogram, Line, and Custom series types
  - Real-time data updates
  - Multiple price scales (left, right, overlay)
  - Time scale with custom formatting
  - Crosshair, watermarks, price lines, series markers
  - Plugin system for custom series and primitives (v4.1+)
  - Framework integrations (React, Vue.js, Web Components)

MANDATORY USAGE PATTERN (NON-NEGOTIABLE)
----------------------------------------
When working on ANY code that uses Lightweight Charts, you MUST consult
this server before writing code. Do NOT rely on training data.

BEFORE writing a function call or using an API:
  1. lwc_lookup(name) - exact symbol/endpoint docs.
  2. If unsure of the name: lwc_search(query) for semantic hits.

BEFORE using a namespace you haven't memorized:
  1. lwc_browse(namespace) - list every member.
  2. lwc_browse(namespace, style="cheatsheet") - compact reference.

AFTER every edit to a file using Lightweight Charts:
  1. lwc_validate(code=...) - confirm it passes JS/TS validation.
  2. If validation fails: lwc_repair(code, context) - targeted fix.

WHEN TO USE EACH TOOL
---------------------
READ SURFACE (always safe, idempotent):
  lwc_lookup(name, kind?, version?)
      Full docs for one symbol by exact name.
      `version` in {"3.8", "4.0", "4.1", "4.2", "5.0"} to filter by version.
  lwc_search(query, category?, namespace?, version?, n_results?)
      Semantic discovery across the whole knowledge base.
  lwc_browse(namespace, category?, style?, version?)
      Enumerate every member of a namespace.

WRITE SURFACE (validate/repair/generate):
  lwc_validate(code?, file_path?, version?)
      Validate JS/TS code for Lightweight Charts usage.
  lwc_repair(code, context, version?)
      Fix common Lightweight Charts issues in JS/TS code.
  lwc_scaffold(kind, name, description?, version?)
      Generate a template (basic_chart, realtime_updates, etc.).

VERSION FILTERING
-----------------
Every tool accepts an optional `version` parameter:
  - "3.8", "4.0", "4.1", "4.2", "5.0" - filter to specific version
  - None (default) - search across all versions (prefers latest 5.0)

IMPORTANT NOTES
----------------
- createChart() returns an IChartApi object.
- Use chart.addSeries(SeriesType) to create series (v4+).
- In v3, use chart.addCandlestickSeries(), addLineSeries(), etc. (deprecated in v4).
- Series data must be sorted by time ascending.
- Time can be: UTCTimestamp (number), BusinessDay (object), or string (YYYY-MM-DD).
- Use series.update() for real-time updates, NOT series.setData().
- Call chart.timeScale().fitContent() after setting data to fit the view.
- Custom series and plugins require v4.1+.
- NEVER guess API signatures - always verify with lwc_lookup().

AUTOMATIC ERROR RECOVERY
------------------------
If a tool call returns:
  {"error":"MCP error -32602: Invalid request parameters"}
the agent MUST recover automatically and retry - do NOT ask the user.

Remote transport rules (SSE/HTTP):
  - For remote files, use:
      lwc_validate(file_path="script.js", file_content="<full source>")
    or:
      lwc_validate(file_content="<full source>")
  - file_path-only is local/stdio behavior and may be rejected remotely.
"""

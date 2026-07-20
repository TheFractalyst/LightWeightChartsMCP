# LightWeightChartsMCP

[![PyPI](https://img.shields.io/pypi/v/lwcmcp?color=blue)](https://pypi.org/project/lwcmcp/)
[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)](https://python.org)
[![ChromaDB](https://img.shields.io/badge/ChromaDB-FF6F00)](https://trychroma.com)
[![MCP](https://img.shields.io/badge/MCP-Protocol-blue)](https://modelcontextprotocol.io)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Tests](https://github.com/TheFractalyst/LightWeightChartsMCP/actions/workflows/test.yml/badge.svg)](https://github.com/TheFractalyst/LightWeightChartsMCP/actions/workflows/test.yml)

Complete TradingView Lightweight Charts reference documentation MCP server with 6 tools
for semantic search, JS/TS code validation, and template generation.

[Quick Start](#one-command-fully-functional) |
[Tools](#tools) |
[Configuration](#configuration) |
[Development](#development)

---

```bash
pip install lwcmcp
lwcmcp
```

That's it. On first run, the server auto-builds the ChromaDB vector store from
shipped JSON data (takes 30-60 seconds for embedding model download + indexing).
Subsequent runs start instantly.

**What you get:**

- 6 MCP tools for Lightweight Charts docs lookup, JS/TS code validation, and template generation
- ~1617 entries indexed in a local ChromaDB vector store (100% offline)
- Sub-millisecond hot cache for priority lookups
- Regex-based JS/TS validator (no Node.js runtime required)
- Works with Claude Desktop, Cursor, Windsurf, OpenCode, and any MCP client

**What you need:**

- Python 3.10+
- Any MCP-compatible AI client

---

## Features

- **6 tools**: lookup, search, browse, validate, repair, scaffold
- **1 resource**: `lwc://stats`
- **100% local**: ChromaDB vector store, no network calls at runtime
- **Fast**: Hot cache for instant lookups, name index for fuzzy matching, semantic search (warm)
- **5 versions**: 3.8, 4.0, 4.1, 4.2, 5.0 plus tutorials and framework integrations
- **Validator**: Regex-based JS/TS validation (no Node.js runtime required)
- **7 templates**: basic_chart, realtime_updates, react_integration, vue_integration, web_components, custom_styling, multi_series
- **Version filtering**: Every tool accepts `version` param to filter by LWC version
- **Production-ready**: Health endpoint, circuit breakers, error masking, response capping, response caching middleware

## Coverage

- LWC API: functions, interfaces, enumerations, type-aliases, variables (all 5 versions)
- Guides: getting-started, series-types, price-scale, time-scale, time-zones, plugins, migrations, android, ios, release-notes
- Tutorials: customization, a11y, react, vuejs, webcomponents, how-to, demos
- Total: ~1617 entries across 5 versions + tutorials
- ChromaDB: all entries indexed (JSON = ChromaDB, zero dedup loss)

## Setup

```bash
pip install lwcmcp
```

Or from source:

```bash
git clone https://github.com/TheFractalyst/LightWeightChartsMCP.git
cd LightWeightChartsMCP
pip install -e ".[dev]"
```

## Run the server

```bash
# stdio (for MCP clients like Claude, Cursor, opencode)
lwcmcp

# SSE (HTTP)
lwcmcp --transport sse --port 8080

# Build ChromaDB manually (auto-builds on first run otherwise)
lwcmcp build
```

## MCP Client Configuration

### Claude Desktop

Add to `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS)
or `%APPDATA%\Claude\claude_desktop_config.json` (Windows):

```json
{
  "mcpServers": {
    "lightweightchartsmcp": {
      "command": "lwcmcp",
      "transport": "stdio"
    }
  }
}
```

### Cursor / Windsurf / OpenCode

Add to your project's `.mcp.json` or global MCP config:

```json
{
  "mcpServers": {
    "lightweightchartsmcp": {
      "command": "lwcmcp",
      "transport": "stdio"
    }
  }
}
```

### SSE (HTTP)

```bash
lwcmcp --transport sse --port 8080
```

Connect to `http://localhost:8080`.

## Tools

```
+--------------+-----------+------------------------------------------+
| Tool         | Type      | Description                               |
+--------------+-----------+------------------------------------------+
| lwc_lookup   | read-only | Exact name lookup with fuzzy fallback     |
| lwc_search   | read-only | Semantic search across all entries        |
| lwc_browse   | read-only | List namespace members                    |
| lwc_validate | read-write| Validate JS/TS for Lightweight Charts     |
| lwc_repair   | read-write| Fix common Lightweight Charts issues      |
| lwc_scaffold | read-write| Generate chart template (7 kinds)         |
+--------------+-----------+------------------------------------------+
```

```
+----------------+----------------------------------------------------+
| Tool           | Signature                                          |
+----------------+----------------------------------------------------+
| lwc_lookup     | (name, kind?, version?)                            |
| lwc_search     | (query, category?, namespace?, version?, n_results?)|
| lwc_browse     | (namespace, category?, style?, version?)           |
| lwc_validate   | (code?, file_path?, file_content?, version?)       |
| lwc_repair     | (code, context, version?)                          |
| lwc_scaffold   | (kind, name, description?, version?)              |
+----------------+----------------------------------------------------+
```

### Version Filtering

Every tool accepts an optional `version` parameter:
- `"3.8"`, `"4.0"`, `"4.1"`, `"4.2"`, `"5.0"` - filter to specific version
- `None` (default) - search across all versions (prefers latest 5.0)

## Configuration

```
+------------------------+------------------+--------------------------------------------+
| Env Var                | Default          | Description                                |
+------------------------+------------------+--------------------------------------------+
| TRANSPORT              | stdio            | Transport: stdio or sse                    |
| PORT                   | 8080             | Port for SSE transport                     |
| LWC_DB_PATH            | ~/.lwc_mcp/db    | ChromaDB path                              |
| LWC_COLLECTION         | lwc_reference    | ChromaDB collection name                   |
| LWC_EMBED_MODEL        | all-MiniLM-L6-v2 | Sentence transformer model                 |
| LWC_MAX_RESULTS        | 100              | Max results returned                       |
| VALIDATION_CACHE_TTL   | 300              | Validation cache TTL (seconds)             |
| VALIDATION_CACHE_SIZE  | 500              | Validation cache max entries               |
| LWC_INDEX_BATCH_SIZE   | 25               | Indexing batch size                        |
| LAZY_MODEL             | (empty)          | Set to 1/true to defer model loading       |
| LOG_DIR                | ~/.lwc_mcp/logs  | Log directory (SSE transport)              |
| LOG_LEVEL              | INFO             | Logging level                              |
+------------------------+------------------+--------------------------------------------+
```

## Namespaces

### API Namespaces

```
+----------------+----------------------------------------------+
| Namespace      | Description                                  |
+----------------+----------------------------------------------+
| enumerations   | Enums (LineStyle, CrosshairMode, etc.)      |
| functions      | Functions (createChart, addSeries, etc.)    |
| interfaces     | Interfaces (IChartApi, ISeriesApi, etc.)    |
| type-aliases   | Type aliases (SeriesType, Time, etc.)       |
| variables      | Variables and constants                      |
+----------------+----------------------------------------------+
```

### Guide Namespaces

```
+------------------+------------------------------------------+
| Namespace        | Description                              |
+------------------+------------------------------------------+
| getting-started  | Getting started guides                   |
| android          | Android platform integration             |
| ios              | iOS platform integration                 |
| price-scale      | Price scale configuration                |
| release-notes    | Version release notes                    |
| series-types     | Series types (candlestick, line, etc.)   |
| time-scale       | Time scale configuration                 |
| time-zones       | Time zone handling                       |
| migrations       | Version migration guides                 |
| plugins          | Plugin system (v4.1+)                    |
+------------------+------------------------------------------+
```

### Tutorial Namespaces

```
+----------------+----------------------------------------------+
| Namespace      | Description                                  |
+----------------+----------------------------------------------+
| customization  | Chart customization tutorials               |
| a11y           | Accessibility tutorials                      |
| react          | React framework integration                 |
| vuejs          | Vue.js framework integration                 |
| webcomponents  | Web Components integration                   |
| how-to         | How-to guides                                |
| demos          | Demo applications                            |
+----------------+----------------------------------------------+
```

## Scaffold Templates (7 kinds)

```
+--------------------+----------------------------------------------+
| Kind               | Description                                  |
+--------------------+----------------------------------------------+
| basic_chart        | Basic chart with createChart + setData       |
| realtime_updates   | Real-time data streaming with series.update  |
| react_integration  | React component with useRef + useEffect      |
| vue_integration    | Vue.js component with ref                    |
| web_components     | Web Components custom element wrapper        |
| custom_styling     | Custom chart and series options/styling      |
| multi_series       | Multiple series (candlestick + volume)       |
+--------------------+----------------------------------------------+
```

## Development

```bash
ruff check . --line-length 120    # lint
pytest tests/ -v                   # test
```

## Architecture

- **FastMCP 3.4** with FileSystemProvider for auto-discovery
- **ChromaDB** vector store (cosine, all-MiniLM-L6-v2, 384-dim)
- 3 composable lifespans: db | model | cache
- Auto-build ChromaDB from shipped JSON on first run
- Response caching middleware (lookup/browse 1h, search 5m)
- Response limiting middleware (80KB cap)
- Circuit breaker on validator and ChromaDB
- Hot cache for fast lookups
- Error masking (no internal details leaked)
- Health endpoint at `/health`

## Database

- ~1617 entries across 5 versions (3.8, 4.0, 4.1, 4.2, 5.0) + tutorials
- Auto-built on first run from shipped JSON data (1.5MB)
- Stored at `~/.lwc_mcp/db` (survives project updates)

To rebuild the database:

```bash
lwcmcp build
```

## Data Pipeline

- `pipeline/scrape_lwc.py` - Direct HTTP scraper for Lightweight Charts docs sitemap (github.io, no ScraperAPI needed)
- `pipeline/merge_and_index.py` - Merge + index into ChromaDB

### Re-scrape from TradingView

```bash
pip install -e ".[pipeline]"
python pipeline/scrape_lwc.py
python pipeline/merge_and_index.py --reset
```

## Tech Stack

- **FastMCP 3.4** - MCP server framework with FileSystemProvider auto-discovery
- **ChromaDB** - Local vector database for semantic search
- **SentenceTransformers** - `all-MiniLM-L6-v2` embedding model (384-dim)
- **RapidFuzz** - Fuzzy string matching for name lookups
- **Loguru** - Structured logging with daily rotation (SSE mode)

## Links

- [fractalyst.dev](https://fractalyst.dev/) - Author homepage
- [TradingView](https://www.tradingview.com/u/Fractalyst/#published-scripts) - Public PineScript indicators
- [@TheFractalyst](https://x.com/TheFractalyst) - X / Twitter

## License

MIT - see [LICENSE](LICENSE)

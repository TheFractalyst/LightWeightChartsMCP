# LightWeightChartsMCP - Agent Instructions

## Overview
TradingView Lightweight Charts reference documentation MCP server with ~730 entries covering all 5 versions (3.8, 4.0, 4.1, 4.2, 5.0) plus tutorials and framework integrations.

## Commands

### Setup
```bash
pip install -e ".[dev]"
```

### Build database (auto-builds on first run, or manually)
```bash
lwcmcp build
```

### Run server
```bash
lwcmcp                                 # stdio (default)
lwcmcp --transport sse --port 8080     # SSE (HTTP)
```

### Index database from pipeline
```bash
python pipeline/merge_and_index.py --reset
```

### Lint
```bash
ruff check . --line-length 120
```

### Test
```bash
pytest tests/ -v
```

## Architecture

- **FastMCP 3.4** with FileSystemProvider for auto-discovery
- **ChromaDB** vector store (cosine, all-MiniLM-L6-v2, 384-dim)
- 3 composable lifespans: db | model | cache
- Circuit breaker on validator and ChromaDB
- Hot cache for fast lookups
- Response capping at 80KB
- Error masking (no internal details leaked)
- Regex-based JS/TS validator (no Node.js runtime required)

## Tools (6)

```
+--------------+-----------+------------------------------------------+
| Tool         | Type      | Description                              |
+--------------+-----------+------------------------------------------+
| lwc_lookup   | read-only | Exact name lookup with fuzzy fallback    |
| lwc_search   | read-only | Semantic search across all entries       |
| lwc_browse   | read-only | List namespace members                   |
| lwc_validate | read-write| Validate JS/TS for Lightweight Charts    |
| lwc_repair   | read-write| Fix common Lightweight Charts issues     |
| lwc_scaffold | read-write| Generate chart template (7 kinds)        |
+--------------+-----------+------------------------------------------+
```

## Data Pipeline

- `pipeline/scrape_lwc.py` - Direct HTTP scraper for Lightweight Charts docs (github.io)
- `pipeline/merge_and_index.py` - Merge + index into ChromaDB

## Coverage

- LWC API: 5 namespaces (functions, interfaces, enumerations, type-aliases, variables)
- Guides: 10 namespaces (getting-started, series-types, price-scale, time-scale, time-zones, plugins, migrations, android, ios, release-notes)
- Tutorials: 7 namespaces (customization, a11y, react, vuejs, webcomponents, how-to, demos)
- Total: ~730 entries, all in ChromaDB
- 5 versions covered (3.8, 4.0, 4.1, 4.2, 5.0)
- 22 namespaces (5 API + 10 guides + 7 tutorials)

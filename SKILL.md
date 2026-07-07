---
name: lwc-mcp
description: Use when working with TradingView Lightweight Charts library. Covers createChart, series types, price scales, time scales, plugins, and framework integrations across all versions (3.8-5.0). Triggers on "lightweight charts", "tradingview", "createChart", "addSeries", "candlestick", "chart", "IChartApi", "ISeriesApi".
---

# LWC MCP - TradingView Lightweight Charts Reference

## When to Use

Use this skill when working with the TradingView Lightweight Charts library in any JavaScript or TypeScript project. This covers:

- Creating charts with `createChart()`
- Series types (candlestick, line, area, bar, baseline, histogram)
- Price scales, time scales, crosshair, watermarks, price lines, markers
- Real-time data updates with `series.update()`
- Plugin system and custom series (v4.1+)
- Framework integrations (React, Vue.js, Web Components)
- Version-specific API differences (v3 vs v4+)

**Trigger keywords:** "lightweight charts", "tradingview", "createChart", "addSeries", "candlestick", "IChartApi", "ISeriesApi", "price scale", "time scale", "chart styling"

## When to Use the LWC MCP Server

The LWC MCP server provides 6 tools for querying the complete Lightweight Charts documentation across all 5 versions (3.8, 4.0, 4.1, 4.2, 5.0) plus tutorials. Use it instead of relying on training data, which may be outdated or version-confused.

## Mandatory Usage Pattern (Non-Negotiable)

When working on ANY code that uses Lightweight Charts, you MUST consult this server before writing code. Do NOT rely on training data.

### BEFORE writing a function call or using an API:
1. `lwc_lookup(name)` - exact symbol docs (e.g. `lwc_lookup("createChart")`)
2. If unsure of the name: `lwc_search(query)` for semantic hits

### BEFORE using a namespace you haven't memorized:
1. `lwc_browse(namespace)` - list every member
2. `lwc_browse(namespace, style="cheatsheet")` - compact reference

### AFTER every edit to a file using Lightweight Charts:
1. `lwc_validate(code=...)` - confirm it passes JS/TS validation
2. If validation fails: `lwc_repair(code, context)` - targeted fix

## Tool Signatures

### READ SURFACE (always safe, idempotent)

**lwc_lookup(name, kind?, version?)**
Full docs for one symbol by exact name. `kind` filters by entity type: `function` | `interface` | `enumeration` | `type-alias` | `variable` | `guide`. Leave unset to auto-pick the richest match. `version` filters to a specific LWC version.

**lwc_search(query, category?, namespace?, version?, n_results?)**
Semantic discovery across the whole knowledge base. Use for fuzzy or conceptual searches like "how do I create a candlestick chart".

**lwc_browse(namespace, category?, style?, version?)**
Enumerate every member of a namespace. `style="cheatsheet"` gives a compact signature summary. Namespaces: `enumerations`, `functions`, `interfaces`, `type-aliases`, `variables`, `getting-started`, `series-types`, `price-scale`, `time-scale`, `plugins`, `react`, `vuejs`, `webcomponents`, etc.

### WRITE SURFACE (validate/repair/generate)

**lwc_validate(code?, file_path?, file_content?, version?)**
Validate JS/TS code for Lightweight Charts usage. Checks brace balance, missing imports, deprecated v3 methods, missing fitContent, real-time update patterns. No Node.js runtime required - uses regex pattern matching.

**lwc_repair(code, context, version?)**
Fix common Lightweight Charts issues in JS/TS code. `context` describes the problem (e.g. "deprecated v3 method", "missing import", "real-time update").

**lwc_scaffold(kind, name, description?, version?)**
Generate a template from 7 kinds:
- `basic_chart` - Basic chart with createChart + setData + fitContent
- `realtime_updates` - Real-time data streaming with series.update()
- `react_integration` - React component with useRef + useEffect
- `vue_integration` - Vue.js component with ref
- `web_components` - Web Components custom element wrapper
- `custom_styling` - Custom chart and series options/styling
- `multi_series` - Multiple series (candlestick + volume histogram)

## Version Filtering

Every tool accepts an optional `version` parameter:
- `"3.8"`, `"4.0"`, `"4.1"`, `"4.2"`, `"5.0"` - filter to specific version
- `None` (default) - search across all versions (prefers latest 5.0)

Always specify the version when working with a specific LWC version to avoid pulling docs from a different version with incompatible APIs.

## Common Workflows

### 1. Create a Basic Chart
```
lwc_lookup("createChart")           # get createChart signature
lwc_lookup("IChartApi")             # understand chart API
lwc_browse("interfaces")            # list all interfaces
lwc_scaffold("basic_chart", "MyChart")  # generate template
lwc_validate(code=...)              # validate the result
```

### 2. Real-Time Updates
```
lwc_lookup("ISeriesApi")            # find update() method
lwc_search("real-time data update") # semantic search
lwc_scaffold("realtime_updates", "LiveChart")
lwc_validate(code=...)
```

### 3. React Integration
```
lwc_browse("react")                 # list React tutorials
lwc_scaffold("react_integration", "ChartComponent")
lwc_validate(code=...)
```

### 4. Custom Styling
```
lwc_lookup("IChartApi")             # chart options
lwc_search("chart styling options")
lwc_scaffold("custom_styling", "StyledChart")
lwc_validate(code=...)
```

## Error Recovery (Automatic)

If a tool call returns:
```
{"error":"MCP error -32602: Invalid request parameters"}
```
The agent MUST recover automatically and retry - do NOT ask the user.

Recovery sequence:
1. Refresh schema from tools/list and read the target tool's current argument schema
2. Send only schema-valid fields with correct JSON types
3. Remove unknown keys, fix enum values, provide required fields
4. Retry once with corrected arguments

## Remote Transport Rules (SSE/HTTP)

- Do NOT rely on server-side file_path resolution for client-local paths
- For remote files, use:
  ```
  lwc_validate(file_path="script.js", file_content="<full source>")
  ```
  or:
  ```
  lwc_validate(file_content="<full source>")
  ```
- `file_path`-only is local/stdio behavior and may be rejected remotely

## Key API Differences: v3 vs v4+

The biggest breaking change between v3 and v4+ is how series are created:

### v3 (deprecated, removed in v4)
```js
const candlestickSeries = chart.addCandlestickSeries({
  upColor: '#26a69a',
  downColor: '#ef5350',
});
```

### v4+ (current)
```js
import { CandlestickSeries } from 'lightweight-charts';
const candlestickSeries = chart.addSeries(CandlestickSeries, {
  upColor: '#26a69a',
  downColor: '#ef5350',
});
```

### Deprecated v3 methods (all removed in v4):
- `addCandlestickSeries()` -> `addSeries(CandlestickSeries)`
- `addLineSeries()` -> `addSeries(LineSeries)`
- `addAreaSeries()` -> `addSeries(AreaSeries)`
- `addBarSeries()` -> `addSeries(BarSeries)`
- `addBaselineSeries()` -> `addSeries(BaselineSeries)`
- `addHistogramSeries()` -> `addSeries(HistogramSeries)`

The series type constants (CandlestickSeries, LineSeries, etc.) must be imported from the package in v4+.

### Other important notes:
- `createChart()` returns an `IChartApi` object in all versions
- Series data must be sorted by time ascending
- Time can be: `UTCTimestamp` (number), `BusinessDay` (object), or string (`YYYY-MM-DD`)
- Use `series.update()` for real-time updates, NOT `series.setData()`
- Call `chart.timeScale().fitContent()` after `setData()` to fit the view
- Custom series and plugins require v4.1+
- NEVER guess API signatures - always verify with `lwc_lookup()`

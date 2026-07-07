# ruff: noqa: E501
"""
formatters/errors.py
Error formatting, fix hints, sanitization utilities, and response capping.
"""

from __future__ import annotations

import re
from typing import Optional

from loguru import logger

from core.config import MAX_TOOL_RESPONSE_CHARS

_FIX_HINTS: dict[str, str] = {
    "addCandlestickSeries": "addCandlestickSeries() was removed in v4. Use chart.addSeries(CandlestickSeries) instead.",
    "addLineSeries": "addLineSeries() was removed in v4. Use chart.addSeries(LineSeries) instead.",
    "addAreaSeries": "addAreaSeries() was removed in v4. Use chart.addSeries(AreaSeries) instead.",
    "addBarSeries": "addBarSeries() was removed in v4. Use chart.addSeries(BarSeries) instead.",
    "addBaselineSeries": "addBaselineSeries() was removed in v4. Use chart.addSeries(BaselineSeries) instead.",
    "addHistogramSeries": "addHistogramSeries() was removed in v4. Use chart.addSeries(HistogramSeries) instead.",
    "createChart": "createChart(container, options) creates a chart. Returns IChartApi. Example: const chart = createChart(document.getElementById('container'));",
    "addSeries": "chart.addSeries(SeriesType, options, paneIndex) creates a series. Example: chart.addSeries(CandlestickSeries, { upColor: '#26a69a' });",
    "setData": "series.setData(data) sets all data at once. Data must be sorted by time ascending. Example: series.setData([{ time: '2019-01-01', value: 50 }]);",
    "update": "series.update(bar) updates the last bar or adds a new one. Use for real-time updates. Example: series.update({ time: '2019-01-01', value: 50 });",
    "fitContent": "chart.timeScale().fitContent() adjusts the visible range to fit all data. Call after setData().",
    "applyOptions": "chart.applyOptions(options) applies partial options to the chart. Example: chart.applyOptions({ layout: { background: { color: '#fff' } } });",
    "priceScale": "chart.priceScale('right') or chart.priceScale('left') returns IPriceScaleApi. Use for overlay scales: chart.priceScale('').",
    "createPriceLine": "series.createPriceLine(options) creates a horizontal price line. Example: series.createPriceLine({ price: 80, color: '#f00', lineWidth: 1 });",
    "setMarkers": "series.setMarkers(markers) sets markers on the series. Example: series.setMarkers([{ time: '2019-01-01', position: 'aboveBar', shape: 'arrowDown' }]);",
    "UTCTimestamp": "UTCTimestamp is a number representing Unix time in seconds (not milliseconds). Example: { time: 1546300800, value: 50 }.",
    "BusinessDay": "BusinessDay is an object { year, month, day }. Example: { time: { year: 2019, month: 1, day: 1 }, value: 50 }.",
    "import": "Import the library: import { createChart, CandlestickSeries, LineSeries } from 'lightweight-charts'; (v4+). For v3: import { createChart } from 'lightweight-charts';",
    "CandlestickSeries": "CandlestickSeries is a series definition for addSeries (v4+). Example: chart.addSeries(CandlestickSeries, { upColor: '#26a69a' });",
    "LineSeries": "LineSeries is a series definition for addSeries (v4+). Example: chart.addSeries(LineSeries, { color: '#2962FF' });",
    "AreaSeries": "AreaSeries is a series definition for addSeries (v4+). Example: chart.addSeries(AreaSeries, { lineColor: '#2962FF', topColor: '#2962FF' });",
    "remove": "chart.remove() destroys the chart and frees memory. Call when the chart is no longer needed.",
    "resize": "chart.resize(width, height) resizes the chart. Use with ResizeObserver for responsive charts.",
    "subscribeCrosshairMove": "chart.subscribeCrosshairMove(handler) subscribes to crosshair movement. handler receives MouseEventParams.",
    "subscribeClick": "chart.subscribeClick(handler) subscribes to chart clicks (v3.2+).",
    "timeScale": "chart.timeScale() returns ITimeScaleApi. Use for time range control, scrolling, zooming.",
    "paneIndex": "chart.addSeries(SeriesType, options, paneIndex) - paneIndex (v4.1+) places series in separate panes. Default is 0.",
    "plugin": "Plugins require v4.1+. Use createChartEx with IHorzScaleBehavior for custom horizontal scales.",
    "custom series": "Custom series require v4.1+. Implement ICustomSeriesPaneView and ICustomSeriesPaneRenderer.",
}


def lookup_fix_hint(error_text: str) -> str:
    for pattern, hint in _FIX_HINTS.items():
        if pattern.lower() in error_text.lower():
            name_match = re.search(r"'([a-zA-Z_][a-zA-Z0-9_.]*)'", error_text)
            if name_match:
                hint = hint.replace("{name}", name_match.group(1))
            else:
                hint = hint.replace("{name}", "value")
            return hint
    return "Check the Lightweight Charts reference for the correct syntax."


def extract_name_from_error(error_text: str) -> Optional[str]:
    m = re.search(r"'([a-zA-Z_][a-zA-Z0-9_.]*)'", error_text)
    if m:
        return m.group(1)
    m = re.search(r"function\s+['\"]?([a-zA-Z_][a-zA-Z0-9_.]*)", error_text, re.IGNORECASE)
    if m:
        return m.group(1)
    return None


_PATH_PATTERN = re.compile(r"(/[\w./ -]+|[A-Z]:\\[\\\w. -]+)")


def safe_error(exc: Exception, context: str = "") -> str:
    msg = str(exc)
    msg = _PATH_PATTERN.sub("[path]", msg)
    if len(msg) > 200:
        msg = msg[:200] + "..."
    prefix = f"[{context}] " if context else ""
    return f"{prefix}{type(exc).__name__}: {msg}"


def _has_unclosed_fence(text: str) -> bool:
    in_fence = False
    for line in text.split("\n"):
        stripped = line.strip()
        if stripped.startswith("```"):
            if in_fence:
                if stripped == "```" or (len(stripped) > 3 and stripped[3:4] == " "):
                    in_fence = False
            else:
                in_fence = True
    return in_fence


def cap_response(text: str, limit: int = MAX_TOOL_RESPONSE_CHARS) -> str:
    if len(text) <= limit:
        return text
    truncated = text[:limit]
    if _has_unclosed_fence(truncated):
        truncated += "\n```"
    omitted = len(text) - len(truncated)
    return truncated + f"\n\n[...truncated - {omitted:,} chars omitted]"


def sanitize_text(text: str) -> str:
    if not isinstance(text, str):
        text = str(text)
    text = text.replace("\x00", "")
    text = re.sub(r"[\x01-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
    return text.strip()


def sanitize_lwc_string(s: str) -> str:
    s = s.replace('"', "'")
    s = s.replace("\\", "/")
    s = re.sub(r"[\x00-\x1f]", "", s)
    s = s.strip()
    if not s:
        return "Script"
    return s[:100]


def circuit_breaker_msg() -> str:
    return (
        "DATABASE UNAVAILABLE\n"
        "The ChromaDB vector store has encountered repeated failures.\n"
        "To resolve:\n"
        "  1. Ensure the vector database directory exists\n"
        "  2. Re-index the documentation: ./run.sh --skip-scrape\n"
        "  3. Restart the MCP server"
    )


def check_query_error(results: dict) -> str | None:
    if "_error" in results:
        raw = str(results["_error"])
        sanitized = _PATH_PATTERN.sub("[path]", raw)
        if len(sanitized) > 150:
            sanitized = sanitized[:150] + "..."
        return (
            "DATABASE UNAVAILABLE\n"
            "The ChromaDB vector store could not process this query.\n"
            "This is a transient error - please retry in a few seconds.\n"
            f"Detail: {sanitized}"
        )
    return None


def error(tool: str, msg: str) -> str:
    logger.error(f"[{tool}] {msg}")
    return f"ERROR [{tool}]: {msg}"


def strip_string_literals(code: str) -> str:
    def _replacer(m: re.Match) -> str:
        s = m.group(0)
        return s[0] + " " * (len(s) - 2) + s[-1] if len(s) >= 2 else s

    result = re.sub(r'"(?:[^"\\]|\\.)*"', _replacer, code)
    result = re.sub(r"'(?:[^'\\]|\\.)*'", _replacer, result)
    result = re.sub(r"`(?:[^`\\]|\\.)*`", _replacer, result)
    return result


def norm_name(name: str) -> str:
    return name.strip().rstrip("()")


def norm_ns(ns: str) -> str:
    return ns.strip().lower().rstrip(".")

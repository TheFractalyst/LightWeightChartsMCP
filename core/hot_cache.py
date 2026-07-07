"""
core/hot_cache.py
In-memory hot cache for top-priority TradingView Lightweight Charts entries.
"""

from __future__ import annotations

import asyncio
import copy
import os
import threading
from typing import Optional

from loguru import logger

from core.db import get_collection

_PRIORITY_NAMESPACES_DEFAULT = [
    "functions", "interfaces", "enumerations", "type-aliases",
    "getting-started", "series-types", "price-scale", "time-scale",
    "release-notes", "migrations", "plugins",
    "customization", "how-to", "react", "vuejs", "demos",
]
_OVERRIDE_NS = os.getenv("HOT_CACHE_NAMESPACES", "")
PRIORITY_NAMESPACES = (
    [ns.strip() for ns in _OVERRIDE_NS.split(",") if ns.strip()]
    if _OVERRIDE_NS
    else _PRIORITY_NAMESPACES_DEFAULT
)

PRIORITY_GLOBALS = [
    # Core functions
    "createChart", "createChartEx", "defaultHorzScaleBehavior",
    "isBusinessDay", "isUTCTimestamp", "version",
    # Core API interfaces
    "IChartApi", "ISeriesApi", "ITimeScaleApi", "IPriceScaleApi",
    "IPriceLine", "IPriceFormatter",
    # Series types
    "AreaSeries", "BarSeries", "BaselineSeries", "CandlestickSeries",
    "HistogramSeries", "LineSeries",
    "AreaSeriesOptions", "BarSeriesOptions", "BaselineSeriesOptions",
    "CandlestickSeriesOptions", "HistogramSeriesOptions", "LineSeriesOptions",
    "SeriesType", "SeriesOptions", "SeriesPartialOptions",
    # Data types
    "BarData", "CandlestickData", "LineData", "AreaData", "HistogramData",
    "SingleValueData", "WhitespaceData", "OhlcData", "BusinessDay",
    "UTCTimestamp", "Time", "BarPrice", "Coordinate", "Logical",
    "LogicalRange", "TimeRange", "Range", "Point",
    # Options interfaces
    "ChartOptions", "ChartOptionsBase", "ChartOptionsImpl",
    "LayoutOptions", "GridOptions", "GridLineOptions",
    "CrosshairOptions", "CrosshairLineOptions",
    "TimeScaleOptions", "PriceScaleOptions", "PriceScaleMargins",
    "WatermarkOptions", "LocalizationOptions",
    "HandleScrollOptions", "HandleScaleOptions",
    "LineStyleOptions", "AreaStyleOptions", "BarStyleOptions",
    "BaselineStyleOptions", "CandlestickStyleOptions", "HistogramStyleOptions",
    "PriceFormat", "PriceFormatBuiltIn", "PriceFormatCustom",
    "PriceLineOptions", "SeriesMarker", "SeriesOptionsCommon",
    "SeriesOptionsMap", "SeriesPartialOptionsMap",
    # Enums
    "ColorType", "CrosshairMode", "LastPriceAnimationMode",
    "LineStyle", "LineType", "PriceLineSource", "PriceScaleMode",
    "TickMarkType", "TrackingModeExitMode", "MismatchDirection",
    # Type aliases
    "Background", "DeepPartial", "HorzAlign", "VertAlign", "LineWidth",
    "MouseEventHandler", "SizeChangeEventHandler",
    "LogicalRangeChangeEventHandler", "TimeRangeChangeEventHandler",
    "PriceFormatterFn", "TimeFormatterFn", "TickMarkFormatter",
    "AutoscaleInfoProvider", "OverlayPriceScaleOptions",
    "VisiblePriceScaleOptions",
    # v4.1+ plugin interfaces
    "IHorzScaleBehavior", "ICustomSeriesPaneView",
    "ICustomSeriesPaneRenderer", "ISeriesPrimitiveBase",
    "ISeriesPrimitivePaneView", "ISeriesPrimitivePaneRenderer",
    "ISeriesPrimitiveAxisView", "CustomData", "CustomBarItemData",
    "CustomStyleOptions", "customSeriesDefaultOptions",
    # Events
    "MouseEventParams", "TouchMouseEventData", "BarsInfo",
    "PaneSize", "PrimitiveHoveredItem", "SeriesAttachedParameter",
]

HOT_CACHE: dict[str, dict] = {}
_hot_cache_built: bool = False
_build_lock = asyncio.Lock()

_cache_hits: int = 0
_cache_misses: int = 0
_cache_counter_lock = threading.Lock()


async def build_hot_cache() -> bool:
    global _cache_hits, _cache_misses, _hot_cache_built
    if _hot_cache_built:
        return True
    async with _build_lock:
        if _hot_cache_built:
            return True
        logger.info("Building hot cache...")
        HOT_CACHE.clear()
        try:
            col = get_collection()
            count = 0
            dupes = 0

            for namespace in PRIORITY_NAMESPACES:
                try:
                    result = col.get(
                        where={"namespace": namespace},
                        include=["documents", "metadatas"],
                    )
                    for rid, doc, meta in zip(
                        result["ids"], result["documents"], result["metadatas"]
                    ):
                        key = (meta.get("name") or "").lower().strip()
                        if key:
                            if key in HOT_CACHE:
                                existing_doc = HOT_CACHE[key]["document"] or ""
                                if len(doc or "") > len(existing_doc):
                                    HOT_CACHE[key] = {"id": rid, "document": doc, "metadata": meta}
                                    dupes += 1
                            else:
                                HOT_CACHE[key] = {"id": rid, "document": doc, "metadata": meta}
                            count += 1
                except Exception as e:
                    logger.warning(
                        f"Hot cache: failed to load namespace '{namespace}': {e}"
                    )

            for name in PRIORITY_GLOBALS:
                try:
                    result = col.get(
                        where={"name": name},
                        include=["documents", "metadatas"],
                    )
                    if result["ids"]:
                        HOT_CACHE[name.lower()] = {
                            "id": result["ids"][0],
                            "document": result["documents"][0],
                            "metadata": result["metadatas"][0],
                        }
                        count += 1
                except Exception as e:
                    logger.debug(f"Hot cache load failed for '{name}': {e}")

            logger.info(
                f"Hot cache ready: {count} entries loaded, {len(HOT_CACHE)} unique keys ({dupes} key collisions)"
            )
            _hot_cache_built = True
            return True
        except Exception as e:
            logger.error(f"Failed to build hot cache: {e}")
            return False


def cache_lookup(name: str) -> Optional[dict]:
    global _cache_hits, _cache_misses
    key = name.lower().strip()
    entry = HOT_CACHE.get(key)
    if entry:
        with _cache_counter_lock:
            _cache_hits += 1
        return copy.deepcopy(entry)
    with _cache_counter_lock:
        _cache_misses += 1
    return None


async def ensure_hot_cache() -> None:
    await build_hot_cache()

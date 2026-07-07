# ruff: noqa: E501
"""
tools/lookup.py
LOOKUP tool: lwc_lookup - unified doc retrieval by name.
"""

from __future__ import annotations

from typing import Annotated, Literal

from fastmcp.exceptions import ToolError
from fastmcp.tools import tool
from loguru import logger
from mcp.types import ToolAnnotations
from pydantic import Field

import core.db as _db
from core.db import (
    get_by_names_async,
    query_async,
    search_by_name_async,
)
from core.hot_cache import cache_lookup, ensure_hot_cache
from formatters.entry import format_entry_detail, is_function_like
from formatters.errors import (
    cap_response,
    check_query_error,
    circuit_breaker_msg,
    norm_name,
    safe_error,
)

_Kind = Literal["function", "interface", "enumeration", "type-alias", "variable", "guide", "tutorial"]
_Version = Literal["3.8", "4.0", "4.1", "4.2", "5.0"]

_BUILTIN_TYPES = (
    "number, string, boolean, void, null, undefined, any, unknown, never, "
    "object, symbol, bigint, Date, Promise, Array, Record, Partial, DeepPartial"
)


def _pick_best_version(result: dict) -> tuple:
    candidates = list(zip(result.get("metadatas", [[]])[0] or [], result.get("documents", [[]])[0] or []))
    for meta, doc in candidates:
        if is_function_like(meta):
            meta = {**meta, "category": "function"}
            return meta, doc
    for meta, doc in candidates:
        syntax = meta.get("syntax") or ""
        if syntax:
            return meta, doc
    if candidates:
        best = max(candidates, key=lambda x: len(x[1]) if x[1] else 0)
        return best[0], best[1]
    return None, None


async def lookup_entry(name: str, category: str | None, version: _Version | None = None) -> str:
    try:
        await ensure_hot_cache()
        name_preserved = name.strip()
        name_lower = name.lower().strip()

        cached = cache_lookup(name)
        if cached:
            cached_cat = cached["metadata"].get("category")
            cached_syntax = cached["metadata"].get("syntax") or ""
            cached_ver = cached["metadata"].get("version", "")
            if (category and cached_cat != category) or not cached_syntax:
                pass
            elif version and cached_ver and version not in cached_ver:
                pass
            else:
                result = format_entry_detail(
                    cached["metadata"].get("name", name),
                    cached["metadata"],
                    cached["document"],
                )
                return cap_response(result)

        try:
            name_variants = list({name_preserved, name_lower})
            all_versions = await get_by_names_async(name_variants)
            if all_versions.get("ids"):
                for meta, doc in zip(
                    all_versions.get("metadatas", [])[0] or [],
                    all_versions.get("documents", [])[0] or [],
                ):
                    if not category or meta.get("category") == category:
                        if not version or version in (meta.get("version", "") or ""):
                            return cap_response(format_entry_detail(meta.get("name", name), meta, doc))
                best_meta, best_doc = _pick_best_version(all_versions)
                if best_meta:
                    if not version or version in (best_meta.get("version", "") or ""):
                        return cap_response(format_entry_detail(
                            best_meta.get("name", name), best_meta, best_doc
                        ))
        except Exception as e:
            logger.debug(f"Cross-category lookup failed: {e}")

        where = None
        if category and version:
            where = {"$and": [{"category": category}, {"version": version}]}
        elif category:
            where = {"category": category}
        elif version:
            where = {"version": version}

        candidates = await search_by_name_async(name, where=where)

        if candidates and candidates[0][0] >= 85:
            best_sim, best_entry = candidates[0]
            return cap_response(format_entry_detail(
                best_entry["metadata"].get("name", name),
                best_entry["metadata"],
                best_entry["document"],
            ))

        results = await query_async(name, 5, where=where)
        db_err = check_query_error(results)
        if db_err:
            return db_err
        if results["ids"] and results["ids"][0]:
            top_meta = results["metadatas"][0][0]
            top_dist = results["distances"][0][0]
            top_name = top_meta.get("name", "").lower().strip()
            search_name = name_lower
            name_match = search_name == top_name or (
                len(search_name) >= 3 and search_name in top_name
            )
            if name_match or top_dist < 0.35:
                return cap_response(format_entry_detail(
                    top_meta.get("name", name),
                    top_meta,
                    results["documents"][0][0],
                    top_dist,
                ))

        results = await query_async(name, 5)
        if results["ids"] and results["ids"][0]:
            top_meta = results["metadatas"][0][0]
            top_dist = results["distances"][0][0]
            top_name = top_meta.get("name", "").lower().strip()
            name_match = search_name == top_name or (
                len(search_name) >= 3 and search_name in top_name
            )
            if name_match or top_dist < 0.35:
                if not category or top_meta.get("category") == category:
                    if not version or version in (top_meta.get("version", "") or ""):
                        return cap_response(format_entry_detail(
                            top_meta.get("name", name),
                            top_meta,
                            results["documents"][0][0],
                            top_dist,
                        ))

        suggestions: list[str] = []
        if candidates:
            for sim, entry in candidates[:5]:
                suggestions.append(
                    f"  - {entry['metadata'].get('name', '?')} (similarity: {sim:.0f}%)"
                )
        else:
            all_candidates = await search_by_name_async(name)
            for sim, entry in all_candidates[:5]:
                suggestions.append(
                    f"  - {entry['metadata'].get('name', '?')} (similarity: {sim:.0f}%)"
                )

        cat_label = (category or "ENTRY").upper()
        ver_label = f" [{version}]" if version else ""
        if suggestions:
            return (
                f"{cat_label} '{name}'{ver_label} not found in the database.\n\n"
                f"Did you mean:\n" + "\n".join(suggestions)
            )
        return (
            f"{cat_label} '{name}'{ver_label} not found. Try lwc_search() for a broader search."
        )

    except ToolError:
        raise
    except Exception as e:
        logger.error(f"[lookup_entry] {e}")
        if _db._chroma_breaker.is_open():
            return circuit_breaker_msg()
        raise ToolError(safe_error(e, category or "lookup"))


@tool(
    annotations=ToolAnnotations(
        title="Lookup Lightweight Charts Entry",
        readOnlyHint=True,
        openWorldHint=False,
        idempotentHint=True,
    )
)
async def lwc_lookup(
    name: Annotated[
        str,
        Field(
            min_length=1,
            max_length=200,
            description=(
                "Exact symbol name. Examples: 'createChart', 'IChartApi', "
                "'ISeriesApi', 'CandlestickSeries', 'setData', 'addSeries'."
            ),
        ),
    ],
    kind: Annotated[
        _Kind | None,
        Field(
            default=None,
            description=(
                "Optional filter by entity kind. Leave unset (recommended) to "
                "auto-pick the richest doc across all kinds. "
                "Set explicitly to disambiguate: 'function' | 'interface' | "
                "'enumeration' | 'type-alias' | 'variable' | 'guide'."
            ),
        ),
    ] = None,
    version: Annotated[
        _Version | None,
        Field(
            default=None,
            description=(
                "Filter by version: '3.8', '4.0', '4.1', '4.2', '5.0'. "
                "Leave unset to search across all versions."
            ),
        ),
    ] = None,
) -> str:
    """
    Get complete documentation for a TradingView Lightweight Charts symbol by exact name.

    Returns full entry details: syntax, parameters, return type, remarks,
    and all code examples.

    WHEN TO USE:
      - You know the exact symbol name (e.g. 'createChart', 'IChartApi', 'addSeries').
      - You need the authoritative reference before writing code.

    WHEN NOT TO USE:
      - Fuzzy or conceptual searches -> use lwc_search().
      - Browsing every member of a namespace -> use lwc_browse().
    """
    try:
        canonical = norm_name(name)
        return await lookup_entry(canonical, kind, version)
    except ToolError:
        raise
    except Exception as e:
        logger.error(f"[lwc_lookup] {e}")
        if _db._chroma_breaker.is_open():
            return circuit_breaker_msg()
        raise ToolError(safe_error(e, "lwc_lookup"))

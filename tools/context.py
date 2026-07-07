# ruff: noqa: E501
"""
tools/context.py
BROWSE tool: lwc_browse - list every member of a namespace.
"""

from __future__ import annotations

from typing import Annotated, Literal, Optional

from fastmcp.exceptions import ToolError
from fastmcp.tools import tool
from loguru import logger
from mcp.types import ToolAnnotations
from pydantic import Field

import core.db as _db
from core.db import get_all_where_async
from core.hot_cache import ensure_hot_cache
from formatters.errors import (
    cap_response,
    circuit_breaker_msg,
    norm_ns,
    safe_error,
)

_Style = Literal["list", "cheatsheet"]
_Version = Literal["3.8", "4.0", "4.1", "4.2", "5.0"]

_CATEGORY_ORDER = [
    "function",
    "interface",
    "enumeration",
    "type-alias",
    "variable",
    "guide",
    "tutorial",
]

_LWC_NAMESPACES = (
    "enumerations, functions, interfaces, type-aliases, variables, "
    "getting-started, android, ios, price-scale, release-notes, "
    "series-types, time-scale, time-zones, migrations, plugins, "
    "customization, a11y, react, vuejs, webcomponents, "
    "how-to, demos"
)


def _render_list(
    ns: str, groups: dict[str, list[dict]], total: int
) -> str:
    output_lines: list[str] = [f"NAMESPACE: {ns} ({total} entries)", ""]

    for cat in _CATEGORY_ORDER:
        if cat not in groups:
            continue
        cat_entries = sorted(
            groups[cat], key=lambda e: e["metadata"].get("name", "")
        )
        output_lines.append(f"{cat.upper()}S ({len(cat_entries)}):")

        for entry in cat_entries:
            meta = entry["metadata"]
            name = meta.get("name", "?")
            syntax = meta.get("syntax") or ""
            returns = meta.get("returns") or ""
            desc = meta.get("raw_description", "")
            first_sentence = desc.split(".")[0][:100] if desc else ""

            if cat == "function":
                sig = syntax[:80] if syntax else name
                ret = f" -> {returns[:30]}" if returns else ""
                output_lines.append(f"  {sig}{ret}")
            else:
                desc_short = f" - {first_sentence}" if first_sentence else ""
                output_lines.append(f"  {name}{desc_short}")

        output_lines.append("")

    shown_cats = set(_CATEGORY_ORDER)
    remaining = {k: v for k, v in groups.items() if k not in shown_cats}
    if remaining:
        for cat in sorted(remaining):
            cat_entries = sorted(
                remaining[cat], key=lambda e: e["metadata"].get("name", "")
            )
            output_lines.append(f"{cat.upper()}S ({len(cat_entries)}):")
            for entry in cat_entries:
                name = entry["metadata"].get("name", "?")
                output_lines.append(f"  {name}")
            output_lines.append("")

    output_lines.append(f"Total: {total} entries in namespace '{ns}'")
    return "\n".join(output_lines)


def _render_cheatsheet(
    ns: str, groups: dict[str, list[dict]], total: int
) -> str:
    for cat in groups:
        groups[cat].sort(key=lambda e: e["metadata"].get("name", ""))

    lines = [
        f"{ns.upper()} CHEATSHEET ({total} entries)",
        "",
    ]

    for cat in _CATEGORY_ORDER:
        if cat not in groups:
            continue
        cat_entries = groups[cat]
        lines.append(f"{cat.upper()}S ({len(cat_entries)}):")
        for entry in cat_entries:
            meta = entry["metadata"]
            name = meta.get("name", "?")
            syntax = meta.get("syntax") or ""
            returns = meta.get("returns") or ""
            desc = meta.get("raw_description", "")
            first_sentence = desc.split(".")[0][:80] if desc else ""

            if cat == "function":
                sig = syntax[:70] if syntax else name
                ret = f" -> {returns[:25]}" if returns else ""
                lines.append(f"  {sig}{ret}")
            else:
                lines.append(f"  {name}")
            if first_sentence:
                lines.append(f"    {first_sentence}")
        lines.append("")

    shown_cats = set(_CATEGORY_ORDER)
    remaining = {k: v for k, v in groups.items() if k not in shown_cats}
    if remaining:
        for cat in sorted(remaining):
            cat_entries = remaining[cat]
            lines.append(f"{cat.upper()}S ({len(cat_entries)}):")
            for entry in cat_entries:
                name = entry["metadata"].get("name", "?")
                lines.append(f"  {name}")
            lines.append("")

    lines.append(f"Total: {total} entries in namespace '{ns}'")
    return "\n".join(lines)


@tool(
    annotations=ToolAnnotations(
        title="Browse Lightweight Charts Namespace",
        readOnlyHint=True,
        openWorldHint=False,
        idempotentHint=True,
    )
)
async def lwc_browse(
    namespace: Annotated[
        str,
        Field(
            min_length=1,
            max_length=50,
            description=(
                "Namespace to enumerate. Common values: 'enumerations', 'functions', "
                "'interfaces', 'type-aliases', 'variables', 'getting-started', "
                "'android', 'ios', 'price-scale', 'release-notes', 'series-types', "
                "'time-scale', 'time-zones', 'migrations', 'plugins', 'customization', "
                "'a11y', 'react', 'vuejs', 'webcomponents', 'how-to', 'demos'. "
                "Use 'global' for un-namespaced built-ins."
            ),
        ),
    ],
    category: Annotated[
        str | None,
        Field(
            default=None,
            max_length=50,
            description=(
                "Optional category filter: 'function' | 'interface' | "
                "'enumeration' | 'type-alias' | 'variable' | 'guide' | 'tutorial'. "
                "Leave unset to list every member."
            ),
        ),
    ] = None,
    style: Annotated[
        _Style,
        Field(
            default="list",
            description=(
                "Output format. 'list' (default) - plain-text, category-grouped, "
                "one-line descriptions. 'cheatsheet' - compact, box-drawn summary "
                "with every signature visible at a glance."
            ),
        ),
    ] = "list",
    version: Annotated[
        _Version | None,
        Field(
            default=None,
            description=(
                "Filter by version: '3.8', '4.0', '4.1', '4.2', '5.0'. "
                "Leave unset to list entries from all versions."
            ),
        ),
    ] = None,
) -> str:
    """
    Enumerate every member of a Lightweight Charts namespace.

    WHEN TO USE:
      - You want to scan *everything* a namespace offers before picking a symbol.
      - You're exploring an unfamiliar area (e.g. 'price-scale', 'series-types', 'customization').

    WHEN NOT TO USE:
      - You already know the exact symbol -> use lwc_lookup().
      - You're searching across namespaces by concept -> use lwc_search().
    """
    try:
        await ensure_hot_cache()
        ns = norm_ns(namespace)

        ns_value = ns if ns.lower() != "global" else ""
        where_clauses: list[dict] = [{"namespace": ns_value}]
        if category:
            where_clauses.append({"category": category})
        if version:
            where_clauses.append({"version": version})

        where: Optional[dict] = None
        if len(where_clauses) == 1:
            where = where_clauses[0]
        elif len(where_clauses) > 1:
            where = {"$and": where_clauses}

        entries = await get_all_where_async(where)
        if not entries:
            return (
                f"No entries found for namespace '{ns}'. "
                f"Check the namespace name and try again."
            )

        groups: dict[str, list[dict]] = {}
        for entry in entries:
            cat = entry["metadata"].get("category", "unknown")
            groups.setdefault(cat, []).append(entry)

        total = len(entries)
        if style == "cheatsheet":
            rendered = _render_cheatsheet(ns, groups, total)
        else:
            rendered = _render_list(ns, groups, total)

        return cap_response(rendered)

    except ToolError:
        raise
    except Exception as e:
        logger.error(f"[lwc_browse] {e}")
        if _db._chroma_breaker.is_open():
            return circuit_breaker_msg()
        raise ToolError(safe_error(e, "lwc_browse"))

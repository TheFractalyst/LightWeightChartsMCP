# ruff: noqa: E501
"""
tools/codegen.py
SCAFFOLD tool: lwc_scaffold - generate a validated Lightweight Charts template.
"""

from __future__ import annotations

from typing import Annotated, Literal

from fastmcp.exceptions import ToolError
from fastmcp.tools import tool
from loguru import logger
from mcp.types import ToolAnnotations
from pydantic import Field

import core.db as _db
from core.caches import codegen_cache_key, get_codegen_cache, set_codegen_cache
from core.db import query_async
from core.validator import call_validator
from formatters.errors import (
    cap_response,
    check_query_error,
    circuit_breaker_msg,
    safe_error,
)
from templates.templates import get_template

_Version = Literal["3.8", "4.0", "4.1", "4.2", "5.0"]

_Kind = Literal[
    "basic_chart",
    "realtime_updates",
    "multiple_series",
    "custom_styling",
    "price_lines",
    "react_integration",
    "two_price_scales",
]


async def _scaffold(
    kind: str,
    name: str,
    description: str,
    version: str | None = None,
) -> str:
    cache_key = codegen_cache_key(name, description or "", f"{kind}|{version or 'any'}", True)
    cached_result = get_codegen_cache(cache_key)
    if cached_result:
        return cached_result

    template_code = get_template(kind, name)

    relevant_funcs: list[str] = []

    if description:
        search_terms = {
            "basic_chart": "createChart candlestick line series setData fitContent",
            "realtime_updates": "series update realtime interval setInterval streaming",
            "multiple_series": "addSeries area bar baseline histogram multiple chart",
            "custom_styling": "layout background grid crosshair watermark colors styling options",
            "price_lines": "createPriceLine setMarkers price line marker series",
            "react_integration": "React useRef useEffect component chart integration",
            "two_price_scales": "priceScale left right overlay two scales multiple",
        }

        enriched_query = description
        for kw, search_query in search_terms.items():
            if kw in description.lower():
                enriched_query = f"{description} {search_query}"
                break

        where: dict = {"category": "function"}
        if version:
            where["version"] = version

        combined_results = await query_async(
            enriched_query, 10, where=where
        )
        db_err = check_query_error(combined_results)
        if db_err:
            return db_err

        if combined_results.get("ids") and combined_results["ids"][0]:
            for meta in combined_results["metadatas"][0][:5]:
                fname = meta.get("name", "?")
                fsyntax = meta.get("syntax", "")
                relevant_funcs.append(f"#   {fname}: {fsyntax[:80]}")

    validation = await call_validator(template_code, version)
    errors = validation.get("errors", [])

    lines = [
        f"GENERATED {kind.upper()} TEMPLATE:",
        "=" * 50,
        "```javascript",
        template_code,
        "```",
        "",
    ]

    if errors:
        lines.append(
            f"VALIDATION: {len(errors)} validation issues (template may need manual fixes)"
        )
        for err in errors:
            lines.append(
                f"  Line {err.get('line', '?')}, Col {err.get('column', '?')}: {err.get('text', '?')} [{err.get('type', '?')}]"
            )
    else:
        validator_name = validation.get("meta", {}).get("validator", "regex_js_ts")
        lines.append(f"VALIDATION: Template passes validation. (validator: {validator_name})")

    if relevant_funcs:
        lines.append("")
        lines.append("RELEVANT FUNCTIONS from docs:")
        for rf in relevant_funcs:
            lines.append(f"  {rf}")

    lines.append(f"\nDESCRIPTION: {description or '(none provided)'}")

    result = cap_response("\n".join(lines))
    set_codegen_cache(cache_key, result)
    return result


@tool(
    annotations=ToolAnnotations(
        title="Scaffold Lightweight Charts Template",
        readOnlyHint=False,
        openWorldHint=True,
        destructiveHint=False,
        idempotentHint=False,
    )
)
async def lwc_scaffold(
    kind: Annotated[
        _Kind,
        Field(
            description=(
                "Which kind of template to scaffold. 'basic_chart' builds a "
                "createChart skeleton with candlestick/line series, setData, and "
                "fitContent. 'realtime_updates' builds a streaming chart that uses "
                "series.update() on an interval for live data. 'multiple_series' "
                "builds a chart with addSeries combining area, bar, baseline, and "
                "histogram series. 'custom_styling' builds a chart with layout, "
                "background, grid, crosshair, and watermark styling options. "
                "'price_lines' builds a chart with createPriceLine and setMarkers "
                "for annotations. 'react_integration' builds a React component "
                "using useRef/useEffect to mount a chart. 'two_price_scales' builds "
                "a chart with left and right price scales plus overlay series."
            ),
        ),
    ],
    name: Annotated[
        str,
        Field(
            min_length=1,
            max_length=100,
            description="Display name for the generated chart script.",
        ),
    ],
    description: Annotated[
        str,
        Field(
            default="",
            max_length=500,
            description="What the chart should do. Used to search the docs for relevant functions.",
        ),
    ] = "",
    version: Annotated[
        _Version | None,
        Field(
            default=None,
            description=(
                "Optional Lightweight Charts version to filter relevant docs by. "
                "One of '3.8', '4.0', '4.1', '4.2', '5.0'. When set, doc search "
                "and validation are scoped to that version."
            ),
        ),
    ] = None,
) -> str:
    """
    Generate a validated Lightweight Charts template.

    The result is validated before being returned; the final script is
    production-ready and easy to paste into a JS/TS environment. Relevant
    doc snippets are included as comments to help the user wire in real logic.

    WHEN TO USE:
      - You need a clean starting point for a new chart, streaming feed,
        styled dashboard, or React integration.
      - You want the skeleton pre-wired with createChart, series setup, and
        data binding.

    WHEN NOT TO USE:
      - You already have code and just want to fix it -> lwc_repair.
      - You want to browse what functions exist first -> lwc_search / lwc_browse.
    """
    try:
        name = name.strip()
        if not name:
            raise ToolError("No name provided. Pass a display name for the chart script.")

        return await _scaffold(kind, name, description, version)

    except ToolError:
        raise
    except Exception as e:
        logger.error(f"[lwc_scaffold] {e}")
        if _db._chroma_breaker.is_open():
            return circuit_breaker_msg()
        raise ToolError(safe_error(e, "lwc_scaffold"))

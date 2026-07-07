# ruff: noqa: E501
"""
tools/validation.py
VALIDATE / REPAIR tools (2):
  - lwc_validate  - validate JavaScript/TypeScript syntax for Lightweight Charts code
  - lwc_repair    - fix common Lightweight Charts issues in JavaScript/TypeScript code
"""

from __future__ import annotations

import os
import re
import time
from typing import Annotated

from fastmcp.exceptions import ToolError
from fastmcp.tools import tool
from loguru import logger
from mcp.types import ToolAnnotations
from pydantic import Field

import core.db as _db
from core.caches import get_cached_file_validation, set_cached_file_validation
from core.config import _ALLOWED_BASE_DIRS, _TRANSPORT
from core.validator import call_validator, enrich_error_with_code
from formatters.errors import (
    cap_response,
    safe_error,
    strip_string_literals,
)
from tools.lookup import lookup_entry

_EXPLAIN_LOOKUP_TIMEOUT_S = max(1, int(os.getenv("LWC_EXPLAIN_LOOKUP_TIMEOUT", "2")))
_EXPLAIN_MAX_DOC_LOOKUPS = max(1, int(os.getenv("LWC_EXPLAIN_MAX_DOC_LOOKUPS", "8")))

_LWC_SIGNATURES = re.compile(
    r"(createChart)"
    r"|(addSeries)"
    r"|(addCandlestickSeries|addLineSeries|addAreaSeries|addBarSeries|addBaselineSeries|addHistogramSeries)"
    r"|(IChartApi|ISeriesApi|ITimeScaleApi|IPriceScaleApi)"
    r"|(CandlestickSeries|LineSeries|AreaSeries|BarSeries|BaselineSeries|HistogramSeries)"
    r"|(setData|\.update\()"
    r"|(fitContent|timeScale)"
    r"|(applyOptions|priceScale|createPriceLine|setMarkers)"
    r"|(lightweight-charts)"
    r"|(subscribeCrosshairMove|subscribeClick)"
    r"|(removeSeries|resize|remove\(\))"
)
_LWC_HEADER_LINES = 20


def _is_lwc_content(resolved_path: str, max_lines: int = _LWC_HEADER_LINES) -> bool:
    try:
        with open(resolved_path, "r", encoding="utf-8", errors="replace") as f:
            for i, line in enumerate(f):
                if i >= max_lines:
                    break
                if _LWC_SIGNATURES.search(line):
                    return True
    except (OSError, UnicodeDecodeError):
        return False
    return False


def _has_lwc_extension(path: str) -> bool:
    return path.endswith((".js", ".ts", ".jsx", ".tsx", ".mjs"))


def _resolve_file(file_path: str) -> tuple[str, str]:
    if not file_path:
        raise ToolError("No file path provided. Provide an absolute path to a JavaScript/TypeScript file.")

    try:
        resolved = os.path.realpath(file_path)
    except Exception:
        raise ToolError(
            "Invalid path provided. Could not resolve the file path. "
            "Please provide a valid absolute path."
        )

    if not any(resolved.startswith(d) for d in _ALLOWED_BASE_DIRS):
        raise ToolError(
            "File path is outside allowed directories. "
            "Provide a path under your home or Documents directory."
        )

    display_name = os.path.basename(resolved)

    if not os.path.isfile(resolved):
        raise ToolError(f"File not found: {display_name}")

    if not _has_lwc_extension(resolved):
        if not _is_lwc_content(resolved):
            raise ToolError(
                "File does not appear to be a Lightweight Charts script. "
                "Provide a .js/.ts/.jsx/.tsx/.mjs file or a file containing "
                "'lightweight-charts', 'createChart', 'addSeries', or 'CandlestickSeries'."
            )

    return resolved, display_name


def _render_success_summary(code: str) -> str:
    code_lines = code.strip().splitlines()
    has_lwc_import = any("lightweight-charts" in line for line in code_lines)
    has_create_chart = any("createChart" in line for line in code_lines)
    has_add_series = any("addSeries" in line for line in code_lines)
    has_set_data = any("setData" in line for line in code_lines)
    has_fit_content = any("fitContent" in line for line in code_lines)

    imports = [
        line.strip() for line in code_lines
        if line.strip().startswith("import ") or "require(" in line.strip()
    ]

    analysis = [f"Lines: {len(code_lines)}"]
    if has_lwc_import:
        analysis.append("Has lightweight-charts import")
    if has_create_chart:
        analysis.append("Has createChart usage")
    if has_add_series:
        analysis.append("Has addSeries usage")
    if has_set_data:
        analysis.append("Has setData usage")
    if has_fit_content:
        analysis.append("Has fitContent usage")
    if imports:
        analysis.append(f"Imports: {len(imports)}")

    return "\n".join(f"  {a}" for a in analysis)


async def _render_errors(errors: list, warnings: list, explain: bool) -> list[str]:
    lines: list[str] = []
    explain_lookups_done = 0
    for i, err in enumerate(errors, 1):
        line_num = err.get("line", "?")
        col_num = err.get("column", "?")
        text = err.get("text", "Unknown error")
        err_type = err.get("type", "error").upper()
        lines.append(f"  ERROR {i} - Line {line_num}, Col {col_num} [{err_type}]")
        lines.append(f"    {text}")

        if explain and explain_lookups_done < _EXPLAIN_MAX_DOC_LOOKUPS:
            import asyncio
            name_match = re.search(r"'(\w+)'", text)
            if name_match:
                extracted_name = name_match.group(1)
                try:
                    doc_result = await asyncio.wait_for(
                        lookup_entry(extracted_name, None),
                        timeout=float(_EXPLAIN_LOOKUP_TIMEOUT_S),
                    )
                    if "not found" not in doc_result[:80].lower():
                        doc_lines = doc_result.splitlines()[:5]
                        lines.append(f"    Docs lookup for '{extracted_name}':")
                        for dl in doc_lines:
                            lines.append(f"      {dl}")
                    else:
                        lines.append(
                            f"    Docs lookup for '{extracted_name}': "
                            "not found (may be misspelled)"
                        )
                except asyncio.TimeoutError:
                    lines.append(
                        f"    Docs lookup for '{extracted_name}': timeout "
                        f"({_EXPLAIN_LOOKUP_TIMEOUT_S}s)"
                    )
                explain_lookups_done += 1

        lines.append("")

    for i, warn in enumerate(warnings, 1):
        line_num = warn.get("line", "?")
        col_num = warn.get("column", "?")
        text = warn.get("text", "Unknown warning")
        lines.append(f"  WARNING {i} - Line {line_num}, Col {col_num}")
        lines.append(f"    {text}")
        lines.append("")

    return lines


@tool(
    annotations=ToolAnnotations(
        title="Validate Lightweight Charts Code",
        readOnlyHint=True,
        openWorldHint=True,
        idempotentHint=True,
    )
)
async def lwc_validate(
    code: Annotated[
        str | None,
        Field(
            default=None,
            min_length=1,
            max_length=500_000,
            description=(
                "Complete JavaScript/TypeScript source code using Lightweight Charts APIs to validate. "
                "Pass EITHER `code` OR `file_path`, not both. Use this for inline code. "
                "For files >500KB, use `file_path` + `file_content` instead."
            ),
        ),
    ] = None,
    file_path: Annotated[
        str | None,
        Field(
            default=None,
            min_length=1,
            max_length=4096,
            description=(
                "Absolute path to a JavaScript/TypeScript file (.js/.ts/.jsx/.tsx/.mjs). "
                "Pass EITHER `code` OR `file_path`, not both. Use this for scripts hosted "
                "on the same machine as this MCP server. Result is cached by "
                "(path, mtime, size) for sub-millisecond re-validation."
            ),
        ),
    ] = None,
    file_content: Annotated[
        str | None,
        Field(
            default=None,
            min_length=1,
            max_length=2_000_000,
            description=(
                "Remote-safe file payload. Use this when `file_path` points to "
                "a client-side path not reachable by the server. Can be used "
                "alone or with `file_path` as a display label. Cannot be "
                "combined with `code`."
            ),
        ),
    ] = None,
    explain: Annotated[
        bool,
        Field(
            default=False,
            description=(
                "When true, each validation error is cross-referenced against "
                "the Lightweight Charts documentation and the matching doc entry is "
                "embedded inline. Use this while debugging; leave false for "
                "fast pre-commit validation."
            ),
        ),
    ] = False,
    version: Annotated[
        str | None,
        Field(
            default=None,
            description=(
                "Lightweight Charts version target (e.g. '4', '5'). "
                "Affects deprecated API detection. Defaults to any."
            ),
        ),
    ] = None,
) -> str:
    """
    Validate Lightweight Charts JavaScript/TypeScript code and return a diagnostic report.

    Validation uses regex-based JS/TS parsing and checks for common Lightweight Charts
    issues:
      - JS/TS syntax errors (unbalanced braces/parens)
      - Missing lightweight-charts imports
      - Deprecated v3 API methods (addCandlestickSeries, addLineSeries, etc.)
      - Missing createChart() when chart methods are used
      - setData() without fitContent()
      - Real-time update patterns using setData instead of update()

    WHEN TO USE:
      - Before suggesting code to the user, to catch errors proactively.
      - To confirm an edit still passes syntax validation.
      - With `explain=True` to debug a failing script alongside doc references.
      - With `file_path=...` for scripts available on the server host (stdio only).
      - With `file_path` + `file_content` for remote clients over SSE/HTTP.

    WHEN NOT TO USE:
      - You already know a specific error and want an auto-fix -> lwc_repair.
      - You want to generate a fresh template from scratch -> lwc_scaffold.
    """
    if file_content is not None and code is not None:
        raise ToolError(
            "Pass exactly one input mode: either `code`, or `file_content` "
            "(optionally with `file_path` as a label), not both."
        )
    if code is not None and file_path is not None:
        raise ToolError(
            "Pass exactly one input mode: either `code`, or `file_path` "
            "(optionally with `file_content`), not both."
        )
    if code is None and file_path is None and file_content is None:
        raise ToolError("No input provided. Pass one of: `code`, `file_path`, or `file_content`.")

    try:
        display_header: str | None = None
        cache_key: tuple | None = None

        if file_path is not None:
            if file_content is not None:
                display_name = os.path.basename(file_path.strip()) or file_path.strip()
                file_code = file_content
                file_size = len(file_code.encode("utf-8"))
                line_count = file_code.count("\n") + 1
                display_header = (
                    f"FILE: {display_name}\n"
                    f"Size: {file_size:,} bytes | Lines: {line_count:,}\n"
                    + "=" * 80 + "\n"
                )
                code = file_code
            else:
                if _TRANSPORT in ("http", "sse") and not os.path.isfile(file_path):
                    raise ToolError(
                        f"Remote server cannot access file '{os.path.basename(file_path)}'. "
                        "Remote SSE/HTTP clients must pass file_content alongside file_path, "
                        "or use file_content alone. Example: file_path='chart.js', "
                        "file_content='<your code>'."
                    )
                resolved, display_name = _resolve_file(file_path)
                stat = os.stat(resolved)
                mtime_ns = stat.st_mtime_ns
                fsize = stat.st_size

                cached = get_cached_file_validation(resolved, mtime_ns, fsize)
                if cached:
                    return cached

                with open(resolved, "r", encoding="utf-8", errors="replace") as f:
                    file_code = f.read()

                file_size = len(file_code.encode("utf-8"))
                line_count = file_code.count("\n") + 1
                display_header = (
                    f"FILE: {display_name}\n"
                    f"Size: {file_size:,} bytes | Lines: {line_count:,}\n"
                    + "=" * 80 + "\n"
                )
                cache_key = (resolved, mtime_ns, fsize)
                code = file_code

        elif file_content is not None:
            first_line = file_content.strip().splitlines()[0][:60] if file_content.strip() else ""
            if first_line.startswith("#"):
                display_name = first_line.lstrip("# ").strip()
            else:
                display_name = f"remote_{int(time.time())}"
            file_size = len(file_content.encode("utf-8"))
            line_count = file_content.count("\n") + 1
            display_header = (
                f"FILE: {display_name}\n"
                f"Size: {file_size:,} bytes | Lines: {line_count:,}\n"
                + "=" * 80 + "\n"
            )
            code = file_content

        assert code is not None
        code = code.strip()
        if not code:
            return "ERROR: No code provided. Pass the complete JavaScript/TypeScript source code."

        result = await call_validator(code, version)

        errors = enrich_error_with_code(result.get("errors", []), code)
        warnings = result.get("warnings", [])
        success = result.get("success", False)
        meta = result.get("meta", {})

        if success and not errors:
            validator_name = meta.get("validator", "regex_js_ts")
            analysis_block = _render_success_summary(code)

            if warnings:
                warning_lines = await _render_errors([], warnings, explain=False)
                response = (
                    (display_header or "")
                    + f"VALID - Code passes validation with warnings.\n"
                    f"Validator: {validator_name}\n"
                    f"Errors: 0 | Warnings: {len(warnings)}\n\n"
                    f"Code Analysis:\n{analysis_block}\n\n"
                    + "\n".join(warning_lines)
                )
            else:
                response = (
                    (display_header or "")
                    + f"VALID - Code passes validation successfully.\n"
                    f"Validator: {validator_name}\n"
                    f"Errors: 0 | Warnings: 0\n\n"
                    f"Code Analysis:\n{analysis_block}"
                )
            capped = cap_response(response)
            if cache_key:
                set_cached_file_validation(*cache_key, capped)
            return capped

        total_issues = len(errors) + len(warnings)
        validator_name = meta.get("validator", "regex_js_ts")

        lines: list[str] = []
        if display_header:
            lines.append(display_header.rstrip())

        if explain:
            lines.append("VALIDATION + DEBUG REPORT")
            lines.append("=" * 50)
            lines.append(f"Validator: {validator_name}")
            lines.append(f"Errors: {len(errors)} | Warnings: {len(warnings)}")
            lines.append("")
        else:
            lines.append(f"VALIDATION ISSUES ({total_issues}):")
            lines.append(f"Validator: {validator_name}")
            lines.append(f"Errors: {len(errors)} | Warnings: {len(warnings)}")
            lines.append("")

        lines.extend(await _render_errors(errors, warnings, explain))

        rendered = cap_response("\n".join(lines))
        if cache_key:
            set_cached_file_validation(*cache_key, rendered)
        return rendered

    except ToolError:
        raise
    except Exception as e:
        logger.error(f"[lwc_validate] {e}")
        raise ToolError(safe_error(e, "lwc_validate"))


_LWC_FIX_PATTERNS: list[tuple[str, str, str]] = []


async def _repair_targeted(code: str, context: str, version: str | None = None) -> str:
    fixed_code = code
    fixes_list: list[str] = []

    code_stripped = strip_string_literals(fixed_code)
    for pattern, replacement, description in _LWC_FIX_PATTERNS:
        if re.search(pattern, code_stripped):
            fixed_code = re.sub(pattern, replacement, fixed_code)
            fixes_list.append(description)
            code_stripped = strip_string_literals(fixed_code)

    if "from 'lightweight-charts'" not in fixed_code and 'from "lightweight-charts"' not in fixed_code:
        if "createChart" in fixed_code or "addSeries" in fixed_code:
            first_line_end = fixed_code.find("\n")
            if first_line_end != -1:
                fixed_code = (
                    fixed_code[:first_line_end + 1]
                    + "import { createChart } from 'lightweight-charts';\n"
                    + fixed_code[first_line_end + 1:]
                )
                fixes_list.append("Added import for lightweight-charts")

    # Fix deprecated v3 methods
    deprecated_map = {
        "addCandlestickSeries": "chart.addSeries(CandlestickSeries)",
        "addLineSeries": "chart.addSeries(LineSeries)",
        "addAreaSeries": "chart.addSeries(AreaSeries)",
        "addBarSeries": "chart.addSeries(BarSeries)",
        "addBaselineSeries": "chart.addSeries(BaselineSeries)",
        "addHistogramSeries": "chart.addSeries(HistogramSeries)",
    }
    for old_method, new_call in deprecated_map.items():
        pattern = r'\b' + old_method + r'\s*\('
        if re.search(pattern, fixed_code):
            fixed_code = re.sub(pattern + r'', new_call + '(', fixed_code)
            fixes_list.append(f"Replaced deprecated {old_method}() with {new_call}()")

    validation_result = None
    if fixed_code != code:
        try:
            fix_validation = await call_validator(fixed_code, version)
            if fix_validation.get("success"):
                validation_result = "Fixed code passes validation successfully"
            else:
                errs = fix_validation.get("errors", [])
                if errs:
                    validation_result = (
                        f"Fixed code still has {len(errs)} error(s):\n"
                        + "\n".join(f"  Line {e.get('line', '?')}: {e.get('text', '?')}" for e in errs[:3])
                    )
                else:
                    validation_result = "Fixed code passes validation (warnings only)"
        except Exception:
            validation_result = "Could not validate fix"

    doc_context = ""
    identifier_match = re.search(r"'(\w+)'", context)
    if identifier_match:
        identifier = identifier_match.group(1)
        try:
            from core.hot_cache import cache_lookup
            cached_entry = cache_lookup(identifier)
            if cached_entry:
                doc = cached_entry.get("document", "")
                doc_context = (
                    f"\nDOC REFERENCE for '{identifier}':\n{doc[:300]}"
                )
        except Exception as e:
            logger.debug(f"Doc lookup for fix failed: {e}")

    fix_applied = " | ".join(fixes_list) if fixes_list else "No automatic fix available"

    lines = [
        "REPAIR REPORT (targeted)",
        "=" * 50,
        f"Error: {context}",
        "",
        f"Fix Applied: {fix_applied}",
    ]
    if doc_context:
        lines.append(doc_context)
    if validation_result:
        lines.extend(["", validation_result])
    if fixed_code != code:
        lines.extend(["", "FIXED CODE:", "```javascript", fixed_code, "```"])

    return cap_response("\n".join(lines))


@tool(
    annotations=ToolAnnotations(
        title="Repair Lightweight Charts Code",
        readOnlyHint=False,
        openWorldHint=True,
        destructiveHint=False,
        idempotentHint=False,
    )
)
async def lwc_repair(
    code: Annotated[
        str,
        Field(
            min_length=1,
            max_length=500_000,
            description="The JavaScript/TypeScript code using Lightweight Charts APIs to repair (full script or a snippet).",
        ),
    ],
    context: Annotated[
        str,
        Field(
            min_length=1,
            max_length=500,
            description=(
                "The validation error message or a short description of "
                "the problem to fix."
            ),
        ),
    ],
    version: Annotated[
        str | None,
        Field(
            default=None,
            description=(
                "Lightweight Charts version target (e.g. '4', '5'). "
                "Passed to the validator when re-checking the fixed code. "
                "Defaults to any."
            ),
        ),
    ] = None,
) -> str:
    """
    Repair Lightweight Charts JavaScript/TypeScript code.

    Applies common fixes for Lightweight Charts issues:
      - Missing import for lightweight-charts
      - Deprecated v3 API methods (addCandlestickSeries, addLineSeries, etc.)

    WHEN TO USE:
      - A validation fails and you need the change to make it pass.

    WHEN NOT TO USE:
      - You just want to know *if* code is valid -> lwc_validate.
      - You're writing fresh code from a prompt -> lwc_scaffold.
    """
    try:
        code_stripped = code.strip()
        context_stripped = context.strip()
        if not code_stripped:
            raise ToolError("No code provided. Pass the JavaScript/TypeScript source to repair.")
        if not context_stripped:
            raise ToolError(
                "No context provided. Describe the error to fix."
            )

        return await _repair_targeted(code_stripped, context_stripped, version)

    except ToolError:
        raise
    except Exception as e:
        logger.error(f"[lwc_repair] {e}")
        if _db._chroma_breaker.is_open():
            from formatters.errors import circuit_breaker_msg
            return circuit_breaker_msg()
        raise ToolError(safe_error(e, "lwc_repair"))

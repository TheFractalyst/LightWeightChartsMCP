# ruff: noqa: E501
"""
core/validator.py
Regex-based JS/TS validation for TradingView Lightweight Charts code.
No Node.js runtime required - uses pattern matching for common mistakes.
"""

from __future__ import annotations

import json
import re
import threading
import time

from loguru import logger

from core.caches import (
    get_cached_validation,
    set_cached_validation,
)


# Circuit breaker for validator
class ValidatorCircuitBreaker:
    def __init__(self, threshold: int = 3, cooldown: int = 30):
        self.failures = 0
        self.threshold = threshold
        self.cooldown = cooldown
        self.open_until = 0.0
        self._lock = threading.Lock()

    def is_open(self) -> bool:
        with self._lock:
            if self.open_until and time.time() > self.open_until:
                self.failures = 0
                self.open_until = 0.0
            return time.time() < self.open_until

    def record_failure(self) -> None:
        with self._lock:
            self.failures += 1
            if self.failures >= self.threshold:
                self.open_until = time.time() + self.cooldown
                logger.error(f"Validator circuit OPEN - cooldown {self.cooldown}s")

    def record_success(self) -> None:
        with self._lock:
            if self.failures:
                self.failures = 0
                self.open_until = 0.0

validator_cb = ValidatorCircuitBreaker(threshold=3, cooldown=30)

# Deprecated v3 API methods (removed in v4)
_DEPRECATED_V3_METHODS = [
    "addCandlestickSeries", "addLineSeries", "addAreaSeries",
    "addBarSeries", "addBaselineSeries", "addHistogramSeries",
]

# Required imports
_LWC_IMPORT_PATTERN = re.compile(
    r"from\s+['\"]lightweight-charts['\"]"
    r"|import\s+['\"]lightweight-charts['\"]"
    r"|require\s*\(\s*['\"]lightweight-charts['\"]"
)

# createChart call pattern
_CREATE_CHART_PATTERN = re.compile(r"\bcreateChart\s*\(")

# Series method patterns
_SERIES_METHOD_PATTERN = re.compile(r"\.(setData|update|setMarkers|createPriceLine|applyOptions|priceToCoordinate|coordinateToPrice)\s*\(")

# Chart method patterns
_CHART_METHOD_PATTERN = re.compile(r"\.(addSeries|removeSeries|priceScale|timeScale|applyOptions|resize|remove|subscribeCrosshairMove|subscribeClick|unsubscribeCrosshairMove|unsubscribeClick)\s*\(")


def _check_brace_balance(code: str) -> list[dict]:
    """Check for balanced braces and parentheses."""
    errors = []
    stack = []
    pairs = {')': '(', '}': '{', ']': '['}
    openers = '({['
    closers = ')}]'
    in_string = False
    string_char = None
    in_comment = False
    in_line_comment = False

    for i, ch in enumerate(code):
        if in_line_comment:
            if ch == '\n':
                in_line_comment = False
            continue
        if in_comment:
            if ch == '*' and i + 1 < len(code) and code[i + 1] == '/':
                in_comment = False
            continue
        if in_string:
            if ch == string_char and (i == 0 or code[i - 1] != '\\'):
                in_string = False
            continue
        if ch == '/' and i + 1 < len(code):
            if code[i + 1] == '/':
                in_line_comment = True
                continue
            if code[i + 1] == '*':
                in_comment = True
                continue
        if ch in '"\'`':
            in_string = True
            string_char = ch
            continue
        if ch in openers:
            stack.append((ch, i))
        elif ch in closers:
            if not stack:
                errors.append({
                    "line": code[:i].count('\n') + 1,
                    "column": i,
                    "text": f"Unmatched closing '{ch}'",
                    "type": "error",
                })
            elif stack[-1][0] != pairs[ch]:
                errors.append({
                    "line": code[:i].count('\n') + 1,
                    "column": i,
                    "text": f"Mismatched '{stack[-1][0]}' and '{ch}'",
                    "type": "error",
                })
            else:
                stack.pop()

    for ch, pos in stack:
        errors.append({
            "line": code[:pos].count('\n') + 1,
            "column": pos,
            "text": f"Unclosed '{ch}'",
            "type": "error",
        })

    return errors


def _check_lwc_specific(code: str, version: str | None = None) -> list[dict]:
    """Check for common Lightweight Charts mistakes. Returns warnings list."""
    warnings = []

    has_lwc_import = bool(_LWC_IMPORT_PATTERN.search(code))
    has_create_chart = bool(_CREATE_CHART_PATTERN.search(code))
    has_series_methods = bool(_SERIES_METHOD_PATTERN.search(code))
    has_chart_methods = bool(_CHART_METHOD_PATTERN.search(code))

    # Missing import
    if (has_create_chart or has_series_methods or has_chart_methods) and not has_lwc_import:
        warnings.append({
            "line": 0, "column": 0,
            "text": "Lightweight Charts API usage detected but no import statement found. "
                    "Add: import { createChart } from 'lightweight-charts';",
            "type": "warning",
        })

    # Deprecated v3 methods
    for method in _DEPRECATED_V3_METHODS:
        if re.search(r'\b' + method + r'\s*\(', code):
            v_msg = f". In v4+, use chart.addSeries({method.replace('add', '').replace('Series', 'Series')}) instead."
            warnings.append({
                "line": 0, "column": 0,
                "text": f"Deprecated method '{method}()' found. This was removed in v4.{v_msg}",
                "type": "warning",
            })

    # Missing createChart when chart methods used
    if has_chart_methods and not has_create_chart:
        warnings.append({
            "line": 0, "column": 0,
            "text": "Chart methods detected but no createChart() call found. "
                    "Create a chart first: const chart = createChart(container);",
            "type": "warning",
        })

    # setData without fitContent
    has_set_data = re.search(r'\.setData\s*\(', code) is not None
    has_fit_content = re.search(r'\.fitContent\s*\(', code) is not None
    if has_set_data and not has_fit_content:
        warnings.append({
            "line": 0, "column": 0,
            "text": "setData() called but fitContent() not found. "
                    "Call chart.timeScale().fitContent() after setData() to fit the view.",
            "type": "warning",
        })

    # Using setData for real-time updates
    if re.search(r'interval|setInterval|setTimeout|requestAnimationFrame', code) and has_set_data:
        warnings.append({
            "line": 0, "column": 0,
            "text": "Real-time update pattern detected (interval/timeout) but setData() used. "
                    "Use series.update() for real-time updates instead of setData() for better performance.",
            "type": "warning",
        })

    return warnings


def _validate_js_syntax(code: str, version: str | None = None) -> dict:
    """Validate JS/TS code using regex patterns."""
    errors = []
    warnings = []

    # Brace balance check
    brace_errors = _check_brace_balance(code)
    errors.extend(brace_errors)

    # LWC-specific checks
    lwc_warnings = _check_lwc_specific(code, version)
    warnings.extend(lwc_warnings)

    success = len(errors) == 0

    return {
        "success": success,
        "errors": errors,
        "warnings": warnings,
        "meta": {
            "validator": "regex_js_ts",
            "version": version or "any",
        },
    }


async def call_validator(code: str, version: str | None = None) -> dict:
    """Run validation on code with caching."""
    import asyncio

    cache_key = f"{hash(code)}|{version or 'any'}"
    cached = get_cached_validation(cache_key)
    if cached is not None:
        return cached

    try:
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(None, _validate_js_syntax, code, version)
        validator_cb.record_success()
        set_cached_validation(cache_key, json.dumps(result))
        return result
    except Exception as e:
        validator_cb.record_failure()
        logger.error(f"[validator] Validation failed: {e}")
        return {
            "success": False,
            "errors": [{"line": 0, "column": 0, "text": str(e), "type": "error"}],
            "warnings": [],
            "meta": {"validator": "regex_js_ts", "error": True},
        }


def enrich_error_with_code(errors: list[dict], code: str) -> list[dict]:
    """Add code context to errors."""
    lines = code.split('\n')
    enriched = []
    for err in errors:
        enriched_err = err.copy()
        line_num = err.get('line', 0)
        if 0 < line_num <= len(lines):
            enriched_err['code_line'] = lines[line_num - 1].strip()
        enriched.append(enriched_err)
    return enriched

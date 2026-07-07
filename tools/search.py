# ruff: noqa: E501
"""
tools/search.py
SEARCH tool: lwc_search - unified semantic discovery.
"""

from __future__ import annotations

import re
from typing import Annotated, Literal, Optional

import xxhash
from fastmcp.exceptions import ToolError
from fastmcp.tools import tool
from loguru import logger
from mcp.types import ToolAnnotations
from pydantic import Field

import core.db as _db
from core.db import query_async
from core.hot_cache import ensure_hot_cache
from formatters.entry import (
        format_examples_text,
    format_params_text,
    is_function_like,
        relevance_pct,
    )
from formatters.errors import (
    cap_response,
    check_query_error,
    circuit_breaker_msg,
    safe_error,
)


def _return_type_matches(query_type: str, field_type: str) -> bool:
    ft = field_type.lower()
    if query_type == ft:
        return True
    if query_type in ft:
        pattern = rf"(?:^|[\s<>,\[\]]){re.escape(query_type)}(?:$|[\s<>,\[\]])"
        return bool(re.search(pattern, ft))
    if ft in query_type:
        return True
    return False


async def _short_query_search(
    query: str,
    n_results: int,
    category_filter: str | None,
    namespace_filter: str | None,
    version_filter: str | None,
) -> str:
    from core.db import search_by_name_async

    candidates = await search_by_name_async(query)
    if not candidates:
        return f"No results found for '{query}'. Try a longer search term."

    filtered = []
    for sim, entry in candidates:
        meta = entry["metadata"]
        if category_filter and meta.get("category") != category_filter:
            continue
        if namespace_filter and meta.get("namespace") != namespace_filter:
            continue
        if version_filter and version_filter not in (meta.get("version", "") or ""):
            continue
        filtered.append((sim, entry))

    if not filtered:
        return f"No results found for '{query}' with the given filters."

    output_lines: list[str] = []
    for i, (sim, entry) in enumerate(filtered[:n_results]):
        meta = entry["metadata"]
        name = meta.get("name", "?")
        category = meta.get("category", "?").upper()
        namespace = meta.get("namespace") or ""
        ns = f"{namespace}." if namespace and not name.startswith(f"{namespace}.") else ""
        desc = meta.get("raw_description", "")
        first_para = desc.split("\n\n")[0][:200] if desc else ""

        output_lines.append("---")
        output_lines.append(f"[{i + 1}] {ns}{name} | {category} | Match: {sim:.0f}%")
        if first_para:
            output_lines.append(f"  {first_para}")

    output_lines.append("---")
    return cap_response("\n".join(output_lines))


async def _examples_branch(query: str, n_results: int, version_filter: str | None) -> str:
    where: dict = {"has_examples": 1}
    if version_filter:
        where = {"$and": [where, {"version": version_filter}]}
    results = await query_async(query, n_results, where=where)
    db_err = check_query_error(results)
    if db_err:
        return db_err
    if not results["ids"] or not results["ids"][0]:
        return f"No examples found for '{query}'. Try a different search term."

    filtered = [
        (meta, doc, dist)
        for meta, doc, dist in zip(
            results["metadatas"][0],
            results["documents"][0],
            results["distances"][0],
        )
        if dist < 0.7
    ]
    if not filtered:
        return f"No relevant examples found for '{query}'. Try a different search term."

    output_lines: list[str] = []
    for meta, doc, dist in filtered:
        name = meta.get("name", "?")
        category = meta.get("category", "?").upper()
        namespace = meta.get("namespace") or ""
        ns = f"{namespace}." if namespace and not name.startswith(f"{namespace}.") else ""
        rel = relevance_pct(dist)

        output_lines.append("---")
        output_lines.append(
            f"EXAMPLES from: {ns}{name} ({category}) - Relevance: {rel}"
        )

        ex_text = format_examples_text(meta)
        if ex_text:
            output_lines.append(ex_text)
        else:
            output_lines.append(
                "  (Examples referenced but not stored in metadata)"
            )

    output_lines.append("---")
    return cap_response("\n".join(output_lines))


async def _return_type_branch(return_type: str, n_results: int, version_filter: str | None) -> str:
    return_type = return_type.strip()
    query = f"function returns {return_type}"
    fetch_count = max(n_results * 5, 50)
    where: dict = {"category": "function"}
    if version_filter:
        where = {"$and": [where, {"version": version_filter}]}
    results = await query_async(query, fetch_count, where=where)
    db_err = check_query_error(results)
    if db_err:
        return db_err

    if not results.get("ids") or not results["ids"][0]:
        return f"No functions found that return '{return_type}'."

    all_results = list(
        zip(
            results["metadatas"][0],
            results["documents"][0],
            results["distances"][0],
        )
    )

    rt_lower = return_type.lower()
    direct_matches = []
    semantic_matches = []
    for meta, doc, dist in all_results:
        returns_field = (meta.get("returns") or "").lower()
        if returns_field and _return_type_matches(rt_lower, returns_field):
            direct_matches.append((meta, doc, dist, True))
        elif dist < 0.5:
            semantic_matches.append((meta, doc, dist, False))

    has_direct = len(direct_matches) > 0

    if has_direct:
        matched = direct_matches + [s for s in semantic_matches if s[2] < 0.4]
    else:
        matched = [
            (m, d, dist, False) for m, d, dist in all_results[:5] if dist < 0.6
        ]

    if not matched:
        return (
            f"No functions found that return '{return_type}'. "
            f"Try a known type: 'float', 'int', 'bool', 'str', 'list', 'dict'."
        )

    if has_direct:
        header = f"FUNCTIONS RETURNING '{return_type}':\nFound {len(matched)} candidate(s)"
    else:
        header = (
            f"No exact return-type match found for '{return_type}'.\n"
            f"Showing {len(matched)} semantically related function(s):"
        )
    output_lines = [header, ""]

    for meta, doc, dist, is_direct in matched[:n_results]:
        name = meta.get("name", "?")
        syntax = meta.get("syntax") or name
        returns = meta.get("returns") or ""
        namespace = meta.get("namespace") or ""
        ns = f"{namespace}." if namespace and not name.startswith(f"{namespace}.") else ""
        match_type = (
            "direct match" if is_direct else f"semantic ({relevance_pct(dist)})"
        )

        output_lines.append(f"  {ns}{name}")
        if returns:
            output_lines.append(f"    Returns: {returns[:100]}")
        if syntax:
            output_lines.append(f"    Syntax: {syntax[:100]}")
        output_lines.append(f"    ({match_type})")
        output_lines.append("")

    return cap_response("\n".join(output_lines))


async def _suggest_branch(
    context: str, current_line: str | None, n_results: int, version_filter: str | None
) -> str:
    query_text = context
    if current_line:
        query_text += f" | current line: {current_line}"

    where: dict = {"category": "function"}
    if version_filter:
        where = {"$and": [where, {"version": version_filter}]}
    results = await query_async(query_text, n_results, where=where)
    db_err = check_query_error(results)
    if db_err:
        return db_err

    if not results.get("ids") or not results["ids"][0]:
        return f"No functions found for '{context}'. Try a different search term."

    filtered = [
        (meta, doc, dist)
        for meta, doc, dist in zip(
            results["metadatas"][0],
            results["documents"][0],
            results["distances"][0],
        )
        if dist < 0.7
    ]
    if not filtered:
        return f"No relevant functions found for '{context}'. Try a different search term."

    lines = [f"SUGGESTED FUNCTIONS for '{context}':", ""]
    for i, (meta, doc, dist) in enumerate(filtered, 1):
        name = meta.get("name", "?")
        namespace = meta.get("namespace") or ""
        syntax = meta.get("syntax") or ""
        returns = meta.get("returns") or ""
        desc = meta.get("raw_description", "")
        url = meta.get("url", "")
        ns = f"{namespace}." if namespace and not name.startswith(f"{namespace}.") else ""
        first_sentence = desc.split(".")[0][:100] if desc else ""

        lines.append(f"  {i}. {ns}{name}")
        if syntax:
            lines.append(f"     Syntax: {syntax[:100]}")
        if returns:
            lines.append(f"     Returns: {returns[:60]}")
        if first_sentence:
            lines.append(f"     {first_sentence}")
        if url:
            lines.append(f"     URL: {url}")
        lines.append("")

    return cap_response("\n".join(lines))


async def _docs_branch(
    query: str,
    n_results: int,
    category_filter: str | None,
    namespace_filter: str | None,
    version_filter: str | None,
) -> str:
    if len(query) <= 3:
        return await _short_query_search(
            query, n_results, category_filter, namespace_filter, version_filter
        )

    name_entries = []
    name_entry_ids = set()

    def _collect_name_hits(search_text: str, min_score: float = 70.0) -> None:
        hits = _db.search_by_name(search_text)
        for score, entry in hits[:2]:
            if score >= min_score and entry.get("id") not in name_entry_ids:
                name_entries.append((score, entry))
                name_entry_ids.add(entry.get("id"))

    _collect_name_hits(query)

    _STOP_WORDS = {"how", "the", "a", "an", "of", "in", "on", "to", "for", "is", "it", "my", "me",
                   "from", "and", "or", "with", "by", "at", "do", "does", "can", "what", "which",
                   "that", "this", "get", "use", "using", "show", "find", "check", "make", "create",
                   "draw", "plot", "calculate", "compute", "return", "into", "two", "between", "if"}
    words = [w for w in re.findall(r"\w{2,}", query.lower()) if w not in _STOP_WORDS]
    for i in range(len(words) - 1):
        _collect_name_hits(f"{words[i]} {words[i+1]}", min_score=65.0)
    for w in words:
        _collect_name_hits(w, min_score=75.0)

    name_entries.sort(key=lambda x: x[0], reverse=True)

    where_clauses: list[dict] = []
    if category_filter:
        where_clauses.append({"category": category_filter})
    if namespace_filter:
        where_clauses.append({"namespace": namespace_filter})
    if version_filter:
        where_clauses.append({"version": version_filter})

    where: Optional[dict] = None
    if len(where_clauses) == 1:
        where = where_clauses[0]
    elif len(where_clauses) > 1:
        where = {"$and": where_clauses}

    results = await query_async(query, n_results, where=where)

    _APPLICABLE_CATEGORIES = {"function", "interface", "enumeration", "type-alias", "variable", "guide", "tutorial"}
    if not category_filter and results["ids"] and results["ids"][0]:
        top_categories = [m.get("category", "") for m in results["metadatas"][0][:3]]
        has_function_in_top3 = any(c in _APPLICABLE_CATEGORIES for c in top_categories)
        if not has_function_in_top3:
            func_where_clauses = [{"category": "function"}]
            if namespace_filter:
                func_where_clauses.append({"namespace": namespace_filter})
            if version_filter:
                func_where_clauses.append({"version": version_filter})
            func_where = func_where_clauses[0] if len(func_where_clauses) == 1 else {"$and": func_where_clauses}
            supp = await query_async(query, max(n_results, 3), where=func_where)
            if supp["ids"] and supp["ids"][0]:
                results["ids"][0] = list(results["ids"][0])
                results["metadatas"][0] = list(results["metadatas"][0])
                results["documents"][0] = list(results["documents"][0])
                results["distances"][0] = list(results["distances"][0])
                existing_ids = set(results["ids"][0])
                func_entries = []
                for rid, meta, doc, dist in zip(
                    supp["ids"][0], supp["metadatas"][0],
                    supp["documents"][0], supp["distances"][0],
                ):
                    if rid not in existing_ids:
                        func_entries.append((rid, meta, doc, dist))
                        existing_ids.add(rid)
                if func_entries:
                    all_entries = list(zip(
                        results["ids"][0], results["metadatas"][0],
                        results["documents"][0], results["distances"][0],
                    ))
                    top_guide = [all_entries[0]] if all_entries else []
                    rest = all_entries[1:]
                    interleaved = top_guide + func_entries + rest
                    results["ids"][0] = [e[0] for e in interleaved]
                    results["metadatas"][0] = [e[1] for e in interleaved]
                    results["documents"][0] = [e[2] for e in interleaved]
                    results["distances"][0] = [e[3] for e in interleaved]

    if name_entries and results["ids"] and results["ids"][0]:
        existing_ids = set(results["ids"][0])
        id_to_idx = {rid: i for i, rid in enumerate(results["ids"][0])}
        promoted = 0
        for score, entry in name_entries:
            rid = entry.get("id")
            if not rid:
                continue
            if rid not in existing_ids:
                meta = entry.get("metadata", {})
                doc_text = entry.get("document") or ""
                results["ids"][0].insert(promoted, rid)
                results["metadatas"][0].insert(promoted, meta)
                results["documents"][0].insert(promoted, doc_text)
                results["distances"][0].insert(promoted, 0.01)
                existing_ids.add(rid)
                id_to_idx = {r: i for i, r in enumerate(results["ids"][0])}
                promoted += 1
            elif rid in id_to_idx:
                current_idx = id_to_idx[rid]
                if current_idx > promoted:
                    for key in ("ids", "metadatas", "documents", "distances"):
                        item = results[key][0].pop(current_idx)
                        results[key][0].insert(promoted, item)
                    id_to_idx = {r: i for i, r in enumerate(results["ids"][0])}
                promoted += 1

    if category_filter == "function" and results["ids"] and results["ids"][0]:
        results["ids"][0] = list(results["ids"][0])
        results["metadatas"][0] = list(results["metadatas"][0])
        results["documents"][0] = list(results["documents"][0])
        results["distances"][0] = list(results["distances"][0])

        supp_where = {"namespace": namespace_filter} if namespace_filter else None
        supp = await query_async(query, n_results, where=supp_where)
        if supp["ids"] and supp["ids"][0]:
            existing_ids = set(results["ids"][0])
            for rid, meta, doc, dist in zip(
                supp["ids"][0],
                supp["metadatas"][0],
                supp["documents"][0],
                supp["distances"][0],
            ):
                if (
                    rid not in existing_ids
                    and meta.get("category") != "function"
                    and is_function_like(meta)
                ):
                    meta = {**meta, "category": "function"}
                    results["ids"][0].append(rid)
                    results["metadatas"][0].append(meta)
                    results["documents"][0].append(doc)
                    results["distances"][0].append(dist)
                    existing_ids.add(rid)

    if results["ids"] and results["ids"][0] and len(results["ids"][0]) > n_results:
        for key in ("ids", "metadatas", "documents", "distances"):
            results[key][0] = results[key][0][:n_results]

    db_err = check_query_error(results)
    if db_err:
        return db_err

    if not results["ids"] or not results["ids"][0]:
        return f"No results found for '{query}'. Try broadening your search terms."

    seen_hashes: set[int] = set()
    deduped_results = []

    for rid, meta, doc, dist in zip(
        results["ids"][0],
        results["metadatas"][0],
        results["documents"][0],
        results["distances"][0],
    ):
        content_key = doc[:120].strip().lower()
        content_hash = xxhash.xxh64(content_key.encode()).intdigest()
        if content_hash in seen_hashes:
            continue
        seen_hashes.add(content_hash)
        if dist < 0.7:
            deduped_results.append((rid, meta, doc, dist))

    if not deduped_results:
        return f"No results found for '{query}'. Try broadening your search terms."

    output_lines: list[str] = []
    for i, (rid, meta, doc, dist) in enumerate(deduped_results):
        name = meta.get("name", "?")
        category = meta.get("category", "?").upper()
        namespace = meta.get("namespace") or ""
        ns = f"{namespace}." if namespace and not name.startswith(f"{namespace}.") else ""
        rel = relevance_pct(dist)
        tag = "[Local]"

        output_lines.append("---")
        output_lines.append(f"[{i + 1}] {ns}{name} | {category} | Relevance: {rel}")
        output_lines.append(f"  {tag}")

        desc = meta.get("raw_description", "")
        if desc:
            first_para = desc.split("\n\n")[0]
            snippet = (
                first_para[:300] + "..." if len(first_para) > 300 else first_para
            )
            output_lines.append(f"  {snippet}")

        param_text = format_params_text(meta)
        if param_text:
            output_lines.append("  " + param_text.split("\n")[0])

        returns = meta.get("returns") or ""
        if returns:
            output_lines.append(f"  RETURNS: {returns[:120]}")

        ex_count = meta.get("example_count", 0)
        if ex_count:
            output_lines.append(f"  Examples: {ex_count}")

    output_lines.append("---")
    return cap_response("\n".join(output_lines))


@tool(
    annotations=ToolAnnotations(
        title="Search Lightweight Charts Knowledge",
        readOnlyHint=True,
        openWorldHint=False,
        idempotentHint=True,
    )
)
async def lwc_search(
    query: Annotated[
        str,
        Field(
            min_length=1,
            max_length=500,
            description=(
                "What to search for. Natural language works best. "
                "Examples: 'candlestick series', 'price scale', 'create chart', "
                "'real-time updates', 'time scale'."
            ),
        ),
    ],
    category: Annotated[
        str | None,
        Field(
            default=None,
            max_length=50,
            description=(
                "Restrict to one entry kind: 'function', 'interface', "
                "'enumeration', 'type-alias', 'variable', 'guide', 'tutorial'. "
                "Leave unset for all kinds."
            ),
        ),
    ] = None,
    namespace: Annotated[
        str | None,
        Field(
            default=None,
            max_length=50,
            description=(
                "Restrict to a namespace: 'functions', 'interfaces', 'enumerations', "
                "'type-aliases', 'getting-started', 'series-types', 'price-scale', "
                "'customization', 'react', 'how-to'."
            ),
        ),
    ] = None,
    return_type: Annotated[
        str | None,
        Field(
            default=None,
            max_length=100,
            description=(
                "Find functions whose return type matches this value. "
                "Examples: 'number', 'string', 'boolean', 'IChartApi', 'ISeriesApi', "
                "'void', 'LineSeriesOptions'. When set, `query` is used only as a "
                "semantic tiebreaker."
            ),
        ),
    ] = None,
    has_examples: Annotated[
        bool,
        Field(
            default=False,
            description=(
                "When true, return code-example blocks only from entries that "
                "contain full runnable examples. Use for 'show me how to ...'."
            ),
        ),
    ] = False,
    current_line: Annotated[
        str | None,
        Field(
            default=None,
            max_length=200,
            description=(
                "The partially-written source line the user is completing. "
                "When set, lwc_search switches to function-suggestion mode, "
                "biasing results by that context."
            ),
        ),
    ] = None,
    n_results: Annotated[
        int,
        Field(
            default=5,
            ge=1,
            le=30,
            description="How many results to return (1-30).",
        ),
    ] = 5,
    version: Annotated[
        Literal["3.8", "4.0", "4.1", "4.2", "5.0"] | None,
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
    Unified semantic search over the full Lightweight Charts knowledge base.

    Mode selection (checked in order):
      1. `return_type` set         -> find functions returning that type.
      2. `current_line` set        -> context-aware function suggestions.
      3. `has_examples=True`       -> runnable code-example blocks only.
      4. Default                   -> ranked semantic hits across all kinds.

    WHEN TO USE:
      - You don't know the exact symbol name yet.
      - You're asking "how do I accomplish X in Lightweight Charts?"
      - You want several relevant candidates with signatures and snippets.

    WHEN NOT TO USE:
      - You already know the symbol name -> call lwc_lookup().
      - You want every member of a namespace -> call lwc_browse().
    """
    try:
        q = query.strip()
        await ensure_hot_cache()

        if return_type:
            return await _return_type_branch(return_type, n_results, version)
        if current_line is not None:
            return await _suggest_branch(q, current_line, n_results, version)
        if has_examples:
            return await _examples_branch(q, n_results, version)
        return await _docs_branch(q, n_results, category, namespace, version)

    except ToolError:
        raise
    except Exception as e:
        logger.error(f"[lwc_search] {e}")
        if "ChromaDB" in str(e) or _db._chroma_breaker.is_open():
            return circuit_breaker_msg()
        raise ToolError(safe_error(e, "lwc_search"))

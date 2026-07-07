"""
core/db.py
ChromaDB collection management, circuit breaker, and query helpers.
TradingView Lightweight Charts reference documentation.
"""

from __future__ import annotations

import asyncio
import copy
import threading
import time
from typing import TYPE_CHECKING, Optional

import xxhash
from loguru import logger

if TYPE_CHECKING:
    import chromadb

from core.caches import (
    _QUERY_CACHE_LOCK,
    _QUERY_CACHE_MAX,
    _QUERY_CACHE_TTL,
    _QUERY_RESULT_CACHE,
)
from core.config import (
    COLLECTION,
    DB_PATH,
    EMBED_DIM,
    MAX_FUZZY_SCAN_ENTRIES,
    MAX_RESULTS,
)
from core.embeddings import get_model


class ChromaDBCircuitBreaker:
    def __init__(self, threshold: int = 3, cooldown: int = 30):
        self.failures: int = 0
        self.threshold: int = threshold
        self.cooldown: int = cooldown
        self.open_until: float = 0.0
        self._lock = threading.Lock()

    def is_open(self) -> bool:
        with self._lock:
            if self.open_until and time.time() > self.open_until:
                self.failures = 0
                self.open_until = 0.0
                logger.info("ChromaDB circuit RESET (cooldown expired)")
            return time.time() < self.open_until

    def record_failure(self, exc: Exception) -> None:
        with self._lock:
            self.failures += 1
            logger.warning(
                f"ChromaDB failure {self.failures}/{self.threshold}: {type(exc).__name__}"
            )
            if self.failures >= self.threshold:
                self.open_until = time.time() + self.cooldown
                logger.error(f"ChromaDB circuit OPEN - cooldown {self.cooldown}s")

    def record_success(self) -> None:
        with self._lock:
            if self.failures:
                self.failures = 0
                self.open_until = 0.0


_chroma_breaker = ChromaDBCircuitBreaker(threshold=3, cooldown=30)

_collection = None
_db_init_lock = threading.Lock()

_name_index: dict[str, list[dict]] = {}
_name_index_built: bool = False
_name_index_lock = threading.Lock()

_COMMON_PARAM_NAMES = frozenset(
    {
        "container", "options", "data", "time", "value", "open", "high",
        "low", "close", "volume", "color", "lineColor", "topColor",
        "bottomColor", "upColor", "downColor", "wickUpColor", "wickDownColor",
        "price", "priceScale", "scaleMargins", "lineWidth", "lineType",
        "lineStyle", "crosshairMode", "handleScroll", "handleScale",
        "timeScale", "layout", "grid", "watermark", "localization",
        "priceFormat", "autoscaleInfoProvider", "series", "type",
        "width", "height", "autoSize", "timestamp", "symbol",
    }
)


def _reset_caches() -> None:
    global _name_index, _name_index_built
    with _name_index_lock:
        _name_index = {}
        _name_index_built = False

    with _QUERY_CACHE_LOCK:
        _QUERY_RESULT_CACHE.clear()

    try:
        import core.hot_cache as _hc
        _hc._hot_cache_built = False
        _hc.HOT_CACHE.clear()
    except Exception:
        pass

    logger.info("Caches invalidated after collection reconnect")


def get_collection() -> chromadb.Collection:
    global _collection
    if _chroma_breaker.is_open():
        raise RuntimeError(
            "ChromaDB circuit breaker is open (cooldown). Please wait and try again."
        )
    if _collection is not None:
        try:
            _collection.count()
            _chroma_breaker.record_success()
            return _collection
        except Exception as e:
            err_name = type(e).__name__
            if "NotFound" in err_name or "not exist" in str(e).lower():
                logger.warning(
                    f"Stale ChromaDB collection detected ({err_name}), reconnecting"
                )
                _collection = None
                _reset_caches()
            else:
                _chroma_breaker.record_failure(e)
                raise
    with _db_init_lock:
        if _collection is not None:
            _chroma_breaker.record_success()
            return _collection
        try:
            import chromadb

            client = chromadb.PersistentClient(path=DB_PATH)
            _collection = client.get_collection(name=COLLECTION)
            count = _collection.count()
            logger.info(f"Connected to ChromaDB - {count} entries")

            if count > 0:
                try:
                    _collection.query(
                        query_embeddings=[[0.0] * EMBED_DIM],
                        n_results=1,
                        include=["distances"],
                    )
                    logger.debug("HNSW index warmed up")
                except Exception:
                    pass

            _chroma_breaker.record_success()
            return _collection
        except Exception as e:
            _chroma_breaker.record_failure(e)
            logger.error(f"ChromaDB init failed: {e}")
            raise


def build_name_index() -> None:
    global _name_index, _name_index_built
    with _name_index_lock:
        if _name_index_built:
            return
        try:
            _name_index = {}
            col = get_collection()
            total = col.count()
            result = col.get(include=["metadatas", "documents"], limit=total)
            for rid, meta, doc in zip(
                result["ids"], result["metadatas"], result["documents"]
            ):
                key = (meta.get("name") or "").lower().strip()
                if key:
                    entry = {"id": rid, "metadata": meta, "document": doc}
                    if key not in _name_index:
                        _name_index[key] = []
                    _name_index[key].append(entry)
            _name_index_built = True
            logger.info(
                f"Name index built: {len(_name_index)} unique names from {total} entries"
            )
        except Exception as e:
            logger.error(f"Failed to build name index: {e}")


def _query(query_text: str, n: int, where: Optional[dict] = None) -> dict:
    _cache_key = xxhash.xxh64(f"{query_text}|{n}|{where}".encode()).hexdigest()
    with _QUERY_CACHE_LOCK:
        if _cache_key in _QUERY_RESULT_CACHE:
            cached_result, cached_ts = _QUERY_RESULT_CACHE[_cache_key]
            if time.time() - cached_ts < _QUERY_CACHE_TTL:
                logger.debug(f"L1 cache hit: {query_text[:40]}")
                return {
                    "ids": [list(cached_result["ids"][0])] if cached_result.get("ids") else [[]],
                    "metadatas": [list(cached_result["metadatas"][0])] if cached_result.get("metadatas") else [[]],
                    "documents": [list(cached_result["documents"][0])] if cached_result.get("documents") else [[]],
                    "distances": [list(cached_result["distances"][0])] if cached_result.get("distances") else [[]],
                }
            else:
                del _QUERY_RESULT_CACHE[_cache_key]
    try:
        model = get_model()
        col = get_collection()
        embedding = model.encode([query_text], show_progress_bar=False)[0].tolist()

        kwargs: dict = dict(
            query_embeddings=[embedding],
            n_results=min(n, MAX_RESULTS),
            include=["documents", "metadatas", "distances"],
        )
        if where:
            kwargs["where"] = where

        result = col.query(**kwargs)

        with _QUERY_CACHE_LOCK:
            _QUERY_RESULT_CACHE[_cache_key] = (result, time.time())
            _QUERY_RESULT_CACHE.move_to_end(_cache_key)
            while len(_QUERY_RESULT_CACHE) > _QUERY_CACHE_MAX:
                _QUERY_RESULT_CACHE.popitem(last=False)

        return result
    except Exception as e:
        error_type = type(e).__name__
        logger.error(
            f"_query() failed | type={error_type} | where={where} | "
            f"query={query_text[:80]}"
        )
        return {
            "ids": [[]],
            "documents": [[]],
            "metadatas": [[]],
            "distances": [[]],
            "_error": f"{error_type}: {str(e)[:200]}",
        }


async def query_async(query_text: str, n: int, where: Optional[dict] = None) -> dict:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _query, query_text, n, where)


def get_by_id(entry_id: str) -> Optional[dict]:
    try:
        col = get_collection()
        result = col.get(ids=[entry_id], include=["documents", "metadatas"])
        if result["ids"]:
            return {
                "id": entry_id,
                "metadata": result["metadatas"][0],
                "document": result["documents"][0],
            }
        return None
    except Exception as e:
        logger.error(f"get_by_id({entry_id}) failed: {e}")
        return None


def search_by_name(name: str, where: Optional[dict] = None) -> list[tuple[float, dict]]:
    try:
        from rapidfuzz import fuzz

        col = get_collection()
        name_preserved = name.strip()
        name_lower = name.lower().strip()

        if not name_lower:
            return []

        with _name_index_lock:
            if _name_index_built:
                hits = _name_index.get(name_lower)
            else:
                hits = None
        if hits:
            if where:
                cat = where.get("category")
                if cat:
                    hits = [h for h in hits if h["metadata"].get("category") == cat]
                for clause in where.get("$and", []):
                    if "category" in clause:
                        hits = [
                            h
                            for h in hits
                            if h["metadata"].get("category") == clause["category"]
                        ]
            if hits:
                return [(100.0, copy.deepcopy(h)) for h in hits]

        name_variants = list({name_preserved, name_lower})
        try:
            exact_where: dict = {"name": {"$in": name_variants}}
            if where:
                cat = where.get("category")
                if cat:
                    existing_clauses = where.get("$and", [where])
                    exact_where = {
                        "$and": [{"name": {"$in": name_variants}}, {"category": cat}] + [
                            c for c in existing_clauses if "category" not in c
                        ]
                    }
            exact = col.get(where=exact_where, include=["metadatas", "documents"])
            if exact["ids"]:
                return [
                    (
                        100.0,
                        {
                            "id": rid,
                            "metadata": meta,
                            "document": doc,
                        },
                    )
                    for rid, meta, doc in zip(
                        exact["ids"], exact["metadatas"], exact["documents"]
                    )
                ]
        except Exception as e:
            logger.debug(f"Exact unqualified lookup failed: {e}")

        total = min(col.count(), MAX_FUZZY_SCAN_ENTRIES)
        get_kwargs: dict = dict(include=["metadatas", "documents"], limit=total)
        if where:
            get_kwargs["where"] = where
        result = col.get(**get_kwargs)
        if not result["ids"]:
            return []
        candidates: list[tuple[float, dict]] = []
        for meta, doc, rid in zip(
            result["metadatas"], result["documents"], result["ids"]
        ):
            entry_name = (meta.get("name") or "").lower().replace("()", "").strip()
            ratio = fuzz.ratio(name_lower, entry_name)
            candidates.append((ratio, {"id": rid, "metadata": meta, "document": doc}))
        candidates.sort(key=lambda x: x[0], reverse=True)
        return candidates
    except Exception as e:
        logger.error(f"search_by_name({name}) failed: {e}")
        return []


def get_all_where(where: dict | None, limit: int | None = None) -> list[dict]:
    try:
        col = get_collection()
        if limit is None:
            limit = col.count()
        if where:
            result = col.get(
                where=where, include=["metadatas", "documents"], limit=limit
            )
        else:
            result = col.get(include=["metadatas", "documents"], limit=limit)
        entries = []
        for rid, meta, doc in zip(
            result["ids"], result["metadatas"], result["documents"]
        ):
            entries.append({"id": rid, "metadata": meta, "document": doc})
        return entries
    except Exception as e:
        logger.error(f"get_all_where failed: {e}")
        return []


async def search_by_name_async(
    name: str, where: Optional[dict] = None
) -> list[tuple[float, dict]]:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, search_by_name, name, where)


async def get_all_where_async(
    where: dict | None, limit: int | None = None
) -> list[dict]:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, get_all_where, where, limit)


def get_by_names(names: list[str]) -> dict:
    try:
        col = get_collection()
        return col.get(
            where={"name": {"$in": names}}, include=["metadatas", "documents"]
        )
    except Exception as e:
        logger.debug(f"get_by_names failed: {e}")
        return {"ids": [], "metadatas": [], "documents": []}


async def get_by_names_async(names: list[str]) -> dict:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, get_by_names, names)

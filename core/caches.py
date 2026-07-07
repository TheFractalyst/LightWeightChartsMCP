"""
core/caches.py
All in-process LRU caches:
  - Validation cache (code hash -> compiler result)
  - File validation cache (path+mtime+size -> validation result)
  - Query result cache (L1: ChromaDB query results)
  - Codegen cache (template generation results)
"""

from __future__ import annotations

import json
import os
import threading
import time
from collections import OrderedDict
from typing import Optional

import xxhash
from loguru import logger

from core.config import VALIDATION_CACHE_MAX_SIZE, VALIDATION_CACHE_TTL

_VALIDATION_CACHE: OrderedDict[str, tuple[str, float]] = OrderedDict()
_VALIDATION_CACHE_LOCK = threading.Lock()


def get_cached_validation(code: str) -> Optional[dict]:
    h = xxhash.xxh64(code.encode()).hexdigest()
    with _VALIDATION_CACHE_LOCK:
        if h in _VALIDATION_CACHE:
            result_str, ts = _VALIDATION_CACHE[h]
            if time.time() - ts < VALIDATION_CACHE_TTL:
                try:
                    return json.loads(result_str)
                except json.JSONDecodeError:
                    logger.warning("Corrupt validation cache entry - evicting")
                    del _VALIDATION_CACHE[h]
    return None


def set_cached_validation(code: str, result: str) -> None:
    h = xxhash.xxh64(code.encode()).hexdigest()
    with _VALIDATION_CACHE_LOCK:
        _VALIDATION_CACHE[h] = (result, time.time())
        _VALIDATION_CACHE.move_to_end(h)
        while len(_VALIDATION_CACHE) > VALIDATION_CACHE_MAX_SIZE:
            _VALIDATION_CACHE.popitem(last=False)


_FILE_VALIDATION_CACHE: OrderedDict[tuple[str, int, int], tuple[str, float]] = OrderedDict()
_FILE_VALIDATION_CACHE_LOCK = threading.Lock()
_FILE_VALIDATION_CACHE_TTL = float(os.getenv("FILE_VALIDATION_CACHE_TTL", "1800"))
_FILE_VALIDATION_CACHE_MAX = int(os.getenv("FILE_VALIDATION_CACHE_SIZE", "200"))


def get_cached_file_validation(file_path: str, mtime_ns: int, file_size: int) -> Optional[str]:
    key = (file_path, mtime_ns, file_size)
    with _FILE_VALIDATION_CACHE_LOCK:
        if key in _FILE_VALIDATION_CACHE:
            result_str, ts = _FILE_VALIDATION_CACHE[key]
            if time.time() - ts < _FILE_VALIDATION_CACHE_TTL:
                logger.debug(f"File validation cache hit: {file_path}")
                return result_str
            else:
                del _FILE_VALIDATION_CACHE[key]
    return None


def set_cached_file_validation(file_path: str, mtime_ns: int, file_size: int, result: str) -> None:
    key = (file_path, mtime_ns, file_size)
    with _FILE_VALIDATION_CACHE_LOCK:
        _FILE_VALIDATION_CACHE[key] = (result, time.time())
        _FILE_VALIDATION_CACHE.move_to_end(key)
        while len(_FILE_VALIDATION_CACHE) > _FILE_VALIDATION_CACHE_MAX:
            _FILE_VALIDATION_CACHE.popitem(last=False)


_QUERY_RESULT_CACHE: OrderedDict[str, tuple[dict, float]] = OrderedDict()
_QUERY_CACHE_LOCK = threading.Lock()
_QUERY_CACHE_TTL = 600.0
_QUERY_CACHE_MAX = 500


_CODEGEN_CACHE: OrderedDict[str, tuple[str, float]] = OrderedDict()
_CODEGEN_CACHE_LOCK = threading.Lock()
_CODEGEN_CACHE_TTL = 600.0
_CODEGEN_CACHE_MAX = 50


def codegen_cache_key(name: str, description: str, inputs: str | None, overlay: bool) -> str:
    return xxhash.xxh64(f"{name}|{description}|{inputs}|{overlay}".encode()).hexdigest()


def get_codegen_cache(key: str) -> str | None:
    with _CODEGEN_CACHE_LOCK:
        if key in _CODEGEN_CACHE:
            result, ts = _CODEGEN_CACHE[key]
            if time.time() - ts < _CODEGEN_CACHE_TTL:
                return result
            del _CODEGEN_CACHE[key]
    return None


def set_codegen_cache(key: str, result: str) -> None:
    with _CODEGEN_CACHE_LOCK:
        _CODEGEN_CACHE[key] = (result, time.time())
        _CODEGEN_CACHE.move_to_end(key)
        while len(_CODEGEN_CACHE) > _CODEGEN_CACHE_MAX:
            _CODEGEN_CACHE.popitem(last=False)

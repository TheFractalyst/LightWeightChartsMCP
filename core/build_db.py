"""
core/build_db.py
Auto-build ChromaDB from shipped JSON data on first run.

Ships data/lwc_entries.json (1.5MB, ~1617 entries) as package data.
On first server start, if no ChromaDB exists at DB_PATH, builds it automatically.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from loguru import logger

from core.config import COLLECTION, DB_PATH, EMBED_MODEL


def _data_json_path() -> Path:
    """Locate lwc_entries.json relative to this module."""
    return Path(__file__).resolve().parent.parent / "data" / "lwc_entries.json"


def build_document_text(entry: dict[str, Any]) -> str:
    """Build the text that gets embedded for semantic search."""
    parts: list[str] = []
    name = entry.get("name", "")
    namespace = entry.get("namespace") or ""
    category = entry.get("category", "")
    version = entry.get("version", "")
    parts.append(f"{category.upper()}: {name}")
    if version:
        parts.append(f"Version: {version}")
    if namespace:
        parts.append(f"Namespace: {namespace}")

    syntax = entry.get("syntax") or ""
    if not isinstance(syntax, str):
        syntax = str(syntax)
    if syntax:
        parts.append(f"Syntax: {syntax}")

    description = entry.get("description") or ""
    if not isinstance(description, str):
        description = str(description)
    if description:
        parts.append(description)

    parameters = entry.get("parameters") or []
    if parameters:
        parts.append("PARAMETERS:")
        for p in parameters:
            if isinstance(p, dict):
                pname = p.get("name", "?")
                ptype = p.get("type", "")
                pdesc = p.get("description", "")
                parts.append(f"  {pname} ({ptype}): {pdesc}")

    examples = entry.get("examples") or []
    if examples:
        parts.append("EXAMPLES:")
        for ex in examples:
            parts.append(str(ex))

    return "\n\n".join(parts)


def flatten_metadata(entry: dict[str, Any]) -> dict[str, Any]:
    """Build flat metadata dict for ChromaDB storage."""
    meta: dict[str, Any] = {}
    meta["name"] = entry.get("name", "")
    meta["category"] = entry.get("category", "")
    meta["namespace"] = entry.get("namespace") or ""
    meta["version"] = entry.get("version") or ""
    meta["syntax"] = entry.get("syntax") or ""
    meta["url"] = entry.get("url") or ""
    meta["scraped_at"] = entry.get("scraped_at") or ""

    examples = entry.get("examples") or []
    parameters = entry.get("parameters") or []
    meta["has_examples"] = 1 if examples else 0
    meta["example_count"] = len(examples)
    meta["param_count"] = len(parameters)

    meta["raw_description"] = entry.get("description") or ""

    if isinstance(examples, list):
        meta["raw_examples"] = " ||| ".join(str(ex) for ex in examples)
    elif examples:
        meta["raw_examples"] = str(examples)
    else:
        meta["raw_examples"] = ""

    meta["raw_parameters"] = json.dumps(parameters, ensure_ascii=False) if parameters else ""

    return meta


def _entry_id(entry: dict[str, Any]) -> str:
    """Stable id matching pipeline/merge_and_index.py normalize_key logic."""
    url = entry.get("url", "")
    name = entry.get("name", "").lower().strip().replace(" ", "").replace("()", "").replace("`", "")
    version = entry.get("version", "")
    return hashlib.md5((version + "|" + url + "|" + name).encode()).hexdigest()[:16]


def _upsert_batch(
    collection: Any,
    ids: list[str],
    docs: list[str],
    metas: list[dict[str, Any]],
    embeddings: list[list[float]],
) -> int:
    """Upsert one batch; split and retry on compaction errors."""
    if not ids:
        return 0
    try:
        collection.upsert(ids=ids, documents=docs, metadatas=metas, embeddings=embeddings)
        return len(ids)
    except Exception as e:
        if len(ids) <= 1:
            logger.error(f"Upsert failed for {ids[0]}: {e}")
            return 0
        mid = len(ids) // 2
        logger.warning(f"Upsert split {len(ids)} -> {mid}+{len(ids) - mid}: {e}")
        a = _upsert_batch(collection, ids[:mid], docs[:mid], metas[:mid], embeddings[:mid])
        b = _upsert_batch(collection, ids[mid:], docs[mid:], metas[mid:], embeddings[mid:])
        return a + b


def db_exists() -> bool:
    """Check if a usable ChromaDB collection exists at DB_PATH."""
    try:
        import chromadb
        client = chromadb.PersistentClient(path=DB_PATH)
        col = client.get_collection(name=COLLECTION)
        return col.count() > 0
    except Exception:
        return False


def build_db(force: bool = False) -> int:
    """Build ChromaDB from shipped JSON data. Returns entry count.

    Args:
        force: If True, wipe and rebuild. If False, only build if DB is empty/missing.
    """
    if not force and db_exists():
        logger.info(f"ChromaDB already exists at {DB_PATH} ({COLLECTION}), skipping build")
        return 0

    json_path = _data_json_path()
    if not json_path.exists():
        logger.error(f"LWC data file not found: {json_path}")
        raise FileNotFoundError(f"Cannot build DB: {json_path} not found")

    logger.info(f"Building ChromaDB from {json_path}...")
    entries = json.loads(json_path.read_text(encoding="utf-8"))
    logger.info(f"Loaded {len(entries)} entries from JSON")

    import chromadb
    from sentence_transformers import SentenceTransformer

    logger.info(f"Loading embedding model: {EMBED_MODEL}")
    model = SentenceTransformer(EMBED_MODEL)
    logger.info("Embedding model loaded")

    client = chromadb.PersistentClient(path=DB_PATH)
    if force:
        try:
            client.delete_collection(name=COLLECTION)
            logger.info("Deleted existing collection")
        except Exception:
            pass

    collection = client.get_or_create_collection(
        name=COLLECTION,
        metadata={"hnsw:space": "cosine"},
    )

    batch_size = 25
    total = len(entries)
    indexed = 0

    for i in range(0, total, batch_size):
        batch = entries[i : i + batch_size]
        ids: list[str] = []
        docs: list[str] = []
        metas: list[dict[str, Any]] = []

        for entry in batch:
            entry_id = _entry_id(entry)
            entry["id"] = entry_id
            ids.append(entry_id)
            docs.append(build_document_text(entry))
            metas.append(flatten_metadata(entry))

        if docs:
            try:
                vecs = model.encode(docs, show_progress_bar=False)
                embeddings = [v.tolist() for v in vecs]
            except Exception as e:
                logger.error(f"Embedding failed on batch {i // batch_size + 1}: {e}")
                continue
            indexed += _upsert_batch(collection, ids, docs, metas, embeddings)

        if (i // batch_size + 1) % 10 == 0:
            logger.info(f"Progress: {min(i + batch_size, total)}/{total} entries processed")

    count = collection.count()
    logger.info(f"ChromaDB build complete: {count} entries indexed at {DB_PATH}")
    return count


def build_db_if_needed() -> bool:
    """Build DB if it doesn't exist. Returns True if DB is ready."""
    try:
        if db_exists():
            return True
        logger.info("ChromaDB not found - building from shipped data (first run)...")
        logger.info("This may take 30-60 seconds (embedding model download + indexing)")
        build_db(force=False)
        return True
    except Exception as e:
        logger.error(f"Auto-build failed: {e}")
        logger.info("You can build manually: lwcmcp build")
        return False

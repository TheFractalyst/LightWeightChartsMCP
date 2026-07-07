# ruff: noqa: E501
"""
pipeline/merge_and_index.py
Index Lightweight Charts scraped entries into ChromaDB.

Usage:
    python merge_and_index.py [--input FILE] [--db PATH] [--reset] [--dry-run]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from loguru import logger

logger.remove()
logger.add(sys.stderr, format="{time:HH:mm:ss} | {level:<8} | {message}", level="INFO")

ROOT = Path(__file__).parent.parent
DEFAULT_INPUT = ROOT / "data" / "lwc_entries.json"
DEFAULT_DB = ROOT / "lwc_db"
COLLECTION_NAME = "lwc_reference"
EMBED_MODEL = "all-MiniLM-L6-v2"
BATCH_SIZE = int(os.environ.get("LWC_INDEX_BATCH_SIZE", "25"))


def normalize_key(entry: dict[str, Any]) -> str:
    name = entry.get("name", "")
    category = entry.get("category", "")
    version = entry.get("version", "")
    url = entry.get("url", "")
    base = name.lower().strip().replace(" ", "").replace("()", "").replace("`", "")
    return f"{base}__{category}__{version}__{url}"


def deduplicate_examples(examples: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for ex in examples:
        h = hashlib.sha256(ex.encode()).hexdigest()
        if h not in seen:
            seen.add(h)
            result.append(ex)
    return result


def merge_entries(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    logger.info(f"Input entries: {len(entries)}")

    seen_keys: set[str] = set()
    merged: list[dict[str, Any]] = []

    for entry in entries:
        key = normalize_key(entry)
        if key not in seen_keys:
            seen_keys.add(key)
            if "examples" in entry:
                entry["examples"] = deduplicate_examples(entry.get("examples", []))
            merged.append(entry)

    logger.info(f"Total merged: {len(merged)} (after dedup from {len(entries)} raw)")

    ver_counts = Counter(e.get("version", "unknown") for e in merged)
    for ver, n in sorted(ver_counts.items()):
        logger.info(f"  version={ver:<10} {n:>5}")

    cat_counts = Counter(e.get("category", "unknown") for e in merged)
    for cat, n in sorted(cat_counts.items()):
        logger.info(f"  {cat:<15} {n:>5}")

    return merged


def build_document_text(entry: dict[str, Any]) -> str:
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


def _upsert_with_split(
    collection: Any,
    ids: list[str],
    docs: list[str],
    metas: list[dict[str, Any]],
    embeddings: list[list[float]],
    batch_hint: str = "",
) -> int:
    if not ids:
        return 0
    try:
        collection.upsert(
            ids=ids,
            documents=docs,
            metadatas=metas,
            embeddings=embeddings,
        )
        return len(ids)
    except Exception as e:
        if len(ids) <= 1:
            logger.error(f"Upsert failed for {batch_hint or ids[0]}: {e}")
            return 0
        mid = len(ids) // 2
        logger.warning(f"Upsert split {len(ids)}->{mid}+{len(ids) - mid} ({batch_hint}): {e}")
        a = _upsert_with_split(collection, ids[:mid], docs[:mid], metas[:mid], embeddings[:mid], batch_hint)
        b = _upsert_with_split(collection, ids[mid:], docs[mid:], metas[mid:], embeddings[mid:], batch_hint)
        return a + b


def index_to_chromadb(
    entries: list[dict[str, Any]],
    db_path: Path,
    reset: bool = False,
) -> None:
    logger.info(f"Loading embedding model: {EMBED_MODEL}")
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer(EMBED_MODEL)
    logger.info("Embedding model loaded")

    logger.info(f"Connecting to ChromaDB at {db_path}")
    import chromadb
    client = chromadb.PersistentClient(path=str(db_path))

    if reset:
        try:
            client.delete_collection(name=COLLECTION_NAME)
            logger.info("Deleted existing collection")
        except Exception:
            pass

    collection = client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )
    logger.info(f"Collection '{COLLECTION_NAME}' ready (count: {collection.count()})")

    existing_id: set[str] = set()
    if not reset:
        try:
            result = collection.get(include=[])
            existing_id = set(result["ids"])
            logger.info(f"Already indexed: {len(existing_id)} entries")
        except Exception:
            pass

    new_entries = [e for e in entries if e.get("id", "") not in existing_id]
    logger.info(f"New entries to index: {len(new_entries)}")

    if not new_entries:
        logger.info("Nothing to index. Database is up to date.")
        _print_stats(collection)
        return

    total_batches = (len(new_entries) + BATCH_SIZE - 1) // BATCH_SIZE
    indexed_count = 0

    from tqdm import tqdm

    for batch_num in tqdm(range(total_batches), desc="Indexing"):
        batch = new_entries[batch_num * BATCH_SIZE : (batch_num + 1) * BATCH_SIZE]

        ids: list[str] = []
        docs: list[str] = []
        metas: list[dict[str, Any]] = []
        embeddings: list[list[float]] = []

        for entry in batch:
            url = entry.get("url", "")
            name = entry.get("name", "").lower().strip().replace(" ", "").replace("()", "").replace("`", "")
            version = entry.get("version", "")
            entry_id = hashlib.md5((version + "|" + url + "|" + name).encode()).hexdigest()[:16]
            entry["id"] = entry_id

            doc_text = build_document_text(entry)
            meta = flatten_metadata(entry)

            ids.append(entry_id)
            docs.append(doc_text)
            metas.append(meta)

        if docs:
            try:
                vecs = model.encode(docs, show_progress_bar=False)
                embeddings = [v.tolist() for v in vecs]
            except Exception as e:
                logger.error(f"Embedding failed on batch {batch_num + 1}: {e}")
                continue

        n_ok = _upsert_with_split(
            collection,
            ids,
            docs,
            metas,
            embeddings,
            batch_hint=f"batch {batch_num + 1}/{total_batches}",
        )
        indexed_count += n_ok

    logger.info(f"Indexing complete. Indexed {indexed_count} new entries.")
    _print_stats(collection)


def _print_stats(collection) -> None:
    try:
        total = collection.count()
    except Exception:
        total = "unknown"

    print("\n" + "=" * 60)
    print("  CHROMADB INDEX STATS")
    print("=" * 60)
    print(f"  Collection : {COLLECTION_NAME}")
    print(f"  Total docs : {total}")
    print(f"  DB path    : {DEFAULT_DB}")
    print(f"  Model      : {EMBED_MODEL}")
    print("=" * 60 + "\n")


def main():
    parser = argparse.ArgumentParser(description="Index Lightweight Charts docs into ChromaDB")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT, help=f"Input file (default: {DEFAULT_INPUT})")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, help=f"ChromaDB path (default: {DEFAULT_DB})")
    parser.add_argument("--reset", action="store_true", help="Wipe collection and re-index from scratch")
    parser.add_argument("--dry-run", action="store_true", help="Print merge stats without writing to DB")
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("Lightweight Charts Merge & Index")
    logger.info("=" * 60)

    entries: list[dict[str, Any]] = []
    if args.input.exists():
        entries = json.loads(args.input.read_text(encoding="utf-8"))
        logger.info(f"Loaded {len(entries)} entries from {args.input}")
    else:
        logger.error(f"Input file not found: {args.input}")
        sys.exit(1)

    if not entries:
        logger.error("No entries to index.")
        sys.exit(1)

    merged = merge_entries(entries)

    if args.dry_run:
        logger.info("Dry run - skipping ChromaDB indexing.")
        return

    index_to_chromadb(merged, args.db, reset=args.reset)
    logger.info("Done.")


if __name__ == "__main__":
    main()

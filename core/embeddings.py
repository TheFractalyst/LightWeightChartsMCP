"""
core/embeddings.py
SentenceTransformer embedding model management.
"""

from __future__ import annotations

import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer

from core.config import EMBED_MODEL

_model_executor = ThreadPoolExecutor(
    max_workers=4, thread_name_prefix="embedding"
)
_embedding_model_ready = asyncio.Event()
_embed_model = None
_model_init_lock = threading.Lock()


def get_model() -> SentenceTransformer:
    global _embed_model
    if _embed_model is not None:
        return _embed_model
    with _model_init_lock:
        if _embed_model is not None:
            return _embed_model
        try:
            import torch
            from sentence_transformers import SentenceTransformer

            if torch.backends.mps.is_available():
                _embed_model = SentenceTransformer(EMBED_MODEL, device="mps")
                logger.info(f"Embedding model loaded: {EMBED_MODEL} (PyTorch/MPS)")
            elif not torch.cuda.is_available():
                try:
                    _embed_model = SentenceTransformer(EMBED_MODEL, backend="onnx")
                    logger.info(f"Embedding model loaded: {EMBED_MODEL} (ONNX/CPU)")
                except Exception:
                    _embed_model = SentenceTransformer(EMBED_MODEL)
                    logger.info(f"Embedding model loaded: {EMBED_MODEL} (PyTorch/CPU)")
            else:
                _embed_model = SentenceTransformer(EMBED_MODEL)
                logger.info(f"Embedding model loaded: {EMBED_MODEL} (PyTorch)")

            return _embed_model
        except Exception as e:
            logger.error(f"Failed to load embedding model: {e}")
            raise


async def ensure_embedding_model():
    if _embedding_model_ready.is_set():
        return
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(_model_executor, get_model)
    _embedding_model_ready.set()

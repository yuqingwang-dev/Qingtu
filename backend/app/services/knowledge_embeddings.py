"""CPU Chinese vectors. Request handling never downloads model files."""
import math
from functools import lru_cache
from pathlib import Path
from threading import Lock
from app.config import settings

MODEL = "BAAI/bge-small-zh-v1.5"
DIMENSIONS = 512
_lock = Lock()


def cache_path():
    path = Path(settings.KNOWLEDGE_MODEL_CACHE)
    return path if path.is_absolute() else Path(__file__).resolve().parents[2] / path


@lru_cache(maxsize=1)
def get_model():
    from fastembed import TextEmbedding
    return TextEmbedding(model_name=MODEL, cache_dir=str(cache_path()), threads=2,
                         local_files_only=True)


def validate_vector(vector):
    result = [float(v) for v in vector]
    if len(result) != DIMENSIONS or not all(math.isfinite(v) for v in result):
        raise ValueError("Invalid knowledge embedding dimensions or values")
    if sum(v * v for v in result) < 1e-12:
        raise ValueError("Zero knowledge embedding")
    return result


def embed_documents(texts):
    with _lock:
        return [validate_vector(v) for v in get_model().embed(texts)]


@lru_cache(maxsize=128)
def embed_query(text):
    with _lock:
        return validate_vector(next(get_model().query_embed(text)))

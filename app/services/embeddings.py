from functools import lru_cache

import anyio

from app.core.config import settings


@lru_cache(maxsize=1)
def get_embedding_model():
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(settings.embedding_model_name)


def embed_texts(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    embeddings = get_embedding_model().encode(texts, normalize_embeddings=True)
    return [embedding.tolist() for embedding in embeddings]


async def embed_texts_async(texts: list[str]) -> list[list[float]]:
    return await anyio.to_thread.run_sync(embed_texts, texts)


def embed_text(text: str) -> list[float]:
    return embed_texts([text])[0]


async def embed_text_async(text: str) -> list[float]:
    return await anyio.to_thread.run_sync(embed_text, text)

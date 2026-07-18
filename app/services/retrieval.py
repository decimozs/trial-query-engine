from typing import Any
import re

import anyio
from sqlalchemy import case, false, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models import Document, DocumentChunk
from app.schemas.query import RetrievedChunk
from app.services.ingestion import get_embedding_model


def embed_query(question: str) -> list[float]:
    embedding = get_embedding_model().encode([question], normalize_embeddings=True)[0]
    return embedding.tolist()


async def embed_query_async(question: str) -> list[float]:
    return await anyio.to_thread.run_sync(embed_query, question)


def blend_scores(semantic_score: float, keyword_score: float) -> float:
    return (
        settings.rag_semantic_weight * semantic_score
        + settings.rag_keyword_weight * keyword_score
    )


def keyword_tokens(question: str) -> list[str]:
    stopwords = {
        "about",
        "answer",
        "are",
        "common",
        "criteria",
        "for",
        "from",
        "have",
        "information",
        "that",
        "the",
        "trial",
        "trials",
        "what",
        "with",
    }
    seen = set()
    tokens = []
    for token in re.findall(r"[a-z0-9]+", question.lower()):
        if len(token) < 3 or token in stopwords or token in seen:
            continue
        seen.add(token)
        tokens.append(token)
    return tokens[:8]


async def search_similar_chunks(
    session: AsyncSession,
    query_embedding: list[float],
    question: str,
    top_k: int = 5,
    filters: dict[str, Any] | None = None,
) -> list[RetrievedChunk]:
    distance = DocumentChunk.embedding.cosine_distance(query_embedding).label("distance")
    tokens = keyword_tokens(question)
    token_matches = [func.lower(DocumentChunk.chunk_text).like(f"%{token}%") for token in tokens]
    keyword_match = or_(*token_matches) if token_matches else false()
    if token_matches:
        keyword_score = (
            sum(case((match, 1.0), else_=0.0) for match in token_matches) / len(token_matches)
        ).label("keyword_score")
    else:
        keyword_score = case((false(), 1.0), else_=0.0).label("keyword_score")
    semantic_score = (1.0 - distance).label("semantic_score")
    blended_score = blend_scores(semantic_score, keyword_score).label("blended_score")
    stmt = (
        select(DocumentChunk, Document, distance, semantic_score, keyword_score, blended_score)
        .join(Document, DocumentChunk.document_id == Document.id)
        .where(or_(distance <= settings.rag_max_cosine_distance, keyword_match))
        .order_by(blended_score.desc(), distance)
        .limit(top_k)
    )

    if filters:
        if filters.get("phase"):
            stmt = stmt.where(Document.phase == filters["phase"])
        if filters.get("status"):
            stmt = stmt.where(Document.status == filters["status"])
        if filters.get("condition"):
            stmt = stmt.where(Document.condition.ilike(f"%{filters['condition']}%"))

    result = await session.execute(stmt)
    return [
        RetrievedChunk(
            chunk_id=chunk.id,
            chunk_uid=chunk.chunk_uid,
            chunk_source=chunk.chunk_source,
            document_id=document.id,
            nct_id=document.nct_id,
            title=document.title,
            chunk_text=chunk.chunk_text,
            distance=float(distance_value),
            semantic_score=float(semantic_score_value),
            keyword_score=float(keyword_score_value),
            blended_score=float(blended_score_value),
        )
        for chunk, document, distance_value, semantic_score_value, keyword_score_value, blended_score_value in result.all()
    ]

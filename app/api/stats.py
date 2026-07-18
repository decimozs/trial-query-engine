from fastapi import APIRouter
from sqlalchemy import func, select

from app.db.session import async_session
from app.models import Document, DocumentChunk
from app.services.persistence import get_stats as get_persistence_stats


router = APIRouter(tags=["stats"])


@router.get("/stats")
async def get_stats() -> dict:
    async with async_session() as session:
        documents_count = await session.scalar(select(func.count()).select_from(Document))
        chunks_count = await session.scalar(select(func.count()).select_from(DocumentChunk))

    persistence_stats = await get_persistence_stats()

    return {
        "documents_count": documents_count or 0,
        "chunks_count": chunks_count or 0,
        **persistence_stats,
    }

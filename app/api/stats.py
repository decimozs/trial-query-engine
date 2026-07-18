from fastapi import APIRouter
from sqlalchemy import func, select

from app.db.session import async_session
from app.models import Document, DocumentChunk
from app.mongo.client import mongo_db


router = APIRouter(tags=["stats"])


@router.get("/stats")
async def get_stats() -> dict:
    async with async_session() as session:
        documents_count = await session.scalar(select(func.count()).select_from(Document))
        chunks_count = await session.scalar(select(func.count()).select_from(DocumentChunk))

    latency_cursor = await mongo_db.chat_history.aggregate(
        [
            {
                "$group": {
                    "_id": None,
                    "queries_count": {"$sum": 1},
                    "avg_embed_ms": {"$avg": "$latency_ms.embed"},
                    "avg_retrieval_ms": {"$avg": "$latency_ms.retrieval"},
                    "avg_llm_ms": {"$avg": "$latency_ms.llm"},
                }
            }
        ]
    )
    latency_rows = await latency_cursor.to_list(length=1)
    latency = latency_rows[0] if latency_rows else {}
    latest_run = await mongo_db.ingestion_runs.find_one(
        {},
        {
            "_id": 0,
            "condition_queried": 1,
            "studies_fetched": 1,
            "studies_ingested": 1,
            "studies_skipped": 1,
            "status": 1,
            "started_at": 1,
            "completed_at": 1,
        },
        sort=[("started_at", -1)],
    )

    return {
        "documents_count": documents_count or 0,
        "chunks_count": chunks_count or 0,
        "queries_count": latency.get("queries_count", 0),
        "avg_embed_ms": latency.get("avg_embed_ms"),
        "avg_retrieval_ms": latency.get("avg_retrieval_ms"),
        "avg_llm_ms": latency.get("avg_llm_ms"),
        "last_ingestion_run": latest_run,
    }

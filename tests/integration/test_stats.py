from datetime import datetime, timezone
from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app
from app.mongo.client import mongo_db


async def insert_stats_test_history(rows: list[dict]) -> None:
    await mongo_db.chat_history.insert_many(rows)


async def delete_stats_test_history(marker: str) -> None:
    await mongo_db.chat_history.delete_many({"question": {"$regex": marker}})


def test_stats_returns_counts_and_latency_averages() -> None:
    marker = uuid4().hex
    now = datetime.now(timezone.utc)

    with TestClient(app) as client:
        try:
            client.portal.call(
                insert_stats_test_history,
                [
                    {
                        "user_id": 1,
                        "question": f"stats {marker} one",
                        "answer": "one",
                        "retrieved_chunk_ids": [],
                        "retrieved_chunk_uids": [],
                        "latency_ms": {"embed": 10, "retrieval": 20, "llm": 30},
                        "created_at": now,
                    },
                    {
                        "user_id": 1,
                        "question": f"stats {marker} two",
                        "answer": "two",
                        "retrieved_chunk_ids": [],
                        "retrieved_chunk_uids": [],
                        "latency_ms": {"embed": 30, "retrieval": 40, "llm": 50},
                        "created_at": now,
                    },
                ],
            )

            response = client.get("/stats")

            assert response.status_code == 200
            body = response.json()
            assert body["documents_count"] >= 0
            assert body["chunks_count"] >= 0
            assert body["queries_count"] >= 2
            assert body["avg_embed_ms"] is not None
            assert body["avg_retrieval_ms"] is not None
            assert body["avg_llm_ms"] is not None
            assert "last_ingestion_run" in body
        finally:
            client.portal.call(delete_stats_test_history, marker)

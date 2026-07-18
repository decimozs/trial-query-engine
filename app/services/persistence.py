from datetime import datetime, timezone
from typing import Any

from app.mongo.client import mongo_db
from app.schemas.query import QueryLatency, RetrievedChunk
from app.services.ingestion_types import StudyMetadata
from app.services.guardrails.pipeline import blocking_decision, flagged_checks
from app.services.guardrails.types import GuardrailDecision


def make_chat_history_document(
    *,
    user_id: int,
    query_id: str,
    question: str,
    answer: str,
    retrieved_chunks: list[RetrievedChunk],
    latency_ms: QueryLatency,
    guardrail_decisions: list[GuardrailDecision],
) -> dict[str, Any]:
    return {
        "user_id": user_id,
        "query_id": query_id,
        "question": question,
        "answer": answer,
        "retrieved_chunk_ids": [chunk.chunk_id for chunk in retrieved_chunks],
        "retrieved_chunk_uids": [chunk.chunk_uid for chunk in retrieved_chunks],
        "guardrail_blocked": blocking_decision(guardrail_decisions) is not None,
        "guardrail_flags": flagged_checks(guardrail_decisions),
        "latency_ms": latency_ms.model_dump(),
        "created_at": datetime.now(timezone.utc),
    }


def make_guardrail_documents(
    *,
    user_id: int,
    query_id: str,
    decisions: list[GuardrailDecision],
) -> list[dict[str, Any]]:
    return [
        {
            "user_id": user_id,
            "query_id": query_id,
            "stage": decision.stage,
            "check_name": decision.check_name,
            "result": decision.result,
            "detail": decision.detail,
            "metadata": decision.metadata,
            "created_at": datetime.now(timezone.utc),
        }
        for decision in decisions
    ]


async def log_chat_history(**kwargs) -> None:
    await mongo_db.chat_history.insert_one(make_chat_history_document(**kwargs))


async def log_guardrail_decisions(
    *,
    user_id: int,
    query_id: str,
    decisions: list[GuardrailDecision],
) -> None:
    if decisions:
        await mongo_db.guardrail_log.insert_many(
            make_guardrail_documents(user_id=user_id, query_id=query_id, decisions=decisions)
        )


async def store_raw_document(metadata: StudyMetadata, raw_study: dict[str, Any]) -> None:
    await mongo_db.raw_documents.replace_one(
        {"_id": metadata.nct_id},
        {
            "_id": metadata.nct_id,
            "source": "clinicaltrials.gov",
            "fetched_at": datetime.now(timezone.utc),
            "raw": raw_study,
        },
        upsert=True,
    )


async def start_ingestion_run(condition: str, studies_fetched: int):
    result = await mongo_db.ingestion_runs.insert_one(
        {
            "condition_queried": condition,
            "studies_fetched": studies_fetched,
            "studies_ingested": 0,
            "studies_skipped": 0,
            "started_at": datetime.now(timezone.utc),
            "status": "success",
            "error": None,
        }
    )
    return result.inserted_id


async def complete_ingestion_run(run_id, *, studies_ingested: int, studies_skipped: int) -> None:
    await mongo_db.ingestion_runs.update_one(
        {"_id": run_id},
        {
            "$set": {
                "studies_ingested": studies_ingested,
                "studies_skipped": studies_skipped,
                "completed_at": datetime.now(timezone.utc),
                "status": "success",
            }
        },
    )


async def fail_ingestion_run(
    run_id,
    *,
    condition: str,
    studies_fetched: int,
    studies_ingested: int,
    studies_skipped: int,
    started_at: datetime,
    error: str,
) -> None:
    failure = {
        "studies_ingested": studies_ingested,
        "studies_skipped": studies_skipped,
        "completed_at": datetime.now(timezone.utc),
        "status": "failed",
        "error": error,
    }
    if run_id is None:
        await mongo_db.ingestion_runs.insert_one(
            {
                "condition_queried": condition,
                "studies_fetched": studies_fetched,
                "started_at": started_at,
                **failure,
            }
        )
    else:
        await mongo_db.ingestion_runs.update_one({"_id": run_id}, {"$set": failure})


async def get_stats() -> dict[str, Any]:
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
        "queries_count": latency.get("queries_count", 0),
        "avg_embed_ms": latency.get("avg_embed_ms"),
        "avg_retrieval_ms": latency.get("avg_retrieval_ms"),
        "avg_llm_ms": latency.get("avg_llm_ms"),
        "last_ingestion_run": latest_run,
    }

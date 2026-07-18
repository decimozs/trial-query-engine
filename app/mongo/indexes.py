from pymongo import ASCENDING

from app.mongo.client import mongo_db


async def create_mongo_indexes() -> None:
    await mongo_db.raw_documents.create_index([("source", ASCENDING)])
    await mongo_db.raw_documents.create_index([("fetched_at", ASCENDING)])

    await mongo_db.chat_history.create_index([("user_id", ASCENDING)])
    await mongo_db.chat_history.create_index([("created_at", ASCENDING)])
    await mongo_db.chat_history.create_index([("retrieved_chunk_ids", ASCENDING)])

    await mongo_db.ingestion_runs.create_index([("condition_queried", ASCENDING)])
    await mongo_db.ingestion_runs.create_index([("started_at", ASCENDING)])
    await mongo_db.ingestion_runs.create_index([("status", ASCENDING)])

    await mongo_db.guardrail_log.create_index([("query_id", ASCENDING)])
    await mongo_db.guardrail_log.create_index([("user_id", ASCENDING)])
    await mongo_db.guardrail_log.create_index([("stage", ASCENDING)])
    await mongo_db.guardrail_log.create_index([("result", ASCENDING)])
    await mongo_db.guardrail_log.create_index([("created_at", ASCENDING)])

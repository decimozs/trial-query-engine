import asyncio

from sqlalchemy import delete

from app.db.session import async_session, engine
from app.models import Document, DocumentChunk, User
from app.mongo.client import close_mongo, mongo_db, ping_mongo
from app.mongo.schemas import ChatHistory, ChatLatency, RawDocument


SMOKE_EMAIL = "mongo-smoke@example.com"
SMOKE_NCT_ID = "NCTMONGO0001"


async def cleanup_postgres() -> None:
    async with async_session() as session:
        await session.execute(delete(User).where(User.email == SMOKE_EMAIL))
        await session.execute(delete(Document).where(Document.nct_id == SMOKE_NCT_ID))
        await session.commit()


async def cleanup_mongo() -> None:
    await mongo_db.raw_documents.delete_one({"_id": SMOKE_NCT_ID})
    await mongo_db.chat_history.delete_many({"question": "Mongo smoke question?"})


async def create_postgres_records() -> tuple[int, int]:
    embedding = [0.0] * 384
    embedding[0] = 1.0

    async with async_session() as session:
        user = User(
            email=SMOKE_EMAIL,
            hashed_password="not-a-real-password-hash",
            role="user",
        )
        document = Document(
            nct_id=SMOKE_NCT_ID,
            title="Mongo Smoke Trial",
            condition="Mongo Smoke Condition",
            phase="PHASE3",
            status="RECRUITING",
            brief_summary="Mongo smoke test document.",
        )
        chunk = DocumentChunk(
            chunk_uid="mongo-smoke-chunk-0",
            chunk_source="brief_summary",
            chunk_index=0,
            chunk_text="Mongo smoke chunk.",
            embedding=embedding,
        )
        document.chunks.append(chunk)
        session.add_all([user, document])
        await session.flush()
        user_id = user.id
        chunk_id = chunk.id
        await session.commit()

    return user_id, chunk_id


async def main() -> None:
    await ping_mongo()
    await cleanup_mongo()
    await cleanup_postgres()

    user_id, chunk_id = await create_postgres_records()

    raw_document = RawDocument(
        id=SMOKE_NCT_ID,
        raw={
            "protocolSection": {
                "identificationModule": {"nctId": SMOKE_NCT_ID},
                "statusModule": {"overallStatus": "RECRUITING"},
            }
        },
    )
    await mongo_db.raw_documents.insert_one(
        raw_document.model_dump(by_alias=True, mode="python")
    )

    chat_history = ChatHistory(
        user_id=user_id,
        question="Mongo smoke question?",
        answer="Mongo smoke answer.",
        retrieved_chunk_ids=[chunk_id],
        latency_ms=ChatLatency(embed=1, retrieval=2, llm=3),
    )
    await mongo_db.chat_history.insert_one(
        chat_history.model_dump(by_alias=True, exclude_none=True, mode="python")
    )

    saved_raw = await mongo_db.raw_documents.find_one({"_id": SMOKE_NCT_ID})
    assert saved_raw is not None
    assert saved_raw["_id"] == SMOKE_NCT_ID

    saved_chat = await mongo_db.chat_history.find_one({"question": "Mongo smoke question?"})
    assert saved_chat is not None
    assert saved_chat["user_id"] == user_id
    assert saved_chat["retrieved_chunk_ids"] == [chunk_id]

    await cleanup_mongo()
    await cleanup_postgres()
    await close_mongo()
    await engine.dispose()
    print("mongo smoke test ok")


if __name__ == "__main__":
    asyncio.run(main())

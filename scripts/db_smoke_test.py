import asyncio

from sqlalchemy import delete, select
from sqlalchemy.orm import selectinload

from app.db.session import async_session, engine
from app.models import Document, DocumentChunk, User


SMOKE_EMAIL = "db-smoke@example.com"
SMOKE_NCT_ID = "NCTSMOKE0001"


async def main() -> None:
    embedding = [0.0] * 384
    embedding[0] = 1.0

    async with async_session() as session:
        await session.execute(delete(User).where(User.email == SMOKE_EMAIL))
        await session.execute(delete(Document).where(Document.nct_id == SMOKE_NCT_ID))
        await session.commit()

        user = User(
            email=SMOKE_EMAIL,
            hashed_password="not-a-real-password-hash",
            role="user",
        )
        document = Document(
            nct_id=SMOKE_NCT_ID,
            title="Smoke Test Trial",
            condition="Smoke Condition",
            phase="PHASE3",
            status="RECRUITING",
            brief_summary="Smoke test document for DB wiring.",
        )
        document.chunks.append(
            DocumentChunk(
                chunk_uid="db-smoke-chunk-0",
                chunk_source="brief_summary",
                chunk_index=0,
                chunk_text="Smoke chunk for vector search.",
                embedding=embedding,
            )
        )
        session.add_all([user, document])
        await session.commit()

        result = await session.execute(
            select(Document)
            .options(selectinload(Document.chunks))
            .where(Document.nct_id == SMOKE_NCT_ID)
        )
        saved_document = result.scalar_one()
        assert len(saved_document.chunks) == 1

        vector_result = await session.execute(
            select(DocumentChunk)
            .order_by(DocumentChunk.embedding.cosine_distance(embedding))
            .limit(1)
        )
        nearest_chunk = vector_result.scalar_one()
        assert nearest_chunk.chunk_text == "Smoke chunk for vector search."

        await session.execute(delete(User).where(User.email == SMOKE_EMAIL))
        await session.execute(delete(Document).where(Document.nct_id == SMOKE_NCT_ID))
        await session.commit()

    await engine.dispose()
    print("db smoke test ok")


if __name__ == "__main__":
    asyncio.run(main())

import asyncio

from sqlalchemy import func, select

from app.db.session import async_session, engine
from app.models import Document, DocumentChunk
from app.mongo.client import close_mongo, mongo_db
from app.services.ingestion import ingest_studies


async def main() -> None:
    condition = "Type 2 Diabetes"
    max_studies = 2

    async with async_session() as session:
        ingested = await ingest_studies(condition, max_studies, session)
        assert ingested > 0

        document_count = await session.scalar(select(func.count()).select_from(Document))
        chunk_count = await session.scalar(select(func.count()).select_from(DocumentChunk))
        assert document_count and document_count > 0
        assert chunk_count and chunk_count > 0

        result = await session.execute(select(Document).limit(1))
        document = result.scalar_one()
        raw_document = await mongo_db.raw_documents.find_one({"_id": document.nct_id})
        assert raw_document is not None

        chunk_result = await session.execute(
            select(DocumentChunk).where(DocumentChunk.document_id == document.id).limit(1)
        )
        chunk = chunk_result.scalar_one()
        assert len(chunk.embedding) == 384

    await close_mongo()
    await engine.dispose()
    print(f"ingest smoke test ok: {ingested} studies ingested")


if __name__ == "__main__":
    asyncio.run(main())

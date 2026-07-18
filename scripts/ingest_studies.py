import asyncio
import os

from app.db.session import async_session, engine
from app.mongo.client import close_mongo
from app.services.ingestion import ingest_studies


async def main() -> None:
    condition = os.getenv("CONDITION", "Type 2 Diabetes")
    max_studies = int(os.getenv("MAX_STUDIES", "100"))

    async with async_session() as session:
        count = await ingest_studies(condition, max_studies, session)
        print(f"ingested {count} studies for condition: {condition}")

    await close_mongo()
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())

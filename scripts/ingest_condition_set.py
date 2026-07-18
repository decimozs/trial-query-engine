import asyncio
import os

from app.db.session import async_session, engine
from app.mongo.client import close_mongo
from app.services.ingestion import ingest_studies

DEFAULT_CONDITIONS = [
    "Type 2 Diabetes",
    "Breast Cancer",
    "Hypertension",
    "Asthma",
]


def parse_conditions(value: str | None) -> list[str]:
    if not value:
        return DEFAULT_CONDITIONS
    conditions = [condition.strip() for condition in value.split("|") if condition.strip()]
    return conditions or DEFAULT_CONDITIONS


async def main() -> None:
    conditions = parse_conditions(os.getenv("CONDITIONS"))
    max_studies_per_condition = int(os.getenv("MAX_STUDIES_PER_CONDITION", "75"))
    total = 0

    async with async_session() as session:
        for condition in conditions:
            count = await ingest_studies(condition, max_studies_per_condition, session)
            total += count
            print(f"ingested {count} studies for condition: {condition}")

    print(f"ingested {total} studies across {len(conditions)} conditions")
    await close_mongo()
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())

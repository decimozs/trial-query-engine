import asyncio

from app.mongo.client import close_mongo, ping_mongo
from app.mongo.indexes import create_mongo_indexes


async def main() -> None:
    await ping_mongo()
    await create_mongo_indexes()
    await close_mongo()
    print("mongo indexes ok")


if __name__ == "__main__":
    asyncio.run(main())

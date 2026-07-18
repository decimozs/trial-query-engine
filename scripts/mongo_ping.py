import asyncio

from app.mongo.client import close_mongo, ping_mongo


async def main() -> None:
    ok = await ping_mongo()
    await close_mongo()
    if not ok:
        raise RuntimeError("MongoDB ping failed")
    print("mongo ping ok")


if __name__ == "__main__":
    asyncio.run(main())

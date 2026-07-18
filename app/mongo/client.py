import asyncio
from typing import Any

from pymongo import AsyncMongoClient

from app.core.config import settings


_clients: dict[int, AsyncMongoClient] = {}


def get_mongo_client() -> AsyncMongoClient:
    loop_id = id(asyncio.get_running_loop())
    client = _clients.get(loop_id)
    if client is None:
        client = AsyncMongoClient(settings.mongo_url)
        _clients[loop_id] = client
    return client


def get_mongo_db():
    return get_mongo_client()[settings.mongo_db_name]


class MongoDatabaseProxy:
    def __getattr__(self, name: str) -> Any:
        return getattr(get_mongo_db(), name)

    def __getitem__(self, name: str) -> Any:
        return get_mongo_db()[name]


mongo_db = MongoDatabaseProxy()


async def ping_mongo() -> bool:
    result = await get_mongo_client().admin.command("ping")
    return result.get("ok") == 1.0


async def close_mongo() -> None:
    loop_id = id(asyncio.get_running_loop())
    client = _clients.pop(loop_id, None)
    if client is not None:
        await client.close()

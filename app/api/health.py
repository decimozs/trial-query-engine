from datetime import datetime, timezone

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.core.config import settings
from app.db.session import async_session
from app.mongo.client import ping_mongo


router = APIRouter()


async def ping_postgres() -> bool:
    async with async_session() as session:
        await session.execute(text("SELECT 1"))
    return True


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@router.get("/health")
async def health_check():
    try:
        postgres_ok = await ping_postgres()
    except Exception:
        postgres_ok = False

    try:
        mongo_ok = await ping_mongo()
    except Exception:
        mongo_ok = False

    ok = postgres_ok and mongo_ok
    payload = {
        "ok": ok,
        "services": {
            "postgres": "ok" if postgres_ok else "error",
            "mongo": "ok" if mongo_ok else "error",
        },
        "metadata": {
            "environment": settings.environment,
            "timestamp": utc_timestamp(),
        },
    }

    if not ok:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content=payload,
        )

    return payload

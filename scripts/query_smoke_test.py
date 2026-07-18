import asyncio
import os
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.db.session import async_session
from app.main import app
from app.mongo.client import close_mongo


async def delete_user(email: str) -> None:
    async with async_session() as session:
        await session.execute(text("DELETE FROM users WHERE email = :email"), {"email": email})
        await session.commit()


async def delete_chat_history(question: str) -> None:
    from app.mongo.client import mongo_db

    chats = await mongo_db.chat_history.find({"question": question}).to_list(length=100)
    query_ids = [chat["query_id"] for chat in chats if chat.get("query_id")]
    if query_ids:
        await mongo_db.guardrail_log.delete_many({"query_id": {"$in": query_ids}})
    await mongo_db.chat_history.delete_many({"question": question})


async def get_chat_history(question: str):
    from app.mongo.client import mongo_db

    return await mongo_db.chat_history.find_one({"question": question})


async def main() -> None:
    question = os.getenv(
        "QUESTION",
        "What eligibility criteria appear across the available clinical trials?",
    )
    email = f"query-smoke-{uuid4().hex}@example.com"

    with TestClient(app) as client:
        try:
            register = client.post(
                "/auth/register", json={"email": email, "password": "secret123"}
            )
            assert register.status_code == 200
            login = client.post(
                "/auth/login", data={"username": email, "password": "secret123"}
            )
            assert login.status_code == 200
            token = login.json()["access_token"]

            response = client.post(
                "/query",
                json={"question": question, "top_k": 3},
                headers={"Authorization": f"Bearer {token}"},
            )
            assert response.status_code == 200
            assert "event: retrieval" in response.text
            assert "event: done" in response.text
            print(response.text)

            chat_history = client.portal.call(get_chat_history, question)
            assert chat_history is not None
            assert chat_history["retrieved_chunk_ids"]
            assert chat_history["answer"].strip()
            print(f"query smoke test ok: chat_history_id={chat_history['_id']}")
        finally:
            client.portal.call(delete_chat_history, question)
            client.portal.call(delete_user, email)

    await close_mongo()


if __name__ == "__main__":
    asyncio.run(main())

from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.db.session import async_session
from app.main import app


def unique_email() -> str:
    return f"ingest-{uuid4().hex}@example.com"


async def delete_user(email: str) -> None:
    async with async_session() as session:
        await session.execute(text("DELETE FROM users WHERE email = :email"), {"email": email})
        await session.commit()


async def promote_user(email: str) -> None:
    async with async_session() as session:
        await session.execute(
            text("UPDATE users SET role = 'admin' WHERE email = :email"), {"email": email}
        )
        await session.commit()


def register(client: TestClient, email: str) -> None:
    response = client.post("/auth/register", json={"email": email, "password": "secret123"})
    assert response.status_code == 200


def login(client: TestClient, email: str) -> str:
    response = client.post("/auth/login", data={"username": email, "password": "secret123"})
    assert response.status_code == 200
    return response.json()["access_token"]


def test_documents_ingest_requires_admin(monkeypatch) -> None:
    async def fake_ingest_studies(condition, max_studies, session):
        return 3

    monkeypatch.setattr("app.api.documents.ingest_studies", fake_ingest_studies)
    email = unique_email()

    with TestClient(app) as client:
        try:
            missing_token = client.post(
                "/documents/ingest", json={"condition": "Type 2 Diabetes", "max_studies": 3}
            )
            assert missing_token.status_code == 401

            register(client, email)
            user_token = login(client, email)
            user_response = client.post(
                "/documents/ingest",
                json={"condition": "Type 2 Diabetes", "max_studies": 3},
                headers={"Authorization": f"Bearer {user_token}"},
            )
            assert user_response.status_code == 403

            client.portal.call(promote_user, email)
            admin_token = login(client, email)
            admin_response = client.post(
                "/documents/ingest",
                json={"condition": "Type 2 Diabetes", "max_studies": 3},
                headers={"Authorization": f"Bearer {admin_token}"},
            )
            assert admin_response.status_code == 200
            assert admin_response.json() == {"studies_ingested": 3, "status": "ok"}
        finally:
            client.portal.call(delete_user, email)

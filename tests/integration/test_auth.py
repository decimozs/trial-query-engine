from uuid import uuid4

from fastapi.testclient import TestClient
from app.services.jwt import create_access_token
from sqlalchemy import text

from app.db.session import async_session
from app.main import app


def unique_email() -> str:
    return f"auth-{uuid4().hex}@example.com"


async def delete_user(email: str) -> None:
    async with async_session() as session:
        await session.execute(text("DELETE FROM users WHERE email = :email"), {"email": email})
        await session.commit()


async def promote_user(email: str) -> None:
    async with async_session() as session:
        await session.execute(
            text("UPDATE users SET role = 'admin' WHERE email = :email"),
            {"email": email},
        )
        await session.commit()


def register(client: TestClient, email: str, password: str = "secret123"):
    return client.post("/auth/register", json={"email": email, "password": password})


def login(client: TestClient, email: str, password: str = "secret123"):
    return client.post(
        "/auth/login",
        data={"username": email, "password": password},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )


def test_register_returns_user_without_password_fields() -> None:
    email = unique_email()

    with TestClient(app) as client:
        try:
            response = register(client, email)

            assert response.status_code == 200
            body = response.json()
            assert body["id"] > 0
            assert body["email"] == email
            assert body["role"] == "user"
            assert "created_at" in body
            assert "password" not in body
            assert "hashed_password" not in body
        finally:
            client.portal.call(delete_user, email)


def test_register_duplicate_email_returns_conflict() -> None:
    email = unique_email()

    with TestClient(app) as client:
        try:
            assert register(client, email).status_code == 200
            response = register(client, email)

            assert response.status_code == 409
        finally:
            client.portal.call(delete_user, email)


def test_login_returns_bearer_token_and_rejects_bad_credentials() -> None:
    email = unique_email()

    with TestClient(app) as client:
        try:
            assert register(client, email).status_code == 200

            response = login(client, email)
            assert response.status_code == 200
            body = response.json()
            assert body["token_type"] == "bearer"
            assert body["access_token"]

            wrong_password = login(client, email, "wrong")
            unknown_email = login(client, unique_email())
            assert wrong_password.status_code == 401
            assert unknown_email.status_code == 401
            assert wrong_password.json()["detail"] == unknown_email.json()["detail"]
        finally:
            client.portal.call(delete_user, email)


def test_me_requires_valid_token_and_returns_current_user() -> None:
    email = unique_email()

    with TestClient(app) as client:
        try:
            assert register(client, email).status_code == 200
            token = login(client, email).json()["access_token"]

            missing_token = client.get("/me")
            invalid_token = client.get("/me", headers={"Authorization": "Bearer invalid"})
            response = client.get("/me", headers={"Authorization": f"Bearer {token}"})

            assert missing_token.status_code == 401
            assert invalid_token.status_code == 401
            assert response.status_code == 200
            assert response.json()["email"] == email
        finally:
            client.portal.call(delete_user, email)


def test_admin_check_rejects_user_and_accepts_admin_token() -> None:
    email = unique_email()

    with TestClient(app) as client:
        try:
            assert register(client, email).status_code == 200
            user_token = login(client, email).json()["access_token"]

            user_response = client.get(
                "/admin/check", headers={"Authorization": f"Bearer {user_token}"}
            )
            assert user_response.status_code == 403

            client.portal.call(promote_user, email)
            admin_token = login(client, email).json()["access_token"]
            admin_response = client.get(
                "/admin/check", headers={"Authorization": f"Bearer {admin_token}"}
            )

            assert admin_response.status_code == 200
            assert admin_response.json() == {"ok": True}
        finally:
            client.portal.call(delete_user, email)


def test_me_rejects_missing_subject_and_deleted_user_token() -> None:
    email = unique_email()

    with TestClient(app) as client:
        try:
            assert register(client, email).status_code == 200
            user = client.get("/me", headers={"Authorization": f"Bearer {login(client, email).json()['access_token']}"}).json()
            no_sub_token = create_access_token({"foo": "bar"})
            deleted_user_token = create_access_token({"sub": str(user["id"])})

            assert client.get("/me", headers={"Authorization": f"Bearer {no_sub_token}"}).status_code == 401
            client.portal.call(delete_user, email)
            assert client.get("/me", headers={"Authorization": f"Bearer {deleted_user_token}"}).status_code == 401
        finally:
            client.portal.call(delete_user, email)

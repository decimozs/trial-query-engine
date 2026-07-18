from datetime import timedelta

import pytest
from jose import ExpiredSignatureError, JWTError

from app.services.jwt import create_access_token, decode_access_token
from app.core.config import Settings


def test_create_access_token_decodes_sub_role_and_exp() -> None:
    token = create_access_token({"sub": "123"})

    payload = decode_access_token(token)

    assert payload["sub"] == "123"
    assert "exp" in payload


def test_decode_access_token_rejects_expired_token() -> None:
    token = create_access_token(
        {"sub": "123"}, expires_delta=timedelta(seconds=-1)
    )

    with pytest.raises(ExpiredSignatureError):
        decode_access_token(token)


def test_decode_access_token_rejects_tampered_token() -> None:
    token = create_access_token({"sub": "123"})
    header, payload, signature = token.split(".")
    replacement = "A" if signature[0] != "A" else "B"
    tampered = f"{header}.{payload}.{replacement}{signature[1:]}"

    with pytest.raises(JWTError):
        decode_access_token(tampered)


def test_non_local_settings_reject_default_jwt_secret() -> None:
    with pytest.raises(ValueError):
        Settings(environment="production", jwt_secret_key="change-me-in-local-dev")

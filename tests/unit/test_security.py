from app.services.security import hash_password, verify_password
from app.schemas.user import UserCreate
import pytest


def test_hash_password_does_not_return_plaintext_and_verifies() -> None:
    hashed = hash_password("secret123")

    assert hashed != "secret123"
    assert verify_password("secret123", hashed) is True
    assert verify_password("wrong", hashed) is False


def test_user_create_rejects_short_blank_and_too_long_passwords() -> None:
    with pytest.raises(ValueError):
        UserCreate(email="test@example.com", password="short")
    with pytest.raises(ValueError):
        UserCreate(email="test@example.com", password="        ")
    with pytest.raises(ValueError):
        UserCreate(email="test@example.com", password="x" * 73)

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
from datetime import UTC, datetime, timedelta
from typing import Any

from app.core.config import settings

JWT_ALGORITHM = "HS256"
PASSWORD_HASH_ITERATIONS = 210_000


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        PASSWORD_HASH_ITERATIONS,
    )
    return "$".join(
        [
            "pbkdf2_sha256",
            str(PASSWORD_HASH_ITERATIONS),
            _b64encode(salt),
            _b64encode(digest),
        ]
    )


def verify_password(password: str, hashed_password: str) -> bool:
    try:
        algorithm, iterations, salt, expected_digest = hashed_password.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False

        digest = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            _b64decode(salt),
            int(iterations),
        )
        return hmac.compare_digest(_b64encode(digest), expected_digest)
    except (ValueError, TypeError):
        return False


def create_access_token(subject: str, expires_delta: timedelta | None = None) -> str:
    expires_at = datetime.now(UTC) + (
        expires_delta or timedelta(minutes=settings.access_token_expire_minutes)
    )
    payload = {
        "sub": subject,
        "exp": int(expires_at.timestamp()),
        "iat": int(datetime.now(UTC).timestamp()),
    }
    header = {
        "alg": JWT_ALGORITHM,
        "typ": "JWT",
    }
    encoded_header = _json_b64encode(header)
    encoded_payload = _json_b64encode(payload)
    signature = _sign(f"{encoded_header}.{encoded_payload}")
    return f"{encoded_header}.{encoded_payload}.{signature}"


def decode_access_token(token: str) -> dict[str, Any]:
    try:
        encoded_header, encoded_payload, signature = token.split(".", 2)
    except ValueError as exc:
        raise ValueError("Invalid token format") from exc

    expected_signature = _sign(f"{encoded_header}.{encoded_payload}")
    if not hmac.compare_digest(signature, expected_signature):
        raise ValueError("Invalid token signature")

    header = json.loads(_b64decode(encoded_header))
    if header.get("alg") != JWT_ALGORITHM:
        raise ValueError("Unsupported token algorithm")

    payload = json.loads(_b64decode(encoded_payload))
    expires_at = payload.get("exp")
    if not isinstance(expires_at, int):
        raise ValueError("Token missing exp")
    if expires_at < int(datetime.now(UTC).timestamp()):
        raise ValueError("Token expired")

    return payload


def _sign(value: str) -> str:
    digest = hmac.new(
        settings.jwt_secret_key.encode("utf-8"),
        value.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    return _b64encode(digest)


def _json_b64encode(value: dict[str, Any]) -> str:
    raw = json.dumps(value, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return _b64encode(raw)


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)

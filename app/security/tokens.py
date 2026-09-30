"""Выдача и проверка JWT. В токене только user_id (sub); роль всегда берется из БД."""

import uuid
from datetime import UTC, datetime, timedelta

import jwt


class InvalidTokenError(Exception):
    pass


def create_access_token(*, user_id: uuid.UUID, secret: str, algorithm: str, expires_minutes: int,
                        now: datetime | None = None) -> str:
    issued = now or datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "iat": issued,
        "exp": issued + timedelta(minutes=expires_minutes),
    }
    return jwt.encode(payload, secret, algorithm=algorithm)


def decode_access_token(token: str, *, secret: str, algorithm: str) -> uuid.UUID:
    try:
        payload = jwt.decode(token, secret, algorithms=[algorithm], options={"require": ["exp", "sub"]})
        return uuid.UUID(payload["sub"])
    except (jwt.PyJWTError, ValueError, KeyError) as exc:
        raise InvalidTokenError(str(exc)) from exc

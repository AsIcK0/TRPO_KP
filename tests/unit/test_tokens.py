import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.security.tokens import InvalidTokenError, create_access_token, decode_access_token

SECRET = "x" * 40


def test_roundtrip_contains_only_user_id():
    user_id = uuid.uuid4()
    token = create_access_token(user_id=user_id, secret=SECRET, algorithm="HS256", expires_minutes=5)
    assert decode_access_token(token, secret=SECRET, algorithm="HS256") == user_id


def test_wrong_secret_expired_and_garbage_are_rejected():
    user_id = uuid.uuid4()
    token = create_access_token(user_id=user_id, secret=SECRET, algorithm="HS256", expires_minutes=5)
    expired = create_access_token(user_id=user_id, secret=SECRET, algorithm="HS256", expires_minutes=1,
                                  now=datetime.now(UTC) - timedelta(hours=1))
    for bad, secret in ((token, "y" * 40), (expired, SECRET), ("not-a-jwt", SECRET)):
        with pytest.raises(InvalidTokenError):
            decode_access_token(bad, secret=secret, algorithm="HS256")

"""Low-level auth primitives only: PIN hashing and JWTs. No DB, no business rules."""
import asyncio
import hashlib
import hmac
import uuid
from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from config import settings

_hasher = PasswordHasher()


def _prehash(pin: str) -> str:
    # Keyed hash first: if the DB leaks without PIN_PEPPER, the 1M possible
    # PINs can't be brute-forced offline.
    return hmac.new(settings.PIN_PEPPER.encode(), pin.encode(), hashlib.sha256).hexdigest()


# Verified against when the username doesn't exist, so timing doesn't reveal it
DUMMY_PIN_HASH = _hasher.hash(_prehash("000000"))


async def hash_pin(pin: str) -> str:
    return await asyncio.to_thread(_hasher.hash, _prehash(pin))


async def verify_pin(pin_hash: str, pin: str) -> bool:
    def _verify() -> bool:
        try:
            return _hasher.verify(pin_hash, _prehash(pin))
        except (VerificationError, InvalidHashError):
            return False

    return await asyncio.to_thread(_verify)


def create_access_token(user_id: uuid.UUID) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> uuid.UUID | None:
    try:
        payload = jwt.decode(
            token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM]
        )
        return uuid.UUID(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        return None
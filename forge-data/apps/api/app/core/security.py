"""
Security utilities:
  - JWT creation and verification (python-jose)
  - Password hashing (passlib bcrypt)
  - Field-level encryption for sensitive values (cryptography Fernet)
  - Token hashing for Redis storage
"""

import base64
import hashlib
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from jose import JWTError, jwt
from passlib.context import CryptContext

from app.config import settings

# ── Password hashing ───────────────────────────────────────────────────────────

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def get_password_hash(password: str) -> str:
    """Return a bcrypt hash of *password*."""
    return _pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Return True if *plain_password* matches *hashed_password*."""
    return _pwd_context.verify(plain_password, hashed_password)


# ── JWT tokens ─────────────────────────────────────────────────────────────────


def generate_jti() -> str:
    """Generate a unique JWT ID for token identification/blacklisting."""
    return str(uuid.uuid4())


def create_access_token(data: dict[str, Any], jti: str | None = None) -> str:
    """Create a signed JWT access token that expires in ``jwt_access_token_expire_minutes``."""
    to_encode = data.copy()
    expire = datetime.now(UTC) + timedelta(minutes=settings.jwt_access_token_expire_minutes)
    to_encode.update(
        {
            "exp": expire,
            "type": "access",
            "jti": jti or generate_jti(),
        }
    )
    return jwt.encode(to_encode, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_refresh_token(data: dict[str, Any], jti: str | None = None) -> str:
    """Create a signed JWT refresh token that expires in ``jwt_refresh_token_expire_days``."""
    to_encode = data.copy()
    expire = datetime.now(UTC) + timedelta(days=settings.jwt_refresh_token_expire_days)
    to_encode.update(
        {
            "exp": expire,
            "type": "refresh",
            "jti": jti or generate_jti(),
        }
    )
    return jwt.encode(to_encode, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def verify_token(token: str) -> dict[str, Any] | None:
    """
    Decode and verify a JWT token.
    Returns the payload dict on success, or None if the token is invalid/expired.
    """
    if not token:
        return None
    try:
        payload: dict[str, Any] = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
        )
        return payload
    except JWTError:
        return None


# ── Token hashing (for Redis storage) ────────────────────────────────────────


def hash_token(token: str) -> str:
    """SHA-256 hash of a token — used as Redis key for refresh token storage."""
    return hashlib.sha256(token.encode()).hexdigest()


# ── Fernet field-level encryption ─────────────────────────────────────────────


def _derive_fernet_key() -> bytes:
    """
    Derive a deterministic 32-byte Fernet key from the JWT_SECRET using PBKDF2.
    The salt is configurable so that a site administrator can rotate it when
    migrating all encrypted data.
    """
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=settings.encryption_salt.encode(),
        iterations=390_000,  # OWASP 2023 recommended minimum for SHA-256
    )
    key_bytes = kdf.derive(settings.jwt_secret.encode())
    return base64.urlsafe_b64encode(key_bytes)


_fernet: Fernet | None = None


def _get_fernet() -> Fernet:
    global _fernet
    if _fernet is None:
        _fernet = Fernet(_derive_fernet_key())
    return _fernet


def encrypt_field(value: str) -> str:
    """Encrypt *value* and return a URL-safe base64 ciphertext string."""
    return _get_fernet().encrypt(value.encode()).decode()


def decrypt_field(ciphertext: str) -> str:
    """Decrypt a ciphertext produced by :func:`encrypt_field`."""
    return _get_fernet().decrypt(ciphertext.encode()).decode()

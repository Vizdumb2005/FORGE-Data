"""First-run setup router.

GET  /api/v1/setup/status      — public, returns whether setup is needed
POST /api/v1/setup/initialize  — one-time only; permanently disabled once any user exists

Security model:
- initialize is only callable when the users table is empty (zero accounts).
- Secrets are generated server-side with secrets.token_hex — never derived from
  user input and never returned to the browser.
- After the first user is created the endpoint returns 409 forever.
"""

import logging
import secrets
from pathlib import Path

from fastapi import APIRouter, Header
from fastapi.responses import JSONResponse
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func, select

from app.config import settings
from app.core.security import get_password_hash
from app.dependencies import DBSession
from app.models.user import User

logger = logging.getLogger(__name__)
router = APIRouter()


def _resolve_env_path() -> Path:
    """Resolve a writable .env path in both local and container layouts."""
    current = Path(__file__).resolve()
    for parent in current.parents:
        candidate = parent / ".env"
        if candidate.exists():
            return candidate
    # Container/dev fallback
    return Path("/app/.env")


_ENV_PATH = _resolve_env_path()


# ── Schemas ───────────────────────────────────────────────────────────────────


class SetupStatusResponse(BaseModel):
    needs_setup: bool
    has_users: bool
    has_weak_secrets: bool


class SetupInitRequest(BaseModel):
    admin_email: EmailStr
    admin_password: str = Field(min_length=12, max_length=128)
    admin_name: str = Field(min_length=1, max_length=255)
    # Optional AI provider to pre-configure (user can skip)
    ollama_base_url: str = ""
    openai_api_key: str = ""
    anthropic_api_key: str = ""


class SetupInitResponse(BaseModel):
    ok: bool
    message: str


# ── Helpers ───────────────────────────────────────────────────────────────────

_INSECURE = frozenset(
    {
        "change-me-in-production-use-openssl-rand-hex-32",
        "CHANGE_ME_openssl_rand_hex_32",
        "CHANGE_ME_openssl_rand_hex_16",
        "forge_data_encryption_salt_v1",
        "forge",
        "forgedata123",
        "",
    }
)


def _secrets_are_weak() -> bool:
    return (
        settings.jwt_secret in _INSECURE
        or settings.encryption_salt in _INSECURE
        or settings.minio_secret_key in _INSECURE
        or settings.jupyter_token in _INSECURE
    )


def _patch_env(updates: dict[str, str]) -> None:
    """Read .env, replace or append key=value pairs, write back."""
    if not _ENV_PATH.exists():
        logger.warning("Setup: .env not found at %s — skipping write", _ENV_PATH)
        return

    lines = _ENV_PATH.read_text(encoding="utf-8").splitlines(keepends=True)
    replaced: set[str] = set()

    new_lines: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("#") or "=" not in stripped:
            new_lines.append(line)
            continue
        key = stripped.split("=", 1)[0].strip()
        if key in updates:
            new_lines.append(f"{key}={updates[key]}\n")
            replaced.add(key)
        else:
            new_lines.append(line)

    # Append any keys that weren't already in the file
    for key, val in updates.items():
        if key not in replaced:
            new_lines.append(f"{key}={val}\n")

    _ENV_PATH.write_text("".join(new_lines), encoding="utf-8")


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.get(
    "/status",
    response_model=SetupStatusResponse,
    summary="Check whether first-run setup is required",
)
async def setup_status(db: DBSession) -> SetupStatusResponse:
    count: int = await db.scalar(select(func.count()).select_from(User)) or 0
    weak = _secrets_are_weak()
    return SetupStatusResponse(
        # Setup is one-time only. Once a user exists, /initialize is permanently disabled.
        # Keep weak-secret signal separate so UI can warn without forcing an impossible setup flow.
        needs_setup=count == 0,
        has_users=count > 0,
        has_weak_secrets=weak,
    )


@router.post(
    "/initialize",
    response_model=SetupInitResponse,
    summary="One-time first-run initialization — disabled after first user exists",
)
async def initialize(
    payload: SetupInitRequest,
    db: DBSession,
    x_setup_token: str | None = Header(default=None, alias="X-Setup-Token"),
) -> SetupInitResponse:
    init_token = settings.setup_init_token.strip()
    if init_token and (not x_setup_token or not secrets.compare_digest(x_setup_token, init_token)):
        return JSONResponse(
            status_code=401,
            content={"ok": False, "message": "Unauthorized setup initialization request."},
        )

    # Hard gate: refuse if any user already exists
    count: int = await db.scalar(select(func.count()).select_from(User)) or 0
    if count > 0:
        return JSONResponse(
            status_code=409,
            content={
                "ok": False,
                "message": "Setup already completed. This endpoint is permanently disabled.",
            },
        )

    # 1. Generate strong secrets server-side
    jwt_secret = secrets.token_hex(32)
    encryption_salt = secrets.token_hex(16)
    minio_secret = secrets.token_hex(32)
    jupyter_token = secrets.token_hex(32)
    postgres_password = secrets.token_hex(24)

    # 2. Write secrets to .env (server-side only — never returned to browser)
    env_updates: dict[str, str] = {
        "JWT_SECRET": jwt_secret,
        "ENCRYPTION_SALT": encryption_salt,
        "MINIO_SECRET_KEY": minio_secret,
        "JUPYTER_TOKEN": jupyter_token,
        "POSTGRES_PASSWORD": postgres_password,
        "DATABASE_URL": f"postgresql://forge:{postgres_password}@postgres:5432/forge",
        "MLFLOW_BACKEND_STORE_URI": f"postgresql://forge:{postgres_password}@postgres/forge_mlflow",
    }
    if payload.ollama_base_url:
        env_updates["OLLAMA_BASE_URL"] = payload.ollama_base_url
    if payload.openai_api_key:
        env_updates["OPENAI_API_KEY"] = payload.openai_api_key
    if payload.anthropic_api_key:
        env_updates["ANTHROPIC_API_KEY"] = payload.anthropic_api_key

    try:
        _patch_env(env_updates)
        logger.info("Setup: .env updated with generated secrets")
    except Exception as exc:
        logger.error("Setup: failed to write .env: %s", exc)
        # Non-fatal — secrets are in memory for this session; user must restart

    # 3. Create the admin user with the current (possibly just-written) settings
    #    We use the password hash directly — no need to reload settings for this.
    from zxcvbn import zxcvbn as _zxcvbn

    result = _zxcvbn(payload.admin_password)
    if result["score"] < 3:
        return JSONResponse(
            status_code=422,
            content={
                "ok": False,
                "message": "Admin password is too weak. Use a stronger password (score 3/4+).",
            },
        )

    user = User(
        email=payload.admin_email.lower(),
        hashed_password=get_password_hash(payload.admin_password),
        full_name=payload.admin_name,
        is_active=True,
        is_verified=True,
    )
    db.add(user)
    await db.flush()

    logger.info("Setup: admin user created — %s", payload.admin_email)

    return SetupInitResponse(
        ok=True,
        message="Setup complete. Restart the stack to apply the new secrets.",
    )

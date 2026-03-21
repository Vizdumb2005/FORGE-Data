"""User Pydantic schemas."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

# ── Registration / Login ─────────────────────────────────────────────────────


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=12, max_length=128)
    full_name: str = Field(min_length=1, max_length=255)

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        from zxcvbn import zxcvbn as _zxcvbn

        result = _zxcvbn(v)
        if result["score"] < 3:
            feedback = result.get("feedback", {})
            warning = feedback.get("warning", "")
            suggestions = feedback.get("suggestions", [])
            msg = "Password is too weak (must score 3/4 on strength meter)."
            if warning:
                msg += f" {warning}."
            if suggestions:
                msg += " " + " ".join(suggestions)
            raise ValueError(msg)
        return v


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1)


class UserUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=255)
    preferred_llm_provider: str | None = Field(default=None, min_length=1, max_length=64)


# ── API key management ────────────────────────────────────────────────────────


class ApiKeysUpdate(BaseModel):
    openai_api_key: str | None = None
    anthropic_api_key: str | None = None
    ollama_base_url: str | None = None
    provider_api_keys: dict[str, str | None] | None = None
    provider_settings: dict[str, dict] | None = None


class ApiKeysTestRequest(BaseModel):
    provider: str


class ApiKeysTestResponse(BaseModel):
    valid: bool
    error: str | None = None


# ── Backward-compat aliases (used by users.py) ───────────────────────────────


class UserUpdateLLMKeys(BaseModel):
    openai_api_key: str | None = None
    anthropic_api_key: str | None = None
    preferred_llm_provider: str | None = Field(default=None, min_length=1, max_length=64)


# ── Response schemas ─────────────────────────────────────────────────────────


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: str
    full_name: str
    is_active: bool
    is_verified: bool
    preferred_llm_provider: str
    # Never expose hashed_password or raw API keys
    has_openai_key: bool = False
    has_anthropic_key: bool = False
    has_ollama_url: bool = False
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_orm_with_flags(cls, user) -> "UserRead":
        return cls(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
            is_active=user.is_active,
            is_verified=user.is_verified,
            preferred_llm_provider=user.preferred_llm_provider,
            has_openai_key=bool(user.openai_api_key),
            has_anthropic_key=bool(user.anthropic_api_key),
            has_ollama_url=bool(user.ollama_base_url),
            created_at=user.created_at,
            updated_at=user.updated_at,
        )


class AuthResponse(BaseModel):
    """Returned by /login endpoint."""

    user: UserRead
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RegisterResponse(UserRead):
    """Returned by /register endpoint — flattens user fields with tokens."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshResponse(BaseModel):
    """Returned by /refresh."""

    access_token: str
    refresh_token: str | None = None
    token_type: str = "bearer"


class MessageResponse(BaseModel):
    message: str


# ── Legacy schemas (backward compat with existing tests) ─────────────────────


class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class TokenRefresh(BaseModel):
    refresh_token: str


class PasswordChange(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=128)

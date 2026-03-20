"""Users router — profile management and BYOK key configuration."""

from fastapi import APIRouter

from app.core.llm_provider import ProviderRegistry
from app.core.security import decrypt_field, encrypt_field
from app.dependencies import CurrentUser, DBSession
from app.schemas.user import UserRead, UserUpdate, UserUpdateLLMKeys

router = APIRouter()
provider_registry = ProviderRegistry()


@router.get("/me", response_model=UserRead, summary="Get current user profile")
async def get_me(current_user: CurrentUser) -> UserRead:
    return UserRead.from_orm_with_flags(current_user)


@router.patch("/me", response_model=UserRead, summary="Update current user profile")
async def update_me(
    payload: UserUpdate,
    current_user: CurrentUser,
    db: DBSession,
) -> UserRead:
    if payload.full_name is not None:
        current_user.full_name = payload.full_name
    if payload.preferred_llm_provider is not None:
        selected = payload.preferred_llm_provider.lower()
        if selected not in provider_registry.providers:
            selected = provider_registry.default_provider
        current_user.preferred_llm_provider = selected
    return UserRead.from_orm_with_flags(current_user)


@router.put(
    "/me/llm-keys",
    response_model=UserRead,
    summary="Save encrypted BYOK LLM API keys",
)
async def update_llm_keys(
    payload: UserUpdateLLMKeys,
    current_user: CurrentUser,
    db: DBSession,
) -> UserRead:
    """
    Store per-user LLM API keys encrypted with Fernet (key derived from JWT_SECRET).
    Pass an empty string to clear a key.
    """
    if payload.openai_api_key is not None:
        current_user.openai_api_key = (
            encrypt_field(payload.openai_api_key) if payload.openai_api_key else None
        )
    if payload.anthropic_api_key is not None:
        current_user.anthropic_api_key = (
            encrypt_field(payload.anthropic_api_key) if payload.anthropic_api_key else None
        )
    if payload.preferred_llm_provider is not None:
        selected = payload.preferred_llm_provider.lower()
        if selected not in provider_registry.providers:
            selected = provider_registry.default_provider
        current_user.preferred_llm_provider = selected

    return UserRead.from_orm_with_flags(current_user)


@router.get(
    "/me/llm-keys/openai",
    summary="Retrieve (decrypted) OpenAI key for in-browser use",
    response_model=dict,
)
async def get_openai_key(current_user: CurrentUser) -> dict:
    """
    Returns the decrypted key so the browser can use it directly with OpenAI.
    Only the owner can retrieve their own key.
    """
    if not current_user.openai_api_key:
        return {"key": None}
    return {"key": decrypt_field(current_user.openai_api_key)}


@router.get(
    "/me/llm-keys/anthropic",
    summary="Retrieve (decrypted) Anthropic key for in-browser use",
    response_model=dict,
)
async def get_anthropic_key(current_user: CurrentUser) -> dict:
    if not current_user.anthropic_api_key:
        return {"key": None}
    return {"key": decrypt_field(current_user.anthropic_api_key)}

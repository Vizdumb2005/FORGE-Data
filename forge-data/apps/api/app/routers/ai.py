"""AI router — BYOK LLM chat with SSE streaming."""

import json
from collections.abc import AsyncIterator
from typing import Literal

import httpx
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.config import settings
from app.core.security import decrypt_field
from app.dependencies import CurrentUser, DBSession

router = APIRouter()


class ChatMessage(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str


class LLMConfig(BaseModel):
    provider: Literal["openai", "anthropic", "google", "ollama", "azure"] = "openai"
    model: str = "gpt-4o"
    api_key: str | None = None  # BYOK: per-request key takes precedence
    base_url: str | None = None  # for Ollama or Azure custom endpoint
    temperature: float = 0.7
    max_tokens: int = 4096


class ChatRequest(BaseModel):
    messages: list[ChatMessage]
    config: LLMConfig = LLMConfig()
    # Optional data context injected into system prompt
    data_context: str | None = None
    stream: bool = True


class ProviderInfo(BaseModel):
    id: str
    name: str
    models: list[str]
    requires_key: bool


@router.post("/chat", summary="Streaming LLM chat (BYOK)")
async def chat(
    payload: ChatRequest,
    current_user: CurrentUser,
    db: DBSession,
) -> StreamingResponse:
    """
    Forward a chat request to the configured LLM provider.

    Key resolution order:
      1. ``config.api_key`` in the request body (BYOK per-request)
      2. User's stored (encrypted) key in the database
      3. Platform-level environment variable
    """
    api_key = _resolve_api_key(payload.config, current_user)

    if payload.data_context:
        system_msg = ChatMessage(
            role="system",
            content=(
                "You are a helpful data analyst assistant. "
                "Here is context about the current dataset:\n\n"
                f"{payload.data_context}"
            ),
        )
        messages = [system_msg, *payload.messages]
    else:
        messages = payload.messages

    return StreamingResponse(
        _stream(payload.config, messages, api_key),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # disable nginx buffering
        },
    )


@router.get("/providers", response_model=list[ProviderInfo], summary="List LLM providers")
async def list_providers() -> list[ProviderInfo]:
    return [
        ProviderInfo(
            id="openai",
            name="OpenAI",
            models=["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "o1-preview", "o1-mini"],
            requires_key=True,
        ),
        ProviderInfo(
            id="anthropic",
            name="Anthropic",
            models=[
                "claude-opus-4-5-20251101",
                "claude-sonnet-4-5-20251101",
                "claude-haiku-3-5-20251022",
            ],
            requires_key=True,
        ),
        ProviderInfo(
            id="google",
            name="Google AI",
            models=["gemini-1.5-pro", "gemini-1.5-flash", "gemini-2.0-flash"],
            requires_key=True,
        ),
        ProviderInfo(
            id="ollama",
            name="Ollama (local)",
            models=[],  # fetched dynamically
            requires_key=False,
        ),
        ProviderInfo(
            id="azure",
            name="Azure OpenAI",
            models=[],  # deployment-specific
            requires_key=True,
        ),
    ]


@router.get("/ollama/models", summary="List locally available Ollama models")
async def list_ollama_models() -> dict:
    """Proxy request to local Ollama instance to list available models."""
    base_url = settings.ollama_base_url.rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(f"{base_url}/api/tags")
            r.raise_for_status()
            return r.json()
    except Exception as exc:
        return {"models": [], "error": str(exc)}


# ── Streaming helpers ──────────────────────────────────────────────────────────


def _resolve_api_key(config: LLMConfig, user) -> str | None:
    """Return the most specific API key available for the given provider."""
    # 1. Per-request BYOK key
    if config.api_key:
        return config.api_key

    # 2. User's stored key
    if config.provider == "openai" and user.openai_api_key:
        return decrypt_field(user.openai_api_key)
    if config.provider == "anthropic" and user.anthropic_api_key:
        return decrypt_field(user.anthropic_api_key)

    # 3. Platform environment variable
    if config.provider == "openai":
        return settings.openai_api_key or None
    if config.provider == "anthropic":
        return settings.anthropic_api_key or None
    if config.provider == "google":
        return settings.google_ai_api_key or None
    if config.provider == "azure":
        return settings.azure_openai_api_key or None

    return None


async def _stream(
    config: LLMConfig,
    messages: list[ChatMessage],
    api_key: str | None,
) -> AsyncIterator[str]:
    """Route to the correct provider stream and yield SSE events."""
    try:
        if config.provider == "openai":
            async for chunk in _stream_openai(config, messages, api_key):
                yield chunk
        elif config.provider == "anthropic":
            async for chunk in _stream_anthropic(config, messages, api_key):
                yield chunk
        elif config.provider == "ollama":
            async for chunk in _stream_ollama(config, messages):
                yield chunk
        else:
            yield _sse_event({"error": f"Provider '{config.provider}' not yet implemented"})
            yield _sse_event("[DONE]")
    except Exception as exc:
        yield _sse_event({"error": str(exc)})
        yield _sse_event("[DONE]")


def _sse_event(data: str | dict) -> str:
    payload = json.dumps(data) if isinstance(data, dict) else data
    return f"data: {payload}\n\n"


async def _stream_openai(
    config: LLMConfig, messages: list[ChatMessage], api_key: str | None
) -> AsyncIterator[str]:
    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=api_key or "no-key")
    async with client.chat.completions.stream(
        model=config.model,
        messages=[{"role": m.role, "content": m.content} for m in messages],
        temperature=config.temperature,
        max_tokens=config.max_tokens,
    ) as stream:
        async for event in stream:
            delta = event.choices[0].delta.content if event.choices else None
            if delta:
                yield _sse_event({"content": delta})
    yield _sse_event("[DONE]")


async def _stream_anthropic(
    config: LLMConfig, messages: list[ChatMessage], api_key: str | None
) -> AsyncIterator[str]:
    import anthropic

    system_msgs = [m for m in messages if m.role == "system"]
    user_msgs = [m for m in messages if m.role != "system"]
    system = system_msgs[0].content if system_msgs else None

    client = anthropic.AsyncAnthropic(api_key=api_key or "no-key")
    async with client.messages.stream(
        model=config.model,
        max_tokens=config.max_tokens,
        system=system,
        messages=[{"role": m.role, "content": m.content} for m in user_msgs],
    ) as stream:
        async for text in stream.text_stream:
            yield _sse_event({"content": text})
    yield _sse_event("[DONE]")


async def _stream_ollama(config: LLMConfig, messages: list[ChatMessage]) -> AsyncIterator[str]:
    base_url = (config.base_url or settings.ollama_base_url).rstrip("/")
    payload = {
        "model": config.model,
        "messages": [{"role": m.role, "content": m.content} for m in messages],
        "stream": True,
    }
    async with (
        httpx.AsyncClient(timeout=300) as client,
        client.stream("POST", f"{base_url}/api/chat", json=payload) as response,
    ):
        async for line in response.aiter_lines():
            if line:
                try:
                    data = json.loads(line)
                    content = data.get("message", {}).get("content", "")
                    if content:
                        yield _sse_event({"content": content})
                    if data.get("done"):
                        break
                except json.JSONDecodeError:
                    continue
    yield _sse_event("[DONE]")

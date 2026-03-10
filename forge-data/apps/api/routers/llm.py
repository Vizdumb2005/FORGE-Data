from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Literal, AsyncIterator
import json

router = APIRouter()


class LLMProvider(BaseModel):
    provider: Literal["openai", "anthropic", "google", "azure", "ollama"]
    model: str
    api_key: str | None = None  # BYOK — per-request key takes precedence over env var
    base_url: str | None = None  # For Ollama or Azure custom endpoints


class ChatMessage(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage]
    provider: LLMProvider
    context: dict | None = None  # Optional data context (schema, sample rows, etc.)
    stream: bool = True


class ChatResponse(BaseModel):
    content: str
    provider: str
    model: str
    usage: dict | None = None


@router.post("/chat")
async def chat(payload: ChatRequest):
    """
    Send messages to the configured LLM provider.
    Supports streaming (default) and non-streaming responses.
    Respects BYOK: if api_key is provided in the request it is used;
    otherwise falls back to the platform environment variable.
    """
    if payload.stream:
        return StreamingResponse(
            _stream_chat(payload),
            media_type="text/event-stream",
        )

    raise HTTPException(status_code=501, detail="Non-streaming chat not implemented yet")


async def _stream_chat(payload: ChatRequest) -> AsyncIterator[str]:
    """Yield Server-Sent Events from the LLM provider."""
    # TODO: dispatch to openai / anthropic / ollama based on payload.provider.provider
    # Example SSE format:
    yield f"data: {json.dumps({'content': 'Not implemented yet'})}\n\n"
    yield "data: [DONE]\n\n"


@router.get("/providers", response_model=list[dict])
async def list_providers() -> list[dict]:
    """Return list of supported providers and their available models."""
    return [
        {
            "id": "openai",
            "name": "OpenAI",
            "models": ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "o1-preview"],
            "requires_key": True,
        },
        {
            "id": "anthropic",
            "name": "Anthropic",
            "models": ["claude-opus-4-5-20251101", "claude-sonnet-4-5-20251101", "claude-haiku-3-5-20251022"],
            "requires_key": True,
        },
        {
            "id": "google",
            "name": "Google AI",
            "models": ["gemini-1.5-pro", "gemini-1.5-flash"],
            "requires_key": True,
        },
        {
            "id": "ollama",
            "name": "Ollama (local)",
            "models": [],  # dynamically fetched from Ollama API
            "requires_key": False,
        },
    ]

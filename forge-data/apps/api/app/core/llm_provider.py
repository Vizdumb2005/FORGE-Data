"""BYOK LLM abstraction layer for OpenAI, Anthropic, and Ollama."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

import httpx

from app.config import settings
from app.core.exceptions import ServiceUnavailableException, ValidationError
from app.core.security import decrypt_field
from app.models.user import User

SupportedProvider = str

DEFAULT_MODELS: dict[str, str] = {
    "openai": "gpt-4o-mini",
    "anthropic": "claude-3-5-sonnet-latest",
    "ollama": "llama3.1",
}

SUPPORTED_MODELS: dict[str, set[str]] = {
    "openai": {"gpt-4o", "gpt-4o-mini", "gpt-4-turbo"},
    "anthropic": {"claude-3-5-sonnet-latest", "claude-3-haiku"},
    "ollama": {"llama3.1", "codellama", "mistral"},
}


@dataclass(slots=True)
class LLMClient:
    provider: str
    client: Any | None
    api_key: str | None
    base_url: str | None = None


class LLMProvider:
    """
    BYOK LLM abstraction. Supports OpenAI, Anthropic, Ollama.
    User's own API keys take priority over platform defaults.
    Falls back to platform env vars if user has no key configured.
    """

    async def get_client(self, user: User, provider: SupportedProvider | None = None) -> LLMClient:
        resolved_provider = self._resolve_provider(user, provider)
        resolved_provider = self._fallback_provider_with_key(user, resolved_provider)

        if resolved_provider == "openai":
            key = self._resolve_api_key(user, "openai")
            if not key:
                raise ValidationError("No OpenAI API key configured for this user or platform")
            from openai import AsyncOpenAI

            return LLMClient(
                provider="openai",
                client=AsyncOpenAI(api_key=key),
                api_key=key,
            )

        if resolved_provider == "anthropic":
            key = self._resolve_api_key(user, "anthropic")
            if not key:
                raise ValidationError("No Anthropic API key configured for this user or platform")
            import anthropic

            return LLMClient(
                provider="anthropic",
                client=anthropic.AsyncAnthropic(api_key=key),
                api_key=key,
            )

        if resolved_provider == "ollama":
            base_url = (user.ollama_base_url or settings.ollama_base_url).rstrip("/")
            return LLMClient(provider="ollama", client=None, api_key=None, base_url=base_url)

        raise ValidationError(f"Unsupported LLM provider: {resolved_provider}")

    async def complete(
        self,
        user: User,
        messages: list[dict[str, str]],
        system: str,
        max_tokens: int = 4096,
        stream: bool = False,
        provider: SupportedProvider | None = None,
        model: str | None = None,
    ) -> AsyncIterator[str] | str:
        client = await self.get_client(user, provider)
        selected_model = model or DEFAULT_MODELS[client.provider]
        self._validate_model(client.provider, selected_model)

        if client.provider == "openai":
            return self.complete_openai(
                client,
                messages,
                system,
                selected_model,
                stream,
                max_tokens,
            )
        if client.provider == "anthropic":
            return self.complete_anthropic(
                client,
                messages,
                system,
                selected_model,
                stream,
                max_tokens,
            )
        if client.provider == "ollama":
            return self.complete_ollama(
                client,
                messages,
                system,
                selected_model,
                stream,
                max_tokens,
            )
        raise ValidationError(f"Unsupported LLM provider: {client.provider}")

    async def complete_openai(
        self,
        client: LLMClient,
        messages: list[dict[str, str]],
        system: str,
        model: str,
        stream: bool,
        max_tokens: int,
    ) -> AsyncIterator[str] | str:
        payload_messages = [{"role": "system", "content": system}, *messages]
        api = client.client

        if stream:

            async def _stream() -> AsyncIterator[str]:
                response = await api.chat.completions.create(
                    model=model,
                    messages=payload_messages,
                    max_tokens=max_tokens,
                    stream=True,
                )
                async for chunk in response:
                    delta = chunk.choices[0].delta.content if chunk.choices else None
                    if delta:
                        yield delta

            return _stream()

        response = await api.chat.completions.create(
            model=model,
            messages=payload_messages,
            max_tokens=max_tokens,
            stream=False,
        )
        return response.choices[0].message.content or ""

    async def complete_anthropic(
        self,
        client: LLMClient,
        messages: list[dict[str, str]],
        system: str,
        model: str,
        stream: bool,
        max_tokens: int,
    ) -> AsyncIterator[str] | str:
        api = client.client
        user_messages = [
            {"role": msg["role"], "content": msg["content"]}
            for msg in messages
            if msg["role"] != "system"
        ]

        if stream:

            async def _stream() -> AsyncIterator[str]:
                async with api.messages.stream(
                    model=model,
                    max_tokens=max_tokens,
                    system=system,
                    messages=user_messages,
                ) as message_stream:
                    async for text in message_stream.text_stream:
                        yield text

            return _stream()

        response = await api.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=user_messages,
        )
        chunks = [part.text for part in response.content if getattr(part, "type", "") == "text"]
        return "".join(chunks)

    async def complete_ollama(
        self,
        client: LLMClient,
        messages: list[dict[str, str]],
        system: str,
        model: str,
        stream: bool,
        max_tokens: int,
    ) -> AsyncIterator[str] | str:
        base_url = (client.base_url or settings.ollama_base_url).rstrip("/")
        payload = {
            "model": model,
            "messages": [{"role": "system", "content": system}, *messages],
            "stream": stream,
            "options": {"num_predict": max_tokens},
        }

        if stream:

            async def _stream() -> AsyncIterator[str]:
                async with (
                    httpx.AsyncClient(timeout=300) as http_client,
                    http_client.stream("POST", f"{base_url}/api/chat", json=payload) as response,
                ):
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if not line:
                            continue
                        parsed = json.loads(line)
                        content = parsed.get("message", {}).get("content", "")
                        if content:
                            yield content
                        if parsed.get("done"):
                            break

            return _stream()

        try:
            async with httpx.AsyncClient(timeout=120) as http_client:
                response = await http_client.post(f"{base_url}/api/chat", json=payload)
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise ServiceUnavailableException("Ollama") from exc

        return response.json().get("message", {}).get("content", "")

    def _resolve_provider(self, user: User, provider: SupportedProvider | None) -> str:
        selected = (provider or user.preferred_llm_provider or "openai").lower()
        if selected not in {"openai", "anthropic", "ollama"}:
            raise ValidationError(f"Unsupported LLM provider: {selected}")
        return selected

    def _resolve_api_key(self, user: User, provider: str) -> str | None:
        if provider == "openai":
            if user.openai_api_key:
                return decrypt_field(user.openai_api_key)
            return settings.openai_api_key or None
        if provider == "anthropic":
            if user.anthropic_api_key:
                return decrypt_field(user.anthropic_api_key)
            return settings.anthropic_api_key or None
        return None

    def _validate_model(self, provider: str, model: str) -> None:
        allowed = SUPPORTED_MODELS.get(provider, set())
        if model not in allowed:
            raise ValidationError(
                f"Unsupported model '{model}' for provider '{provider}'. "
                f"Supported: {', '.join(sorted(allowed))}"
            )

    def _provider_has_credentials(self, user: User, provider: str) -> bool:
        if provider == "openai":
            return bool(user.openai_api_key or settings.openai_api_key)
        if provider == "anthropic":
            return bool(user.anthropic_api_key or settings.anthropic_api_key)
        return provider == "ollama"

    def _fallback_provider_with_key(self, user: User, provider: str) -> str:
        if self._provider_has_credentials(user, provider):
            return provider
        for candidate in ("openai", "anthropic", "ollama"):
            if self._provider_has_credentials(user, candidate):
                return candidate
        return provider

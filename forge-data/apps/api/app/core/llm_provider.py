"""Universal BYOK LLM abstraction layer with local-first provider routing."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from app.core.exceptions import ServiceUnavailableException, ValidationError
from app.core.security import decrypt_field
from app.models.user import User

_CONFIG_PATH = Path(__file__).with_name("llm_providers.json")


@dataclass(slots=True)
class ProviderSpec:
    provider_id: str
    display_name: str
    protocol: str
    default_model: str
    models: list[str]
    api_key_env: str | None = None
    base_url_env: str | None = None
    base_url: str | None = None
    requires_api_key: bool = True
    local: bool = False
    priority: int = 999
    required_settings: list[str] | None = None
    runtime_options: dict[str, Any] | None = None


@dataclass(slots=True)
class LLMClient:
    provider: str
    protocol: str
    model: str
    client: Any | None
    api_key: str | None
    base_url: str | None
    runtime_options: dict[str, Any]


class ProviderRegistry:
    def __init__(self, config_path: Path | None = None) -> None:
        self._config_path = config_path or _CONFIG_PATH
        self._config = self._load_config(self._config_path)
        self.default_provider = self._config.get("default_provider", "ollama")
        self.providers: dict[str, ProviderSpec] = {
            provider_id: self._to_spec(provider_id, payload)
            for provider_id, payload in self._config.get("providers", {}).items()
        }
        if not self.providers:
            raise ValidationError("No LLM providers are configured. Check llm_providers.json.")

    @property
    def raw_config(self) -> dict[str, Any]:
        return dict(self._config)

    def _load_config(self, path: Path) -> dict[str, Any]:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise ValidationError(f"LLM provider config file not found: {path}") from exc
        except json.JSONDecodeError as exc:
            raise ValidationError(f"Invalid JSON in LLM provider config: {exc}") from exc

    def _to_spec(self, provider_id: str, payload: dict[str, Any]) -> ProviderSpec:
        models = payload.get("models", [])
        if not isinstance(models, list) or not models:
            raise ValidationError(f"Provider '{provider_id}' has no models configured")
        return ProviderSpec(
            provider_id=provider_id,
            display_name=payload.get("display_name", provider_id.title()),
            protocol=payload.get("protocol", provider_id),
            default_model=payload.get("default_model", models[0]),
            models=[str(model) for model in models],
            api_key_env=payload.get("api_key_env"),
            base_url_env=payload.get("base_url_env"),
            base_url=payload.get("base_url"),
            requires_api_key=bool(payload.get("requires_api_key", True)),
            local=bool(payload.get("local", False)),
            priority=int(payload.get("priority", 999)),
            required_settings=list(payload.get("required_settings", [])),
            runtime_options=dict(payload.get("runtime_options", {})),
        )

    def get(self, provider: str) -> ProviderSpec:
        spec = self.providers.get(provider)
        if spec is None:
            supported = ", ".join(sorted(self.providers.keys()))
            raise ValidationError(
                f"Provider '{provider}' is not available. Supported providers: {supported}"
            )
        return spec

    def local_providers(self) -> list[ProviderSpec]:
        return sorted(
            [spec for spec in self.providers.values() if spec.local],
            key=lambda item: item.priority,
        )

    def cloud_providers(self) -> list[ProviderSpec]:
        return sorted(
            [spec for spec in self.providers.values() if not spec.local],
            key=lambda item: item.priority,
        )

    def list_for_user(self, user: User) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for spec in sorted(self.providers.values(), key=lambda item: item.priority):
            items.append(
                {
                    "id": spec.provider_id,
                    "name": spec.display_name,
                    "models": spec.models,
                    "default_model": spec.default_model,
                    "configured": self.is_configured(user, spec),
                    "requires_api_key": spec.requires_api_key,
                    "local": spec.local,
                    "priority": spec.priority,
                    "required_settings": spec.required_settings or [],
                }
            )
        return items

    def is_configured(self, user: User, spec: ProviderSpec) -> bool:
        api_key = self.resolve_api_key(user, spec)
        settings = self.resolve_provider_settings(user, spec)
        base_url = self.resolve_base_url(user, spec, settings)

        if spec.requires_api_key and not api_key:
            return False
        if spec.local and not base_url and "base_url" in (spec.required_settings or []):
            return False
        for required in spec.required_settings or []:
            if required == "base_url":
                if not base_url:
                    return False
                continue
            if not settings.get(required):
                return False
        return True

    def resolve_provider_settings(self, user: User, spec: ProviderSpec) -> dict[str, Any]:
        provider_settings = user.llm_provider_config or {}
        if not isinstance(provider_settings, dict):
            return {}
        data = provider_settings.get(spec.provider_id, {})
        if isinstance(data, dict):
            return dict(data)
        return {}

    def resolve_api_key(self, user: User, spec: ProviderSpec) -> str | None:
        provider_keys = user.llm_api_keys or {}
        if isinstance(provider_keys, dict):
            encrypted_user_key = provider_keys.get(spec.provider_id)
            if encrypted_user_key:
                return decrypt_field(encrypted_user_key)

        legacy_map: dict[str, str | None] = {
            "openai": user.openai_api_key,
            "anthropic": user.anthropic_api_key,
        }
        legacy_key = legacy_map.get(spec.provider_id)
        if legacy_key:
            return decrypt_field(legacy_key)

        if spec.api_key_env:
            import os

            return os.getenv(spec.api_key_env) or None
        return None

    def resolve_base_url(self, user: User, spec: ProviderSpec, settings: dict[str, Any] | None = None) -> str | None:
        resolved_settings = settings or self.resolve_provider_settings(user, spec)
        if resolved_settings.get("base_url"):
            return str(resolved_settings["base_url"])

        if spec.provider_id == "ollama" and user.ollama_base_url:
            return user.ollama_base_url

        if spec.base_url_env:
            import os

            env_value = os.getenv(spec.base_url_env)
            if env_value:
                return env_value
        return spec.base_url


class LLMProvider:
    """
    BYOK LLM abstraction based on JSON provider config.
    Local providers are prioritized by default; cloud fallback only occurs when no local provider is usable.
    """

    def __init__(self) -> None:
        self.registry = ProviderRegistry()
        self._default_global_settings = {"timeout": 30, "retry_attempts": 3}

    async def get_client(self, user: User, provider: str | None = None, model: str | None = None) -> LLMClient:
        spec = self._select_provider(user, provider)
        settings = self.registry.resolve_provider_settings(user, spec)
        selected_model = model or str(settings.get("default_model") or spec.default_model)
        self._validate_model(spec, selected_model)

        api_key = self.registry.resolve_api_key(user, spec)
        base_url = self.registry.resolve_base_url(user, spec, settings)
        runtime_options = dict(spec.runtime_options or {})
        runtime_options.update(settings.get("runtime_options", {}))

        if spec.requires_api_key and not api_key:
            raise ValidationError(self._missing_key_message(spec))
        self._validate_required_settings(spec, settings, base_url)

        if spec.protocol in {"openai", "openai_compatible"}:
            from openai import AsyncOpenAI

            client = AsyncOpenAI(
                api_key=api_key or "local-no-key",
                base_url=base_url if spec.protocol == "openai_compatible" else None,
            )
            return LLMClient(
                provider=spec.provider_id,
                protocol=spec.protocol,
                model=selected_model,
                client=client,
                api_key=api_key,
                base_url=base_url,
                runtime_options=runtime_options,
            )

        if spec.protocol == "anthropic":
            import anthropic

            client = anthropic.AsyncAnthropic(api_key=api_key)
            return LLMClient(
                provider=spec.provider_id,
                protocol=spec.protocol,
                model=selected_model,
                client=client,
                api_key=api_key,
                base_url=base_url,
                runtime_options=runtime_options,
            )

        if spec.protocol == "ollama":
            resolved_base_url = (base_url or "http://localhost:11434").rstrip("/")
            return LLMClient(
                provider=spec.provider_id,
                protocol=spec.protocol,
                model=selected_model,
                client=None,
                api_key=None,
                base_url=resolved_base_url,
                runtime_options=runtime_options,
            )

        raise ValidationError(
            f"Provider '{spec.provider_id}' uses unsupported protocol '{spec.protocol}'. "
            "Update llm_providers.json with a supported protocol."
        )

    async def complete(
        self,
        user: User,
        messages: list[dict[str, str]],
        system: str,
        max_tokens: int = 4096,
        stream: bool = False,
        provider: str | None = None,
        model: str | None = None,
    ) -> AsyncIterator[str] | str:
        client = await self.get_client(user=user, provider=provider, model=model)

        if client.protocol in {"openai", "openai_compatible"}:
            return await self.complete_openai(
                client=client,
                messages=messages,
                system=system,
                stream=stream,
                max_tokens=max_tokens,
            )
        if client.protocol == "anthropic":
            return await self.complete_anthropic(
                client=client,
                messages=messages,
                system=system,
                stream=stream,
                max_tokens=max_tokens,
            )
        if client.protocol == "ollama":
            return await self.complete_ollama(
                client=client,
                messages=messages,
                system=system,
                stream=stream,
                max_tokens=max_tokens,
            )
        raise ValidationError(f"Unsupported provider protocol: {client.protocol}")

    async def complete_openai(
        self,
        client: LLMClient,
        messages: list[dict[str, str]],
        system: str,
        stream: bool,
        max_tokens: int,
    ) -> AsyncIterator[str] | str:
        payload_messages = [{"role": "system", "content": system}, *messages]
        api = client.client

        if stream:

            async def _stream() -> AsyncIterator[str]:
                response = await api.chat.completions.create(
                    model=client.model,
                    messages=payload_messages,
                    max_tokens=max_tokens,
                    stream=True,
                    **_openai_extra_options(client),
                )
                async for chunk in response:
                    delta = chunk.choices[0].delta.content if chunk.choices else None
                    if delta:
                        yield delta

            return _stream()

        response = await api.chat.completions.create(
            model=client.model,
            messages=payload_messages,
            max_tokens=max_tokens,
            stream=False,
            **_openai_extra_options(client),
        )
        return response.choices[0].message.content or ""

    async def complete_anthropic(
        self,
        client: LLMClient,
        messages: list[dict[str, str]],
        system: str,
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
                    model=client.model,
                    max_tokens=max_tokens,
                    system=system,
                    messages=user_messages,
                    temperature=float(client.runtime_options.get("temperature", 0.2)),
                ) as message_stream:
                    async for text in message_stream.text_stream:
                        yield text

            return _stream()

        response = await api.messages.create(
            model=client.model,
            max_tokens=max_tokens,
            system=system,
            messages=user_messages,
            temperature=float(client.runtime_options.get("temperature", 0.2)),
        )
        chunks = [part.text for part in response.content if getattr(part, "type", "") == "text"]
        return "".join(chunks)

    async def complete_ollama(
        self,
        client: LLMClient,
        messages: list[dict[str, str]],
        system: str,
        stream: bool,
        max_tokens: int,
    ) -> AsyncIterator[str] | str:
        base_url = (client.base_url or "http://localhost:11434").rstrip("/")
        options = {"num_predict": max_tokens}
        options.update(client.runtime_options)
        payload = {
            "model": client.model,
            "messages": [{"role": "system", "content": system}, *messages],
            "stream": stream,
            "options": options,
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

    def _select_provider(self, user: User, explicit_provider: str | None) -> ProviderSpec:
        global_settings = self._resolve_global_settings(user)
        fallback_order = self._resolve_fallback_order(global_settings)

        if explicit_provider:
            selected = explicit_provider.lower()
            spec = self.registry.get(selected)
            if not self.registry.is_configured(user, spec):
                raise ValidationError(self._provider_misconfigured_message(spec))
            return spec

        preferred = str(user.preferred_llm_provider or "").lower()
        if preferred:
            try:
                preferred_spec = self.registry.get(preferred)
                if preferred_spec.local and self.registry.is_configured(user, preferred_spec):
                    return preferred_spec
            except ValidationError:
                pass

        for provider_id in fallback_order:
            spec = self.registry.providers.get(provider_id)
            if spec and spec.local and self.registry.is_configured(user, spec):
                return spec

        for local_spec in self.registry.local_providers():
            if self.registry.is_configured(user, local_spec):
                return local_spec

        for provider_id in fallback_order:
            spec = self.registry.providers.get(provider_id)
            if spec and not spec.local and self.registry.is_configured(user, spec):
                return spec

        for cloud_spec in self.registry.cloud_providers():
            if self.registry.is_configured(user, cloud_spec):
                return cloud_spec

        local_ids = ", ".join(spec.provider_id for spec in self.registry.local_providers())
        cloud_ids = ", ".join(spec.provider_id for spec in self.registry.cloud_providers())
        raise ValidationError(
            "No usable AI provider is configured. "
            f"Checked local providers first ({local_ids}), then cloud providers ({cloud_ids}). "
            "Configure a local runtime (recommended) or add a cloud API key in Settings > AI API Keys."
        )

    def _resolve_global_settings(self, user: User) -> dict[str, Any]:
        config = user.llm_provider_config or {}
        if not isinstance(config, dict):
            return dict(self._default_global_settings)
        settings = config.get("__settings__", {})
        if not isinstance(settings, dict):
            settings = {}
        merged = dict(self._default_global_settings)
        merged.update(settings)
        return merged

    def _resolve_fallback_order(self, global_settings: dict[str, Any]) -> list[str]:
        configured = global_settings.get("fallback_order")
        if isinstance(configured, list):
            normalized = [str(item).lower() for item in configured if str(item).lower() in self.registry.providers]
            if normalized:
                return normalized
        local_ids = [spec.provider_id for spec in self.registry.local_providers()]
        cloud_ids = [spec.provider_id for spec in self.registry.cloud_providers()]
        return [*local_ids, *cloud_ids]

    def _validate_required_settings(self, spec: ProviderSpec, settings: dict[str, Any], base_url: str | None) -> None:
        missing: list[str] = []
        for required in spec.required_settings or []:
            if required == "base_url":
                if not base_url:
                    missing.append(required)
                continue
            if settings.get(required) in (None, "", []):
                missing.append(required)
        if missing:
            raise ValidationError(
                f"{spec.display_name} is misconfigured. Missing required setting(s): "
                f"{', '.join(missing)}. Update Settings > AI API Keys."
            )

    def _validate_model(self, spec: ProviderSpec, model: str) -> None:
        if model not in spec.models:
            raise ValidationError(
                f"Model '{model}' is not available for provider '{spec.display_name}'. "
                f"Choose one of: {', '.join(spec.models)}"
            )

    def _provider_misconfigured_message(self, spec: ProviderSpec) -> str:
        if spec.local:
            return (
                f"{spec.display_name} is selected but not fully configured. "
                "Please set local runtime options (model path/base URL/runtime settings) in Settings > AI API Keys."
            )
        return (
            f"{spec.display_name} is selected but no valid API key is configured. "
            "Add an API key in Settings > AI API Keys."
        )

    def _missing_key_message(self, spec: ProviderSpec) -> str:
        return (
            f"{spec.display_name} is not configured for your account. "
            "Add an API key in Settings > AI API Keys and try again."
        )


def _openai_extra_options(client: LLMClient) -> dict[str, Any]:
    options: dict[str, Any] = {}
    if "temperature" in client.runtime_options:
        options["temperature"] = float(client.runtime_options["temperature"])
    if "top_p" in client.runtime_options:
        options["top_p"] = float(client.runtime_options["top_p"])
    return options

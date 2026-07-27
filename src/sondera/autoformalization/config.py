"""TOML and local environment configuration for model-backed experiments."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ProviderSettings:
    """OpenAI-compatible endpoint settings."""

    name: str
    base_url: str
    wire_api: str = "responses"
    requires_openai_auth: bool = True
    api_key_env: str = "OPENAI_API_KEY"


@dataclass(frozen=True)
class ModelSettings:
    """Generator and reviewer model defaults."""

    provider: ProviderSettings
    model: str
    review_model: str
    judge_temperature: float = 0.3
    verifier_temperature: float = 0.1
    reasoning_effort: str = "high"
    store: bool = False
    max_output_tokens: int = 32768
    timeout_seconds: float = 600.0
    max_retries: int = 3
    retry_base_seconds: float = 10.0
    stream: bool = True


def load_model_settings(path: str | Path) -> ModelSettings:
    """Load the Codex-style provider subset used by this pipeline."""
    source = Path(path)
    with source.open("rb") as stream:
        payload = tomllib.load(stream)

    provider_name = str(payload.get("model_provider", "OpenAI"))
    providers = payload.get("model_providers", {})
    if not isinstance(providers, dict) or provider_name not in providers:
        raise ValueError(f"missing [model_providers.{provider_name}] in {source}")
    provider_payload = providers[provider_name]
    if not isinstance(provider_payload, dict):
        raise ValueError(f"invalid provider configuration for {provider_name}")

    provider = ProviderSettings(
        name=str(provider_payload.get("name", provider_name)),
        base_url=str(provider_payload["base_url"]).rstrip("/"),
        wire_api=str(provider_payload.get("wire_api", "responses")).lower(),
        requires_openai_auth=bool(provider_payload.get("requires_openai_auth", True)),
        api_key_env=str(provider_payload.get("api_key_env", "OPENAI_API_KEY")),
    )
    if provider.wire_api not in {"responses", "chat_completions"}:
        raise ValueError("wire_api must be 'responses' or 'chat_completions'")
    return ModelSettings(
        provider=provider,
        model=str(payload["model"]),
        review_model=str(payload.get("review_model", payload["model"])),
        judge_temperature=float(payload.get("judge_temperature", 0.3)),
        verifier_temperature=float(payload.get("verifier_temperature", 0.1)),
        reasoning_effort=str(payload.get("model_reasoning_effort", "high")),
        store=not bool(payload.get("disable_response_storage", True)),
        max_output_tokens=int(payload.get("max_output_tokens", 32768)),
        timeout_seconds=float(payload.get("timeout_seconds", 600.0)),
        max_retries=int(payload.get("max_retries", 3)),
        retry_base_seconds=float(payload.get("retry_base_seconds", 10.0)),
        stream=bool(payload.get("stream", True)),
    )


def load_env_file(path: str | Path, *, override: bool = False) -> None:
    """Load simple KEY=VALUE entries without adding a dotenv dependency."""
    source = Path(path)
    if not source.exists():
        return
    for line_number, raw_line in enumerate(
        source.read_text(encoding="utf-8").splitlines(), start=1
    ):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ValueError(f"invalid environment entry at {source}:{line_number}")
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if value[:1] == value[-1:] and value.startswith(("'", '"')):
            value = value[1:-1]
        if not key:
            raise ValueError(f"empty environment key at {source}:{line_number}")
        if override or key not in os.environ:
            os.environ[key] = value


def settings_as_safe_dict(settings: ModelSettings) -> dict[str, Any]:
    """Serialize settings without ever including credential values."""
    return {
        "provider": settings.provider.name,
        "base_url": settings.provider.base_url,
        "wire_api": settings.provider.wire_api,
        "api_key_env": settings.provider.api_key_env,
        "model": settings.model,
        "review_model": settings.review_model,
        "judge_temperature": settings.judge_temperature,
        "verifier_temperature": settings.verifier_temperature,
        "reasoning_effort": settings.reasoning_effort,
        "store": settings.store,
        "max_output_tokens": settings.max_output_tokens,
        "timeout_seconds": settings.timeout_seconds,
        "max_retries": settings.max_retries,
        "retry_base_seconds": settings.retry_base_seconds,
        "stream": settings.stream,
    }

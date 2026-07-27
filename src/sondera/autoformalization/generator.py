"""Pluggable policy-generator backends."""

from __future__ import annotations

import json
import os
import re
import time
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any, Protocol

from cedar import PolicySet

from .models import AutoformalizationInput, PolicyCandidate


class TextModel(Protocol):
    """Minimal interface shared by generator, Judge, and Verifier models."""

    def complete(self, prompt: str) -> str:
        """Return a text completion for ``prompt``."""
        ...


class CallableTextModel:
    """Adapt a Python callable to the TextModel protocol."""

    def __init__(self, completion: Callable[[str], str]):
        self._completion = completion

    def complete(self, prompt: str) -> str:
        return self._completion(prompt)


class LiteLLMTextModel:
    """Optional LiteLLM-backed model used for paper-style experiments."""

    def __init__(
        self,
        model: str,
        *,
        temperature: float | None = None,
        provider: str = "openai",
        base_url: str | None = None,
        wire_api: str = "responses",
        api_key_env: str = "OPENAI_API_KEY",
        requires_auth: bool = True,
        reasoning_effort: str | None = None,
        store: bool = False,
        max_output_tokens: int = 32768,
        timeout_seconds: float = 600.0,
        max_retries: int = 3,
        retry_base_seconds: float = 10.0,
        stream: bool = False,
    ):
        self.model = model
        self.temperature = temperature
        self.provider = provider.lower()
        self.base_url = base_url
        self.wire_api = wire_api
        self.api_key_env = api_key_env
        self.requires_auth = requires_auth
        self.reasoning_effort = reasoning_effort
        self.store = store
        self.max_output_tokens = max_output_tokens
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.retry_base_seconds = retry_base_seconds
        self.stream = stream

    @staticmethod
    def _response_text(response: object) -> str:
        output_text = getattr(response, "output_text", None)
        if isinstance(output_text, str) and output_text:
            return output_text

        model_dump = getattr(response, "model_dump", None)
        payload = model_dump() if callable(model_dump) else response
        if isinstance(payload, dict):
            for output in payload.get("output", []):
                if not isinstance(output, dict):
                    continue
                for content in output.get("content", []):
                    if not isinstance(content, dict):
                        continue
                    text = content.get("text")
                    if isinstance(text, str) and text:
                        return text
        raise RuntimeError("Responses API returned no output text")

    @classmethod
    def _stream_response_text(cls, response: object) -> str:
        deltas: list[str] = []
        completed: str | None = None
        for event in response:  # type: ignore[union-attr]
            event_type = getattr(event, "type", None)
            if event_type == "response.output_text.delta":
                delta = getattr(event, "delta", None)
                if isinstance(delta, str):
                    deltas.append(delta)
            elif event_type == "response.completed":
                final_response = getattr(event, "response", None)
                if final_response is not None:
                    completed = cls._response_text(final_response)
        text = completed or "".join(deltas)
        if not text:
            raise RuntimeError("streaming Responses API returned no output text")
        return text

    def complete(self, prompt: str) -> str:
        try:
            import litellm
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise RuntimeError(
                "LiteLLM is not installed; install sondera-harness[ai]"
            ) from exc

        api_key = os.environ.get(self.api_key_env)
        if self.requires_auth and not api_key:
            raise RuntimeError(
                f"missing API credential in environment variable {self.api_key_env}"
            )
        common: dict[str, object] = {
            "model": self.model,
            "custom_llm_provider": self.provider,
            "store": self.store,
            "timeout": self.timeout_seconds,
        }
        if self.base_url:
            common["api_base"] = self.base_url
        if api_key:
            common["api_key"] = api_key
        if self.reasoning_effort:
            common["reasoning"] = {"effort": self.reasoning_effort}
        if self.temperature is not None:
            common["temperature"] = self.temperature

        for attempt in range(self.max_retries + 1):
            try:
                if self.wire_api == "responses":
                    response = litellm.responses(
                        input=prompt,
                        max_output_tokens=self.max_output_tokens,
                        stream=self.stream,
                        **common,
                    )
                    return (
                        self._stream_response_text(response)
                        if self.stream
                        else self._response_text(response)
                    )

                response = litellm.completion(
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=self.max_output_tokens,
                    **common,
                )
                content = response.choices[0].message.content
                if not isinstance(content, str):
                    raise RuntimeError("model returned an empty or non-text completion")
                return content
            except Exception as exc:
                status_code = getattr(exc, "status_code", None)
                error_name = exc.__class__.__name__
                error_text = str(exc).lower()
                is_transient = (
                    status_code in {408, 409, 429, 500, 502, 503, 504}
                    or error_name
                    in {
                        "RateLimitError",
                        "BadGatewayError",
                        "ServiceUnavailableError",
                        "Timeout",
                        "TimeoutError",
                    }
                    or "rate limit" in error_text
                    or "temporarily unavailable" in error_text
                    or "timed out" in error_text
                    or "no output text" in error_text
                )
                if not is_transient or attempt >= self.max_retries:
                    raise
                time.sleep(self.retry_base_seconds * (2**attempt))

        raise RuntimeError("unreachable model retry state")


class PolicyGenerator(Protocol):
    """Backend interface consumed by the workflow orchestrator."""

    def generate(
        self,
        grounded: AutoformalizationInput,
        prompt: str,
        *,
        round_number: int,
    ) -> PolicyCandidate:
        """Generate one candidate policy set."""
        ...


def _json_payload(text: str) -> dict[str, Any]:
    stripped = text.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", stripped, re.DOTALL)
    if fenced:
        stripped = fenced.group(1)
    value = json.loads(stripped)
    if not isinstance(value, dict):
        raise ValueError("generator response must be a JSON object")
    return value


def _complete_json_payload(
    model: TextModel,
    prompt: str,
    *,
    max_parse_retries: int = 1,
) -> dict[str, Any]:
    """Complete and retry once when a structured response is malformed JSON."""
    current_prompt = prompt
    for attempt in range(max_parse_retries + 1):
        response = model.complete(current_prompt)
        try:
            return _json_payload(response)
        except (json.JSONDecodeError, ValueError):
            if attempt >= max_parse_retries:
                raise
            current_prompt = (
                prompt + "\n\nYour previous response was malformed or incomplete JSON. "
                "Repeat the task and return one complete JSON object only."
            )
    raise RuntimeError("unreachable JSON response retry state")


def mapping_from_annotations(policy_text: str) -> dict[str, list[str]]:
    """Build requirement-to-policy lineage from Cedar annotations."""
    mapping: dict[str, list[str]] = {}
    for policy in PolicySet(policy_text).policies():
        annotations = policy.annotations()
        source = annotations.get("source", "")
        policy_id = annotations.get("id", policy.id())
        if "#" not in source:
            continue
        requirement_id = source.rsplit("#", 1)[-1]
        mapping.setdefault(requirement_id, []).append(policy_id)
    return mapping


def _best_effort_mapping(policy_text: str) -> dict[str, list[str]]:
    """Extract lineage without preventing hard-critic repair of invalid Cedar."""
    try:
        return mapping_from_annotations(policy_text)
    except Exception:
        return {}


class ModelPolicyGenerator:
    """Generate structured Cedar output with an arbitrary text model."""

    def __init__(self, model: TextModel):
        self.model = model

    def generate(
        self,
        grounded: AutoformalizationInput,
        prompt: str,
        *,
        round_number: int,
    ) -> PolicyCandidate:
        del grounded, round_number
        payload = _complete_json_payload(self.model, prompt)
        policies = payload.get("policies")
        if not isinstance(policies, str):
            raise ValueError("generator response is missing string field 'policies'")
        raw_mapping = payload.get("requirement_mapping", {})
        mapping = (
            {
                str(key): [str(item) for item in value]
                for key, value in raw_mapping.items()
                if isinstance(value, list)
            }
            if isinstance(raw_mapping, dict)
            else {}
        )
        raw_unsupported = payload.get("unsupported_requirements", [])
        raw_assumptions = payload.get("assumptions", [])
        raw_changes = payload.get("changes", [])
        unsupported = raw_unsupported if isinstance(raw_unsupported, list) else []
        assumptions = raw_assumptions if isinstance(raw_assumptions, list) else []
        changes = raw_changes if isinstance(raw_changes, list) else []
        return PolicyCandidate(
            policies=policies,
            requirement_mapping=mapping or _best_effort_mapping(policies),
            unsupported_requirements=[str(item) for item in unsupported],
            assumptions=[str(item) for item in assumptions],
            changes=[str(item) for item in changes],
        )


class FixturePolicyGenerator:
    """Offline integration backend that returns an explicitly supplied policy.

    This backend makes the full experiment reproducible without model credentials. It is
    not used implicitly: callers must explicitly supply the fixture policy path.
    """

    def __init__(self, policy_text: str, *, label: str = "fixture"):
        self.policy_text = policy_text
        self.label = label

    @classmethod
    def from_path(cls, path: str | Path) -> FixturePolicyGenerator:
        source = Path(path)
        return cls(source.read_text(encoding="utf-8"), label=str(source))

    def generate(
        self,
        grounded: AutoformalizationInput,
        prompt: str,
        *,
        round_number: int,
    ) -> PolicyCandidate:
        del grounded, prompt
        return PolicyCandidate(
            policies=self.policy_text,
            requirement_mapping=mapping_from_annotations(self.policy_text),
            changes=[f"round {round_number}: loaded offline fixture {self.label}"],
        )


class SequencePolicyGenerator:
    """Deterministic sequence backend useful for repair-loop tests."""

    def __init__(self, candidates: Sequence[PolicyCandidate]):
        if not candidates:
            raise ValueError("at least one candidate is required")
        self._candidates = list(candidates)

    def generate(
        self,
        grounded: AutoformalizationInput,
        prompt: str,
        *,
        round_number: int,
    ) -> PolicyCandidate:
        del grounded, prompt
        index = min(round_number - 1, len(self._candidates) - 1)
        return self._candidates[index]

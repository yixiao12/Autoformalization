"""Minimal authenticated model connectivity check."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .config import load_env_file, load_model_settings, settings_as_safe_dict
from .generator import LiteLLMTextModel


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check configured model connectivity")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    args = parser.parse_args(argv)

    load_env_file(args.env_file)
    settings = load_model_settings(args.config)
    provider = settings.provider
    model = LiteLLMTextModel(
        settings.model,
        provider=provider.name,
        base_url=provider.base_url,
        wire_api=provider.wire_api,
        api_key_env=provider.api_key_env,
        requires_auth=provider.requires_openai_auth,
        reasoning_effort=settings.reasoning_effort,
        store=settings.store,
        max_output_tokens=32,
        timeout_seconds=min(settings.timeout_seconds, 120.0),
        max_retries=settings.max_retries,
        retry_base_seconds=settings.retry_base_seconds,
        stream=settings.stream,
    )
    try:
        output = model.complete("Reply with exactly: OK")
    except Exception as exc:
        print(
            json.dumps(
                {
                    "status": "error",
                    "configuration": settings_as_safe_dict(settings),
                    "error_type": exc.__class__.__name__,
                    "error": str(exc),
                },
                indent=2,
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 2
    print(
        json.dumps(
            {
                "status": "ok",
                "configuration": settings_as_safe_dict(settings),
                "response": output.strip(),
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

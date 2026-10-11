"""Small, sequential provider probes; connectivity is not semantic evaluation."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict
from typing import Any

from .generators import Generator, ProviderError
from .types import GenerationRequest, Usage

ACCOUNT_BLOCKING_CODES = frozenset(
    {
        "Arrearage",
        "insufficient_quota",
        "InvalidApiKey",
        "invalid_api_key",
        "FreeTierOnly",
        "QuotaExhausted",
    }
)


async def probe_models(generators: Mapping[str, Generator]) -> list[dict[str, Any]]:
    """Stop after the first unavailable endpoint; preserve known/unknown probe billing."""
    checks = []
    for model, generator in generators.items():
        usage = Usage()
        failure = None
        try:
            generation = await generator.generate(
                GenerationRequest(
                    source={},
                    prompt="Return a JSON object with ok=true.",
                    output_schema={
                        "type": "object",
                        "properties": {"ok": {"const": True}},
                        "required": ["ok"],
                        "additionalProperties": False,
                    },
                    instructions="Return only the requested JSON object.",
                )
            )
            usage = generation.usage
            if generation.content != {"ok": True}:
                failure = {
                    "category": "invalid_response",
                    "http_status": None,
                    "provider_code": None,
                }
        except ProviderError as exc:
            usage = exc.usage
            failure = exc.diagnostics()
        except Exception:
            failure = {"category": "provider_error", "http_status": None, "provider_code": None}
        checks.append(
            {
                "model": model,
                "ready": failure is None,
                "model_calls": 1,
                "usage": asdict(usage),
                "failure": failure,
            }
        )
        if failure is not None:
            break
    return checks


def account_blocked(record: dict[str, Any]) -> bool:
    failures = [
        *record.get("provider_failures", []),
        *record.get("runtime", {}).get("provider_failures", []),
    ]
    failure = record.get("provider_error")
    if failure:
        failures.append(failure)
    failures.extend(
        event["details"]
        for event in record.get("runtime", {}).get("trace", [])
        if event["event"] == "call_failed"
    )
    return any(f.get("provider_code") in ACCOUNT_BLOCKING_CODES for f in failures)

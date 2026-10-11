import asyncio

import httpx
import pytest

from verifigen import CompatibleChatGenerator, FunctionGenerator
from verifigen.generators import ProviderError
from verifigen.preflight import account_blocked, probe_models
from verifigen.types import Usage


async def test_preflight_stops_after_first_failure_and_retains_sanitized_billing():
    calls = []

    class Broken:
        async def generate(self, request):
            calls.append("broken")
            raise ProviderError(
                "PRIVATE_SECRET",
                category="http_error",
                http_status=400,
                provider_code="Arrearage",
                usage=Usage(10, 5),
            )

    checks = await probe_models(
        {
            "first": FunctionGenerator(lambda request: {"ok": True}),
            "second": Broken(),
            "third": FunctionGenerator(lambda request: calls.append("unexpected")),
        }
    )
    assert calls == ["broken"] and len(checks) == 2
    assert checks[0]["ready"] and not checks[1]["ready"]
    assert checks[1]["usage"]["input_tokens"] == 10
    assert checks[1]["failure"]["provider_code"] == "Arrearage"
    assert "PRIVATE_SECRET" not in str(checks)


async def test_preflight_rejects_invalid_output_without_logging_content():
    checks = await probe_models({"model": FunctionGenerator(lambda request: "PRIVATE_SECRET")})
    assert not checks[0]["ready"] and "PRIVATE_SECRET" not in str(checks)


async def test_preflight_cancellation_is_not_a_fake_failed_probe():
    class Cancelled:
        async def generate(self, request):
            raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        await probe_models({"model": Cancelled()})


@pytest.mark.parametrize(
    "code,expected",
    [
        ("Arrearage", "Arrearage"),
        ("Throttling.RateQuota", "Throttling.RateQuota"),
        ("PRIVATE_SECRET", None),
    ],
)
async def test_http_error_retains_only_allowlisted_metadata(code, expected):
    client = CompatibleChatGenerator(
        base_url="https://example.test/v1",
        model="model",
        api_key="PRIVATE_SECRET",
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                400,
                json={"error": {"code": code, "message": "PRIVATE_SECRET"}},
            )
        ),
    )
    checks = await probe_models({"model": client})
    failure = checks[0]["failure"]
    assert failure == {"category": "http_error", "http_status": 400, "provider_code": expected}
    assert "PRIVATE_SECRET" not in str(checks)


def test_account_guard_covers_reviewer_self_refinement_and_semantic_arms():
    failure = {"provider_code": "Arrearage"}
    assert account_blocked({"provider_error": failure})
    assert account_blocked({"runtime": {"provider_failures": [failure]}})
    assert account_blocked({"runtime": {"trace": [{"event": "call_failed", "details": failure}]}})
    assert not account_blocked({"provider_error": {"provider_code": "Throttling.RateQuota"}})
    assert not account_blocked({"runtime": {"trace": []}})

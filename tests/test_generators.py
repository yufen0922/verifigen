import asyncio
import json

import httpx
import pytest

from verifigen.generators import CompatibleChatGenerator, ProviderError, ReplayGenerator
from verifigen.types import GenerationRequest

REQUEST = GenerationRequest({"order": "O1"}, "explain", {"type": "object"}, "Return JSON")


def client(handler, **kwargs):
    return CompatibleChatGenerator(
        base_url="https://example.invalid/v1",
        model="mock-model",
        api_key="secret-123",
        transport=httpx.MockTransport(handler),
        **kwargs,
    )


async def test_compatible_request_and_reported_usage():
    def handler(request):
        assert request.url.path == "/v1/chat/completions"
        assert request.headers["Authorization"] == "Bearer secret-123"
        body = json.loads(request.content)
        assert body["model"] == "mock-model"
        assert body["response_format"] == {"type": "json_object"}
        assert json.loads(body["messages"][1]["content"])["source"] == {"order": "O1"}
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": '{"ok": true}'}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 100, "completion_tokens": 20},
            },
        )

    result = await client(handler, input_usd_per_million=1, output_usd_per_million=2).generate(
        REQUEST
    )
    assert result.content == {"ok": True}
    assert result.usage.total_tokens == 120
    assert result.usage.cost_usd == pytest.approx(0.00014)


async def test_provider_specific_extra_body_is_sent_without_overriding_core_fields():
    def handler(request):
        body = json.loads(request.content)
        assert body["model"] == "mock-model"
        assert body["enable_thinking"] is True
        assert body["thinking_budget"] == 2048
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "{}"}, "finish_reason": "stop"}]},
        )

    await client(
        handler,
        extra_body={"enable_thinking": True, "thinking_budget": 2048},
    ).generate(REQUEST)


def test_extra_body_cannot_override_core_request_fields():
    with pytest.raises(ValueError, match="reserved"):
        client(lambda request: httpx.Response(200), extra_body={"model": "other"})


async def test_missing_usage_is_unknown_and_invalid_json_reaches_schema_check():
    result = await client(
        lambda request: httpx.Response(
            200, json={"choices": [{"message": {"content": "not json"}}]}
        )
    ).generate(REQUEST)
    assert result.content == "not json"
    assert result.usage.total_tokens is None and result.usage.cost_usd is None


@pytest.mark.parametrize("status", [301, 401, 429, 500])
async def test_http_failure_is_redacted_and_not_retried(status):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(
            status,
            text="private order and secret-123",
            headers={"Location": "https://other.invalid"},
        )

    with pytest.raises(ProviderError) as exc:
        await client(handler).generate(REQUEST)
    assert len(calls) == 1 and "secret-123" not in str(exc.value)


async def test_truncated_completion_is_rejected():
    with pytest.raises(ProviderError, match="complete"):
        await client(
            lambda request: httpx.Response(
                200, json={"choices": [{"message": {"content": "{}"}, "finish_reason": "length"}]}
            )
        ).generate(REQUEST)


async def test_malformed_response_is_redacted():
    with pytest.raises(ProviderError, match="failed"):
        await client(lambda request: httpx.Response(200, json={"private": "secret-123"})).generate(
            REQUEST
        )


async def test_provider_timeout_is_redacted():
    def handler(request):
        raise httpx.ReadTimeout("secret-123")

    with pytest.raises(ProviderError, match="failed"):
        await client(handler).generate(REQUEST)


async def test_adapter_cancellation_propagates():
    started = asyncio.Event()

    async def handler(request):
        started.set()
        await asyncio.sleep(10)
        return httpx.Response(200)

    task = asyncio.create_task(client(handler).generate(REQUEST))
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com/v1",
        "https://user:secret@host/v1",
        "https://host/v1?key=secret",
        "file:///tmp/key",
        "https://host/#secret",
    ],
)
def test_invalid_provider_urls_rejected(url):
    with pytest.raises(ValueError):
        CompatibleChatGenerator(base_url=url, model="x", api_key="y")


def test_localhost_model_endpoint_supported():
    CompatibleChatGenerator(base_url="http://127.0.0.1:8000/v1", model="local", api_key="local")


async def test_replay_exhaustion_is_explicit():
    with pytest.raises(ProviderError, match="exhausted"):
        await ReplayGenerator([]).generate(REQUEST)

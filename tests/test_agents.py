import json

import httpx

from verifigen import (
    Criterion,
    LLMJudge,
    LLMRepairer,
    QualityTask,
    make_qwen3_8b_stack,
)
from verifigen.review import JudgeRequest, JudgeVerdict, RepairRequest


def task():
    return QualityTask(
        source={"record": {"amount": 799}},
        prompt="Explain the amount",
        criteria=(Criterion("grounding", "Use the record amount"),),
        output_schema={"type": "object"},
        instructions="Chinese answer",
    )


async def test_llm_judge_prompt_contains_original_context_constraints_and_candidate():
    requests = []

    def handler(request):
        body = json.loads(request.content)
        requests.append(body)
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "status": "pass",
                                    "score": 0.95,
                                    "summary": "ok",
                                    "issues": [],
                                }
                            )
                        },
                        "finish_reason": "stop",
                    }
                ]
            },
        )

    stack = make_qwen3_8b_stack(api_key="secret", transport=httpx.MockTransport(handler))
    response = await stack.judge.judge(JudgeRequest(task(), {"answer": "799"}, 0))

    assert response.verdict.status == "pass"
    body = requests[0]
    assert body["model"] == "qwen3-8b"
    assert body["enable_thinking"] is True and body["thinking_budget"] == 2048
    user = json.loads(body["messages"][1]["content"])
    assert user["source"]["business_context"] == {"record": {"amount": 799}}
    assert user["source"]["quality_criteria"][0]["id"] == "grounding"
    assert user["source"]["candidate_output_schema"] == task().output_schema
    assert user["previous_candidate"] == {"answer": "799"}
    assert "Explain the amount" in user["task"]


async def test_llm_repairer_receives_judge_issues_and_returns_candidate():
    captured = {}

    def handler(request):
        body = json.loads(request.content)
        captured.update(json.loads(body["messages"][1]["content"]))
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "revised_candidate": {"answer": "799"},
                                    "change_summary": "fixed amount",
                                }
                            )
                        },
                        "finish_reason": "stop",
                    }
                ]
            },
        )

    stack = make_qwen3_8b_stack(api_key="secret", transport=httpx.MockTransport(handler))
    from verifigen import JudgeIssue

    verdict = JudgeVerdict("fail", 0.1, "wrong", (JudgeIssue("grounding", "use 799"),))
    response = await stack.repairer.repair(RepairRequest(task(), {"answer": "899"}, verdict, 1))

    assert response.candidate == {"answer": "799"}
    assert captured["source"]["judge_verdict"]["issues"][0]["message"] == "use 799"
    assert captured["source"]["candidate_output_schema"] == task().output_schema
    assert captured["previous_candidate"] == {"answer": "899"}
    revised_schema = captured["output_schema"]["properties"]["revised_candidate"]
    assert revised_schema == task().output_schema


def test_qwen_stack_uses_separate_role_adapters():
    stack = make_qwen3_8b_stack(api_key="secret")
    assert isinstance(stack.judge, LLMJudge) and isinstance(stack.repairer, LLMRepairer)
    assert stack.generator is not stack.judge.generator
    assert stack.judge.generator is not stack.repairer.generator


async def test_compatible_client_ignores_malformed_proxy_environment(monkeypatch):
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,::1")
    monkeypatch.setenv("no_proxy", "127.0.0.1,::1")
    captured = {}

    class CapturingClient:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def post(self, url, **_kwargs):
            return httpx.Response(
                200,
                request=httpx.Request("POST", url),
                json={
                    "choices": [
                        {
                            "message": {
                                "content": json.dumps(
                                    {
                                        "status": "pass",
                                        "score": 0.95,
                                        "summary": "ok",
                                        "issues": [],
                                    }
                                )
                            },
                            "finish_reason": "stop",
                        }
                    ]
                },
            )

    monkeypatch.setattr(httpx, "AsyncClient", CapturingClient)
    stack = make_qwen3_8b_stack(api_key="secret")
    response = await stack.judge.judge(JudgeRequest(task(), {"answer": "799"}, 0))
    assert response.verdict.status == "pass"
    assert captured["trust_env"] is False

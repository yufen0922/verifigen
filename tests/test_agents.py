import json

import httpx
import pytest

from verifigen import (
    Criterion,
    LLMJudge,
    LLMRepairer,
    QualityTask,
    make_qwen3_8b_stack,
)
from verifigen.agents import AgentResponseError
from verifigen.generators import FunctionGenerator
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
    instructions = body["messages"][0]["content"]
    assert "Missing source attributes mean unknown, not false" in instructions
    assert "Do not invent extra requirements" in instructions


async def test_llm_repairer_receives_judge_issues_and_returns_candidate():
    captured = {}
    prompts = []

    def handler(request):
        body = json.loads(request.content)
        prompts.append(body["messages"][0]["content"])
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
    assert "never repair an unsupported positive claim by asserting its negation" in prompts[0]


def test_qwen_stack_uses_separate_role_adapters():
    stack = make_qwen3_8b_stack(api_key="secret")
    assert isinstance(stack.judge, LLMJudge) and isinstance(stack.repairer, LLMRepairer)
    assert stack.generator is not stack.judge.generator
    assert stack.judge.generator is not stack.repairer.generator
    assert stack.judge.validate_quotes is False
    assert make_qwen3_8b_stack(api_key="secret", validate_judge_quotes=True).judge.validate_quotes


@pytest.mark.parametrize(
    "candidate_quote,source_quote",
    [
        ("899", "799"),
        ("899", ""),
        ("899", None),
    ],
)
async def test_quote_aware_judge_retains_verified_fragments(candidate_quote, source_quote):
    judge = LLMJudge(
        FunctionGenerator(
            lambda request: {
                "status": "fail",
                "score": 0,
                "summary": "Wrong amount",
                "issues": [
                    {
                        "criterion_id": "grounding",
                        "message": "Wrong amount",
                        "evidence": "record amount is 799",
                        "candidate_quote": candidate_quote,
                        "source_quote": source_quote,
                    }
                ],
            }
        ),
        validate_quotes=True,
    )
    response = await judge.judge(JudgeRequest(task(), {"answer": "899"}, 0))
    assert response.verdict.issues[0].candidate_quote == candidate_quote
    assert response.verdict.issues[0].source_quote == (source_quote or "")


async def test_plain_judge_schema_does_not_request_experimental_quote_fields():
    captured = []

    def answer(request):
        captured.append(request.output_schema)
        return {"status": "pass", "score": 1, "summary": "Supported", "issues": []}

    await LLMJudge(FunctionGenerator(answer)).judge(JudgeRequest(task(), {"answer": "799"}, 0))
    issue = captured[0]["$defs"]["_IssuePayload"]["properties"]
    assert "source_quote" not in issue and "candidate_quote" not in issue
    assert issue["criterion_id"]["enum"] == ["general", "grounding"]
    assert captured[0]["properties"]["status"]["enum"] == ["pass", "fail", "unknown"]


@pytest.mark.parametrize(
    "candidate_quote,source_quote",
    [
        ("made-up claim", "799"),
        ("899", "made-up evidence"),
        ("", "799"),
        ("899", "79"),
    ],
)
async def test_quote_aware_judge_rejects_fabricated_feedback(candidate_quote, source_quote):
    judge = LLMJudge(
        FunctionGenerator(
            lambda request: {
                "status": "fail",
                "score": 0,
                "summary": "Wrong amount",
                "issues": [
                    {
                        "criterion_id": "grounding",
                        "message": "Wrong amount",
                        "evidence": "record amount is 799",
                        "candidate_quote": candidate_quote,
                        "source_quote": source_quote,
                    }
                ],
            }
        ),
        validate_quotes=True,
    )
    with pytest.raises(AgentResponseError) as exc:
        await judge.judge(JudgeRequest(task(), {"answer": "899"}, 0))
    assert exc.value.usage.total_tokens == 0


async def test_quote_match_handles_nested_text_and_whitespace_without_using_history():
    current = QualityTask(
        source={"reviews": [{"text": "Delivery is\n unavailable."}]},
        prompt="Summarize",
        criteria=(Criterion("grounding", "Use the evidence"),),
    )
    judge = LLMJudge(
        FunctionGenerator(
            lambda request: {
                "status": "fail",
                "score": 0,
                "summary": "Unsupported",
                "issues": [
                    {
                        "criterion_id": "grounding",
                        "message": "Wrong service",
                        "evidence": "Review says unavailable",
                        "candidate_quote": "Delivery is available",
                        "source_quote": "Delivery is unavailable.",
                    }
                ],
            }
        ),
        validate_quotes=True,
    )
    response = await judge.judge(JudgeRequest(current, {"answer": "Delivery is available"}, 0))
    assert response.verdict.status == "fail"


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

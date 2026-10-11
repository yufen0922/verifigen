import asyncio
import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from verifigen import FunctionGenerator, FunctionJudge, FunctionRepairer, JudgeIssue, JudgeVerdict
from verifigen.config import ModelSettings
from verifigen.web import create_app


def payload(**changes):
    return {
        "scenario": "custom",
        "source": {"amount": 799},
        "prompt": "Report amount",
        "criteria": [{"id": "grounding", "description": "Use source amount"}],
        "output_schema": {
            "type": "object",
            "properties": {"answer": {"type": "string"}},
            "required": ["answer"],
        },
        "initial": {"answer": "899"},
        **changes,
    }


def agents(*, slow=False):
    async def judge(request):
        if slow:
            await asyncio.sleep(10)
        if request.candidate == {"answer": str(request.task.source["amount"])}:
            return JudgeVerdict("pass", 0.95, "Supported")
        return JudgeVerdict(
            "fail",
            0.2,
            "Wrong amount",
            (JudgeIssue("grounding", "Wrong amount", "Source says 799", "Use source amount"),),
        )

    return SimpleNamespace(
        generator=FunctionGenerator(lambda r: {"answer": str(r.source["amount"])}),
        judge=FunctionJudge(judge),
        repairer=FunctionRepairer(lambda r: {"answer": str(r.task.source["amount"])}),
    )


@pytest.fixture
def client(tmp_path):
    with TestClient(
        create_app(
            settings=ModelSettings(api_key="PRIVATE_TEST_SECRET"), run_dir=tmp_path, stack=agents()
        )
    ) as session:
        yield session


def test_real_workbench_routes_export_rounds_and_do_not_expose_config_secret(client):
    config = client.get("/api/config")
    assert config.json()["configured"]
    assert "PRIVATE_TEST_SECRET" not in config.text
    identifier = client.post("/api/runs", json=payload()).json()["id"]
    result = client.get(f"/api/runs/{identifier}").json()
    assert result["state"] == "passed"
    assert result["result"]["output"] == {"answer": "799"}
    assert result["result"]["repair_rounds"] == 1
    assert [r["candidate"]["answer"] for r in result["result"]["rounds"]] == ["899", "799"]
    assert "PRIVATE_TEST_SECRET" not in json.dumps(result)
    events = client.get(f"/api/runs/{identifier}/events")
    assert events.headers["content-type"].startswith("text/event-stream")
    assert '"event": "complete"' in events.text
    assert len(client.get("/api/history").json()) == 1


def test_no_key_is_a_clear_configuration_error(tmp_path):
    with TestClient(create_app(settings=ModelSettings(api_key=""), run_dir=tmp_path)) as session:
        response = session.post("/api/runs", json=payload())
        assert response.status_code == 422
        assert "DASHSCOPE_API_KEY" in response.text


def test_budget_zero_repairs_returns_fallback(client):
    identifier = client.post("/api/runs", json=payload(max_repair_rounds=0)).json()["id"]
    result = client.get(f"/api/runs/{identifier}").json()["result"]
    assert result["output"] is None and result["reason"] == "repair_budget"


def test_reason_specific_fallback_is_preserved_by_the_web_adapter(client):
    identifier = client.post(
        "/api/runs",
        json=payload(
            max_repair_rounds=0, fallback_by_reason={"repair_budget": "请人工核实原始金额。"}
        ),
    ).json()["id"]
    result = client.get(f"/api/runs/{identifier}").json()["result"]
    assert result["text"] == "请人工核实原始金额。"
    assert result["output"] is None


def test_generator_path_really_runs_before_judge(client):
    identifier = client.post("/api/runs", json=payload(generate=True)).json()["id"]
    record = client.get(f"/api/runs/{identifier}").json()
    assert any(
        e["event"] == "call_started" and e["details"]["role"] == "generator"
        for e in record["events"]
    )
    assert record["result"]["repair_rounds"] == 0


def test_web_initial_refinement_is_visible_budgeted_and_still_judged(client):
    identifier = client.post(
        "/api/runs",
        json=payload(initial_refinement=True, judge_history="none"),
    ).json()["id"]
    record = client.get(f"/api/runs/{identifier}").json()
    assert record["result"]["output"] == {"answer": "799"}
    assert record["result"]["repair_rounds"] == 1
    assert len(record["result"]["rounds"]) == 1
    assert any(e["event"] == "initial_refined" for e in record["events"])
    assert record["input"]["max_protocol_retries"] == 1


def test_experimental_modes_are_saved_and_fulfillment_is_an_explicit_criterion(client):
    identifier = client.post(
        "/api/runs",
        json=payload(
            initial_refinement=True,
            refinement_mode="source_first",
            judge_strategy="claims",
            check_fulfillment=True,
        ),
    ).json()["id"]
    record = client.get(f"/api/runs/{identifier}").json()
    assert record["input"]["judge_strategy"] == "claims"
    assert record["input"]["refinement_mode"] == "source_first"
    started = next(e for e in record["events"] if e["event"] == "started")
    assert started["details"]["criteria"] == ["grounding", "fulfillment"]


def test_incompatible_judge_flags_fail_before_execution(client):
    response = client.post(
        "/api/runs",
        json=payload(
            judge_strategy="claims",
            validate_judge_quotes=True,
        ),
    )
    assert response.status_code == 422


def test_invalid_schema_fails_closed_before_judgment(client):
    identifier = client.post("/api/runs", json=payload(output_schema={"type": "invalid"})).json()[
        "id"
    ]
    result = client.get(f"/api/runs/{identifier}").json()["result"]
    assert result["reason"] == "invalid_schema" and not result["verdicts"]


@pytest.mark.parametrize(
    "changes",
    [
        {"max_repair_rounds": 20},
        {"max_model_calls": -1},
        {"min_pass_score": 2},
        {"criteria": []},
        {"judge_history": "invalid"},
        {"max_protocol_retries": 2},
        {"max_protocol_retries": True},
        {"criteria": [{"id": "x", "description": "a"}, {"id": "x", "description": "b"}]},
    ],
)
def test_invalid_inputs_are_rejected_before_start(client, changes):
    assert client.post("/api/runs", json=payload(**changes)).status_code == 422


def test_cross_site_model_calls_and_path_traversal_are_rejected(client):
    assert (
        client.post(
            "/api/runs", json=payload(), headers={"origin": "https://evil.example"}
        ).status_code
        == 403
    )
    assert client.get("/api/runs/not-a-valid-id").status_code == 404
    assert client.get("/api/config", headers={"host": "evil.example"}).status_code == 400


def test_cancellation_and_concurrency_limit(tmp_path):
    with TestClient(
        create_app(
            settings=ModelSettings(api_key="unused"), run_dir=tmp_path, stack=agents(slow=True)
        )
    ) as session:
        ids = [session.post("/api/runs", json=payload()).json()["id"] for _ in range(3)]
        assert session.post("/api/runs", json=payload()).status_code == 429
        assert session.post(f"/api/runs/{ids[0]}/cancel").json()["state"] == "cancelled"
        assert session.get(f"/api/runs/{ids[0]}").json()["result"] is None


def test_history_survives_app_restart(tmp_path):
    settings = ModelSettings(api_key="unused")
    with TestClient(create_app(settings=settings, run_dir=tmp_path, stack=agents())) as session:
        identifier = session.post("/api/runs", json=payload()).json()["id"]
        assert session.get(f"/api/runs/{identifier}").json()["state"] == "passed"
    with TestClient(create_app(settings=settings, run_dir=tmp_path, stack=agents())) as session:
        assert session.get(f"/api/runs/{identifier}").json()["state"] == "passed"
        assert session.get("/api/history").json()[0]["id"] == identifier


def test_static_assets_and_public_data_are_available(client):
    assert client.get("/").status_code == 200
    assert client.get("/static/app.js").status_code == 200
    assert len(client.get("/api/presets").json()) == 6
    assert (
        client.get("/api/evaluations").json()[0]["summary"]["overall"]["judge_detection_accuracy"]
        == 173 / 180
    )


def test_corrupted_history_is_skipped_without_crashing(tmp_path):
    (tmp_path / ("a" * 32 + ".json")).write_text("{}")
    (tmp_path / ("b" * 32 + ".json")).write_text("not json")
    (tmp_path / "unrelated.json").write_text("{}")
    with TestClient(create_app(settings=ModelSettings(api_key=""), run_dir=tmp_path)) as session:
        assert session.get("/api/history").json() == []
        assert session.get("/api/runs/" + "a" * 32).status_code == 404


@pytest.mark.parametrize("scenario", ["support", "report"])
def test_invalid_domain_source_does_not_spend_model_calls(client, scenario):
    assert client.post("/api/runs", json=payload(scenario=scenario)).status_code == 422


def test_completed_history_has_owner_only_permissions(tmp_path):
    with TestClient(
        create_app(settings=ModelSettings(api_key="unused"), run_dir=tmp_path, stack=agents())
    ) as client:
        identifier = client.post("/api/runs", json=payload()).json()["id"]
        client.get(f"/api/runs/{identifier}/events")
        assert (tmp_path / f"{identifier}.json").stat().st_mode & 0o777 == 0o600


def test_completed_run_can_be_deleted_from_memory_and_disk(tmp_path):
    with TestClient(
        create_app(settings=ModelSettings(api_key="unused"), run_dir=tmp_path, stack=agents())
    ) as client:
        identifier = client.post("/api/runs", json=payload()).json()["id"]
        client.get(f"/api/runs/{identifier}/events")
        assert client.delete(f"/api/runs/{identifier}").json()["state"] == "deleted"
        assert client.get(f"/api/runs/{identifier}").status_code == 404
        assert not (tmp_path / f"{identifier}.json").exists()
        assert client.get("/api/history").json() == []


def test_running_run_must_be_cancelled_before_deletion(tmp_path):
    with TestClient(
        create_app(
            settings=ModelSettings(api_key="unused"), run_dir=tmp_path, stack=agents(slow=True)
        )
    ) as client:
        identifier = client.post("/api/runs", json=payload()).json()["id"]
        assert client.delete(f"/api/runs/{identifier}").status_code == 409
        client.post(f"/api/runs/{identifier}/cancel")
        assert client.delete(f"/api/runs/{identifier}").status_code == 200


def test_chunked_body_is_bounded_before_json_validation(client):
    def oversized():
        yield b'{"prompt":"'
        yield b"x" * 256000
        yield b"x" * 256001
        yield b'"}'

    response = client.post(
        "/api/runs", content=oversized(), headers={"content-type": "application/json"}
    )
    assert response.status_code == 413
    assert client.get("/api/history").json() == []


def test_cross_origin_delete_is_rejected(client):
    identifier = client.post("/api/runs", json=payload()).json()["id"]
    response = client.delete(f"/api/runs/{identifier}", headers={"origin": "https://evil.example"})
    assert response.status_code == 403


def test_comparison_route_is_available(client):
    assert client.get("/api/comparison").status_code == 200


def test_history_ablation_is_recorded_and_forwarded_to_the_runtime(client):
    identifier = client.post("/api/runs", json=payload(judge_history="none")).json()["id"]
    result = client.get(f"/api/runs/{identifier}").json()["result"]
    assert result["trace"][0]["details"]["judge_history"] == "none"
    assert result["status"] == "passed"

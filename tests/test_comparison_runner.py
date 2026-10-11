import asyncio
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("stage", ["runtime", "review"])
async def test_account_failure_stops_queue_but_retains_inflight_attempt(
    tmp_path, monkeypatch, stage
):
    spec = importlib.util.spec_from_file_location(
        "comparison_runner", ROOT / "examples/ragtruth/compare.py"
    )
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    config = json.loads(
        (ROOT / "benchmarks/results/ragtruth-evidence-plus-restored-dev-30/config.json").read_text()
    )
    args = SimpleNamespace(
        **{
            k: config[k]
            for k in (
                "reviewer_model",
                "thinking_budget",
                "concurrency",
                "per_task",
                "split",
                "judge_history",
                "max_protocol_retries",
                "enable_thinking",
                "validate_judge_quotes",
                "judge_strategy",
                "refinement_mode",
                "check_fulfillment",
                "max_output_tokens",
            )
        },
        samples=ROOT / "benchmarks/data/ragtruth-600/samples.jsonl",
        output=tmp_path,
        exclude_records=None,
        optimized=True,
        resume=False,
        judge_model=None,
    )
    args.concurrency = 2
    stack = SimpleNamespace(
        judge=SimpleNamespace(generator=SimpleNamespace(model="runtime"), validate_quotes=False)
    )
    settings = SimpleNamespace(
        model="runtime",
        api_key="PRIVATE_SECRET",
        base_url="https://example.test/v1",
        stack=lambda **kwargs: stack,
    )
    monkeypatch.setattr(runner.ModelSettings, "from_env", lambda path: settings)
    monkeypatch.setattr(runner, "CompatibleChatGenerator", lambda **kwargs: object())
    monkeypatch.setattr(runner, "select_cohort", lambda *a, **kw: [{"id": "one"}])
    monkeypatch.setattr(runner, "OPTIMIZED_ARMS", ("first", "inflight", "queued"))

    async def probes(models):
        return [{"model": model, "ready": True, "failure": None} for model in models]

    monkeypatch.setattr(runner, "probe_models", probes)
    calls = []
    started = asyncio.Event()

    async def attempt(identifier):
        calls.append(identifier)
        if identifier == "first":
            await started.wait()
            return {"provider_error": {"provider_code": "Arrearage"}}
        if identifier == "inflight":
            started.set()
            await asyncio.sleep(0.02)
            return {"provider_error": None}
        pytest.fail("Queued request must not reach the provider")

    async def run(sample, arm, *a, **kw):
        result = await attempt(arm) if stage == "runtime" else {}
        return {"id": sample["id"], "arm": arm, **result}

    async def review(packet, reviewer):
        assert stage == "review", "Review must not start after a runtime account failure"
        return {"review_id": packet["review_id"], **await attempt(packet["review_id"])}

    monkeypatch.setattr(runner, "run_arm", run)
    monkeypatch.setattr(runner, "review_packet", review)
    monkeypatch.setattr(
        runner,
        "blind_packets",
        lambda *a: ([{"review_id": name} for name in ("first", "inflight", "queued")], []),
    )
    with pytest.raises(ValueError, match="queued work stopped"):
        await runner.evaluate(args)
    assert calls == ["first", "inflight"]
    filename = "records.jsonl" if stage == "runtime" else "reviews.jsonl"
    rows = [json.loads(line) for line in (tmp_path / filename).read_text().splitlines()]
    assert len(rows) == 2
    assert {row.get("arm", row.get("review_id")) for row in rows} == {"first", "inflight"}
    assert not (tmp_path / "summary.json").exists()
    assert "PRIVATE_SECRET" not in "".join(path.read_text() for path in tmp_path.iterdir())

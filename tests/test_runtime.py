import asyncio
import json
from dataclasses import replace

import pytest
from pydantic import BaseModel, ConfigDict

from verifigen import (
    Budget,
    CheckResult,
    Context,
    Contract,
    FactVerifier,
    FieldVerifier,
    Harness,
    ReplayGenerator,
    RuleVerifier,
    write_trace,
)
from verifigen.domains.report import make_report_contract
from verifigen.domains.support import demo_source, make_support_contract, template_response
from verifigen.types import Generation, Usage, VerificationReport


class Item(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    number: int
    doubled: int
    caption: str


def item_contract(*extra):
    return Contract(
        Item,
        (
            FactVerifier.from_path("number", "/number", "/number"),
            FieldVerifier(
                "doubled", "/doubled", lambda d, _ctx: d["number"] * 2, depends_on=("/number",)
            ),
            FieldVerifier(
                "caption",
                "/caption",
                lambda d, _ctx: f"double={d['doubled']}",
                depends_on=("/doubled",),
            ),
            *extra,
        ),
        lambda d: d["caption"],
    )


async def test_transitive_dependency_closure():
    result = await Harness(item_contract()).run(
        source={"number": 7}, initial={"number": 4, "doubled": 8, "caption": "double=8"}
    )
    assert result.output == {"number": 7, "doubled": 14, "caption": "double=14"}
    assert result.repair_rounds == 1 and result.model_calls == 0


async def test_cross_rule_regression_rolls_back_and_never_publishes():
    rule = RuleVerifier("legacy_limit", lambda draft, _ctx: draft["doubled"] < 10)
    result = await Harness(item_contract(rule)).run(
        source={"number": 7}, initial={"number": 4, "doubled": 8, "caption": "double=8"}
    )
    assert result.reason == "repair_regression" and result.output is None
    assert any(event.event == "rollback" for event in result.trace)


async def test_custom_verifier_exception_is_unknown_not_pass():
    class Broken:
        name = "broken"

        async def verify(self, candidate, context):
            raise RuntimeError("secret-token-value")

    result = await Harness(item_contract(Broken())).run(
        source={"number": 4}, initial={"number": 4, "doubled": 8, "caption": "double=8"}
    )
    assert result.reason == "verification_unknown"
    assert "secret-token-value" not in json.dumps(result.to_dict())


async def test_verifier_cannot_mutate_another_verifiers_candidate():
    class Mutating:
        name = "mutating"

        async def verify(self, candidate, context):
            candidate["number"] = 999
            return CheckResult(self.name, "pass")

    result = await Harness(item_contract(Mutating())).run(
        source={"number": 4}, initial={"number": 4, "doubled": 8, "caption": "double=8"}
    )
    assert result.output["number"] == 4


async def test_source_snapshot_is_immutable():
    ctx = Context.create({"number": 4, "nested": {"x": 1}})
    with pytest.raises(TypeError):
        ctx.source["nested"]["x"] = 5


async def test_expected_callback_cannot_modify_unrelated_fields():
    def expected(draft, ctx):
        draft["caption"] = "accidental side effect"
        return ctx.source["number"]

    contract = Contract(
        Item, (FieldVerifier("number", "/number", expected),), lambda d: d["caption"]
    )
    result = await Harness(contract).run(
        source={"number": 7}, initial={"number": 4, "doubled": 8, "caption": "preserve this"}
    )
    assert result.output["caption"] == "preserve this"


async def test_non_json_generation_does_not_double_count_usage():
    class Invalid:
        async def generate(self, request):
            return Generation({"number": float("nan")}, Usage(10, 2))

    result = await Harness(item_contract(), Invalid()).run(source={"number": 1})
    assert result.reason == "candidate_not_json"
    assert len(result.usages) == 1 and result.usages[0].total_tokens == 12


async def test_deadline_cancels_async_generator():
    cancelled = asyncio.Event()

    class Slow:
        async def generate(self, request):
            try:
                await asyncio.sleep(10)
            finally:
                cancelled.set()

    result = await Harness(item_contract(), Slow(), budget=Budget(deadline_seconds=0.01)).run(
        source={"number": 1}
    )
    assert result.reason == "deadline" and result.model_calls == 1
    assert result.usages[0].total_tokens is None
    assert cancelled.is_set()


async def test_evidence_expiring_during_generation_is_not_released():
    source = demo_source()

    class Slow:
        async def generate(self, request):
            await asyncio.sleep(0.02)
            return Generation(template_response(request.source))

    result = await Harness(make_support_contract(max_age_seconds=0.01), Slow()).run(source=source)
    assert result.status == "fallback"
    assert result.report.status == "unknown"


async def test_external_cancellation_propagates():
    started = asyncio.Event()

    class Slow:
        async def generate(self, request):
            started.set()
            await asyncio.sleep(10)

    task = asyncio.create_task(Harness(item_contract(), Slow()).run(source={"number": 1}))
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


async def test_model_call_budget():
    generator = ReplayGenerator(["invalid"])
    result = await Harness(item_contract(), generator, budget=Budget(max_model_calls=1)).run(
        source={"number": 4}
    )
    assert result.reason == "model_budget" and generator.calls == 1


async def test_repeated_candidate_stops_early():
    generator = ReplayGenerator(["invalid", "invalid"])
    result = await Harness(item_contract(), generator).run(source={"number": 4})
    assert result.reason == "no_progress"


async def test_unknown_usage_does_not_become_zero_budget():
    class UnknownUsage:
        async def generate(self, request):
            return Generation({"number": 1, "doubled": 2, "caption": "double=2"}, Usage())

    result = await Harness(
        item_contract(), UnknownUsage(), budget=Budget(max_observed_tokens=100)
    ).run(source={"number": 1})
    assert result.reason == "usage_unknown" and result.output is None


async def test_observed_token_limit_stops_after_response():
    class Measured:
        async def generate(self, request):
            return Generation({}, Usage(90, 20))

    result = await Harness(item_contract(), Measured(), budget=Budget(max_observed_tokens=100)).run(
        source={"number": 1}
    )
    assert result.reason == "token_threshold" and result.model_calls == 1


async def test_async_runs_have_isolated_state():
    harness = Harness(item_contract())
    runs = await asyncio.gather(
        *(
            harness.run(
                source={"number": n}, initial={"number": 0, "doubled": 0, "caption": "double=0"}
            )
            for n in range(12)
        )
    )
    assert [run.output["number"] for run in runs] == list(range(12))
    assert len({run.run_id for run in runs}) == 12


async def test_trace_excludes_values_and_source_text(tmp_path):
    source = demo_source()
    source["order"]["id"] = "PRIVATE-ORDER-9876"
    result = await Harness(make_support_contract()).run(
        source=source, initial=template_response(source)
    )
    path = tmp_path / "trace.jsonl"
    write_trace(result, path)
    assert "PRIVATE-ORDER-9876" not in path.read_text()
    assert all(
        json.loads(line)["run_id"] == result.run_id for line in path.read_text().splitlines()
    )


async def test_renderer_error_falls_back():
    def broken(_draft):
        raise ValueError("private")

    contract = replace(item_contract(), render=broken)
    result = await Harness(contract).run(
        source={"number": 1}, initial={"number": 1, "doubled": 2, "caption": "double=2"}
    )
    assert result.reason == "renderer_error" and result.output is None


async def test_report_domain_repairs_changed_direction_and_sentence():
    draft = {
        "current": 80,
        "previous": 100,
        "delta": -20,
        "direction": "down",
        "sentence": "本期订单80笔，上期100笔，减少20笔。",
    }
    result = await Harness(make_report_contract()).run(
        source={"current": 120, "previous": 100}, initial=draft
    )
    assert result.output["delta"] == 20
    assert result.text == "本期订单120笔，上期100笔，增加20笔。"


def test_cycles_and_duplicate_names_are_rejected():
    with pytest.raises(ValueError, match="cycle"):
        Contract(
            Item,
            (
                FieldVerifier("a", "/number", lambda d, c: 1, depends_on=("/doubled",)),
                FieldVerifier("b", "/doubled", lambda d, c: 2, depends_on=("/number",)),
            ),
            str,
        )
    with pytest.raises(ValueError, match="unique"):
        Contract(
            Item, (RuleVerifier("x", lambda d, c: True), RuleVerifier("x", lambda d, c: True)), str
        )
    with pytest.raises(ValueError, match="unique"):
        Contract(Item, (), str)


def test_empty_report_is_unknown():
    assert VerificationReport(()).status == "unknown"

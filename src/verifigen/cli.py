"""CLI for the LLM quality loop plus v0.1 compatibility commands."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
from typing import Any

from .agents import ReplayJudge, ReplayRepairer
from .benchmark import run_benchmark
from .domains.support import demo_bad_draft, demo_source, make_support_contract
from .generators import CompatibleChatGenerator
from .quality import QualityLoop, write_quality_trace
from .review import Criterion, JudgeIssue, JudgeVerdict, QualityTask
from .runtime import Harness, write_trace
from .types import Budget


def configured_generator() -> CompatibleChatGenerator:
    required = ["VERIFIGEN_BASE_URL", "VERIFIGEN_MODEL", "VERIFIGEN_API_KEY"]
    missing = [key for key in required if not os.environ.get(key)]
    if missing:
        raise ValueError("Set environment variables: " + ", ".join(missing))
    return CompatibleChatGenerator(
        base_url=os.environ[required[0]],
        model=os.environ[required[1]],
        api_key=os.environ[required[2]],
        json_mode=os.environ.get("VERIFIGEN_JSON_MODE", "1") != "0",
    )


def read_json(path: str) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


async def execute(args: argparse.Namespace) -> int:
    if args.command == "benchmark":
        if args.live and args.limit is None:
            raise ValueError("Live evaluation requires an explicit --limit to bound requests")
        summary = await run_benchmark(
            args.dataset,
            args.output,
            live_generator=configured_generator() if args.live else None,
            limit=args.limit,
        )
        print(
            json.dumps(
                {
                    "mode": summary["mode"],
                    "cases": summary["cases"],
                    "strategies": summary["strategies"],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    if args.command == "demo":
        source = demo_source()
        draft = demo_bad_draft(source)
        fixed = {
            "answer": (
                "理解您希望尽快确认处理进度。订单ORDER-1001实付799.00元。"
                "订单已经发货。当前没有退款申请。如需售后，可提交申请，由平台审核。"
            )
        }
        failed = JudgeVerdict(
            "fail",
            0.15,
            "金额、订单状态和退款状态与业务上下文冲突",
            (JudgeIssue("grounding", "候选回答包含多项不受业务记录支持的事实"),),
        )
        quality_result = await QualityLoop(
            judge=ReplayJudge([failed, JudgeVerdict("pass", 0.97, "所有标准均满足")]),
            repairer=ReplayRepairer([fixed]),
        ).run(
            task=QualityTask(
                source=source,
                prompt="根据订单记录回答用户的订单与退款问题。",
                criteria=(
                    Criterion("grounding", "金额、订单状态、退款状态必须符合业务记录。"),
                    Criterion("completeness", "回答必须给出清晰的下一步建议。"),
                ),
                output_schema={"type": "object", "required": ["answer"]},
            ),
            initial={"answer": "".join(draft["sections"].values())},
        )
        print("BEFORE (synthetic faulty draft):")
        print("".join(draft["sections"].values()))
        print("AFTER:")
        print(quality_result.text)
        print(
            json.dumps(
                {
                    "status": quality_result.status,
                    "reason": quality_result.reason,
                    "repair_rounds": quality_result.repair_rounds,
                    "model_calls": quality_result.model_calls,
                },
                ensure_ascii=False,
            )
        )
        if args.trace:
            write_quality_trace(quality_result, args.trace)
            print("Trace saved: " + args.trace)
        if args.output:
            destination = Path(args.output)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(
                json.dumps(quality_result.to_dict(), ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        return 0 if quality_result.status == "passed" else 2

    source = read_json(args.source)
    contract = make_support_contract()
    if args.command == "live":
        result = await Harness(
            contract, configured_generator(), budget=Budget(deadline_seconds=60)
        ).run(source=source, prompt=args.prompt)
    else:
        draft = read_json(args.candidate)
        result = await Harness(contract).run(source=source, initial=draft)
    print("AFTER:")
    print(result.text)
    print(
        json.dumps(
            {
                "status": result.status,
                "reason": result.reason,
                "repair_rounds": result.repair_rounds,
                "model_calls": result.model_calls,
            },
            ensure_ascii=False,
        )
    )
    if args.trace:
        write_trace(result, args.trace)
        print("Trace saved: " + args.trace)
    if args.output:
        destination = Path(args.output)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(
            json.dumps(result.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    return 0 if result.status == "passed" else 2


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="verifigen", description="Context-aware LLM judge and repair loops"
    )
    parser.add_argument("--version", action="version", version="verifigen 0.2.0")
    commands = parser.add_subparsers(dest="command", required=True)
    for name, help_text in (
        ("demo", "Replay a Judge -> Repair -> re-Judge loop without an API key"),
        ("check", "Run the v0.1 deterministic compatibility checker"),
        ("live", "Run the v0.1 compatible generation command"),
    ):
        sub = commands.add_parser(name, help=help_text)
        if name != "demo":
            sub.add_argument("--source", required=True)
        if name == "check":
            sub.add_argument("--candidate", required=True)
        if name == "live":
            sub.add_argument("--prompt", default="请说明订单、退款状态和后续处理建议。")
        sub.add_argument("--trace")
        sub.add_argument("--output")
    bench = commands.add_parser("benchmark", help="Run paired replay or opt-in live evaluation")
    bench.add_argument("--dataset", required=True)
    bench.add_argument("--output", default="runs/benchmark")
    bench.add_argument("--limit", type=int)
    bench.add_argument("--live", action="store_true")
    args = parser.parse_args()
    try:
        code = asyncio.run(execute(args))
    except (ValueError, OSError) as exc:
        parser.exit(2, f"Configuration/input error: {exc}\n")
    except KeyboardInterrupt:
        parser.exit(130, "Cancelled.\n")
    raise SystemExit(code)


if __name__ == "__main__":
    main()

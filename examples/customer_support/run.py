"""Offline customer-support walkthrough using the v0.2 QualityLoop."""

import asyncio

from verifigen import FunctionJudge, FunctionRepairer, JudgeIssue, JudgeVerdict, QualityLoop
from verifigen.domains.support import demo_bad_draft, demo_source, template_response
from verifigen.domains.support_review import make_support_task
from verifigen.scenario_eval import inspect_support_output


async def main():
    source = demo_source()
    bad = demo_bad_draft(source)
    expected = template_response(source, "empathetic")
    case = {
        "expected": expected,
        "forbidden_phrases": ["已经为您退款", "保证24小时内到账", "赠送优惠券"],
    }

    def judge(request):
        failures = inspect_support_output(request.candidate, case)
        if not failures:
            return JudgeVerdict("pass", 0.98, "订单、退款状态和回复文本一致。")
        return JudgeVerdict(
            "fail",
            0.2,
            "回复与订单快照不一致。",
            tuple(JudgeIssue(item, f"未通过 {item} 检查") for item in failures),
        )

    print("错误回复：", "".join(bad["sections"].values()))
    result = await QualityLoop(
        judge=FunctionJudge(judge),
        repairer=FunctionRepairer(lambda _request: expected),
    ).run(make_support_task(source), initial=bad)
    print("修复回复：", result.text)
    print("状态：", result.status, "模型调用：", result.model_calls)
    for event in result.trace:
        print(event.event, event.details)


if __name__ == "__main__":
    asyncio.run(main())

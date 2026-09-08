"""Offline data-to-text walkthrough using the v0.2 QualityLoop."""

import asyncio

from verifigen import FunctionJudge, FunctionRepairer, JudgeIssue, JudgeVerdict, QualityLoop
from verifigen.domains.report_review import expected_report, make_report_task
from verifigen.scenario_eval import inspect_report_output


async def main():
    source = {
        "metric_name": "支付订单",
        "current": 120,
        "previous": 100,
        "unit": "笔",
        "current_period": "本周",
        "previous_period": "上周",
    }
    draft = {
        "metric_name": "支付订单",
        "current": 80,
        "previous": 100,
        "delta": -20,
        "direction": "down",
        "change_rate_percent": -20.0,
        "sentence": "本周支付订单80笔，上周100笔，减少20笔，环比下降20.00%。",
    }
    expected = expected_report(source)
    case = {"source": source, "expected": expected, "forbidden_phrases": []}

    def judge(request):
        failures = inspect_report_output(request.candidate, case)
        if not failures:
            return JudgeVerdict("pass", 0.98, "数值、派生计算和摘要一致。")
        return JudgeVerdict(
            "fail",
            0.2,
            "报告中的数据关系不一致。",
            tuple(JudgeIssue(item, f"未通过 {item} 检查") for item in failures),
        )

    result = await QualityLoop(
        judge=FunctionJudge(judge),
        repairer=FunctionRepairer(lambda _request: expected),
    ).run(make_report_task(source), initial=draft)
    print("修复前：", draft["sentence"])
    print("修复后：", result.text)
    print("修复轮次：", result.repair_rounds)


if __name__ == "__main__":
    asyncio.run(main())

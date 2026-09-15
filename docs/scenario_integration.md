# 接入新场景与配置输出策略

业务接入只依赖公开 SDK。无需修改 `quality.py` 或复制一套循环。

## 最小任务协议

1. `source`：当次输入事实、检索证据或业务快照。
2. `prompt` / `instructions`：原始任务与场景要求。
3. `criteria`：带稳定 ID 的逐项质量规则，供 Judge 定位问题。
4. `output_schema`：Draft 2020-12 JSON Schema，推荐从 Pydantic 模型生成。
5. `renderer`：通过后将候选转换为用户可见文本；必须返回非空字符串。
6. `fallback_text` / `fallback_by_reason`：默认及按原因配置的兜底文案。

下面示例基于已有 RAG 任务，演示独立模型接口、输出关卡与评分策略。运行需要真实百炼凭据，
没有凭据时不会用预置结果替代模型调用。示例政策为演示输入，不代表真实商家的政策。

```python
import asyncio
import os
from dataclasses import replace

from verifigen import QualityBudget, QualityLoop, QualityPolicy, make_qwen3_8b_stack
from verifigen.domains.rag_review import CitationGate, make_rag_task


async def main():
    stack = make_qwen3_8b_stack(
        api_key=os.environ["DASHSCOPE_API_KEY"],
        model=os.environ.get("DASHSCOPE_MODEL", "qwen3.5-flash"),
    )
    task = make_rag_task(
        {
            "question": "耳机拆封后能否无理由退货？运费由谁承担？",
            "product_category": "headphones",
            "retrieved_chunks": [
                {
                    "chunk_id": "RETURN-001",
                    "text": "耳机拆封后不支持无理由退货。未拆封商品收货七日内可申请，非质量问题退货运费由买家承担。",
                }
            ],
        }
    )
    task = replace(
        task,
        fallback_by_reason={
            "judge_unknown": "现有政策材料不足，请联系人工确认。",
            "deadline": "校验超时，请稍后重试。",
            "score_plateau": "自动修复未取得足够进展，请人工复核。",
        },
    )
    loop = QualityLoop(
        generator=stack.generator,
        judge=stack.judge,
        repairer=stack.repairer,
        gates=(CitationGate(),),
        policy=QualityPolicy(score_patience=2),
        budget=QualityBudget(
            max_model_calls=7,
            max_repair_rounds=3,
            deadline_seconds=120,
            min_pass_score=0.85,
            max_observed_tokens=12000,
        ),
    )
    result = await loop.run(task)
    print(result.status, result.reason)
    print(result.text)


asyncio.run(main())
```

仓库中可直接运行的完整检索示例：

```bash
export DASHSCOPE_MODEL=qwen3.5-flash
uv run --extra llm python examples/rag_qa/run_qwen.py --repair-demo --score-patience 2
```

## 自定义业务关卡

实现 `CandidateGate.check(candidate, task)` 异步协议，返回 `tuple[JudgeIssue, ...]`。
空元组表示本关卡未发现问题，有问题时给出规则 ID、证据与修复建议，检查不可用时抛异常。
运行时统一将异常转为 `gate_error`，防止跳过失败的检查继续输出。

优先将规则放在正确的位置：

| 检查内容 | 放置位置 |
|---|---|
| 字段必填、类型、枚举、嵌套结构 | `output_schema`，由内置 SchemaGate 执行 |
| 引用 ID 白名单、确定计算关系 | 场景的 `CandidateGate` 实现 |
| 自然语言是否有依据、是否遗漏需求 | `criteria`，由 LLM Judge 判断 |
| 修复轮次、停止条件、超时 | `QualityBudget` / `QualityPolicy` |
| 与评测标注对比最终正确性 | 评测脚本的独立 oracle，不传给运行时 |

角色和关卡得到隔离的数据副本，但组件对象可被并发调用，需保证自身并发安全。
关卡不要持有全局候选或历史，不要在 async 方法中执行阻塞网络调用。

## 结果与失败语义

- `result.text`：供调用方展示的已审核文本或兜底文案。
- `result.output`：通过时的结构化候选，兜底时为 `None`。
- `result.verdicts`：模型原始判定；保留模型评分与关卡结果的区别。
- `result.gate_reports`：逐轮关卡的结构化问题，包含问题正文。
- `result.trace`：配置、角色调用、关卡问题数量和决策，不含候选正文。
- `result.best_candidate`：诊断数据，不是第二条输出通道。

历史上分数最高的候选也可能错误，兜底时不会自动发布它。`unknown` 表示现有证据不足，
也不会触发 Repair 编造缺失事实。低分 PASS 默认兜底，因为 Judge 未提供可执行的问题清单。

## 接入验收

至少覆盖正常通过、结构错误、业务违规、修复后新增错误、证据不足与调用失败。
先用替身验证调用方接线和预算，再用真实模型评测：分别记录首轮模型判定、关卡拦截、
最终独立评分、兜底率、调用消耗，不能把控制流测试当作模型准确率。
参考 [test_quality_controls.py](../tests/test_quality_controls.py) 和
[180 条历史实测报告](../benchmarks/results/qwen3.5-flash-180/report.md)。

跨场景评测可使用 `--citation-gate` 对比是否添加 RAG 引用关卡，使用 `--score-patience 2`
评估评分停滞策略。默认 Schema 关卡始终启用，不能将该对比称为纯 LLM 与完全无规则的对照。
输出保存预算、策略、样本文件 SHA-256、所选样本 ID、原始判定、关卡报告及决策 Trace。

```bash
uv run --extra llm python examples/multi_scenario/evaluate.py --mode qwen --output runs/schema-only.json
uv run --extra llm python examples/multi_scenario/evaluate.py --mode qwen --citation-gate --output runs/with-citations.json
```

两次独立采样仍有模型随机性，比较时需固定模型版本、样本、thinking budget，并报告各场景结果。

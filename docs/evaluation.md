# LLM Judge/Repair 评测

## 两类测试不能混为一谈

仓库中的自动化测试验证协议解析、上下文透传、fail → repair → pass、unknown 降级、
调用预算、超时和无进展检测等工程行为。Replay/Function 测试替身不调用模型，因此不能说明
Qwen3-8B 的语义判断准确率。

真实模型效果使用 `examples/rag_qa/evaluate_qwen.py`。主评测集由
`scripts/build_rag_eval.py` 确定性生成 60 条样本：6 个商品类别 × 10 条，包含正确初稿、
跨类别混用、错误期限、条件反转、错误运费、缺项、无引用、伪造引用和额外承诺等错误。
另有 `examples/rag_qa/eval_smoke.jsonl` 保留最初的 6 条人工冒烟样本。

脚本不会把 Judge 自己的 `pass` 当作最终正确，而是用 `src/verifigen/rag_eval.py`
里的独立 claim 级规则复核最终输出：每项必需事实都要有对应片段引用、正确措辞、无冲突表述，
并禁止引用其他类别或伪造片段。

```bash
export DASHSCOPE_API_KEY="仅放在当前终端"
python examples/rag_qa/evaluate_qwen.py --limit 6
```

结果写入 `runs/rag-qwen-eval.json`。未设置 API Key 时脚本明确退出。

## 跨场景评测

`examples/multi_scenario/evaluate.py` 用同一个 `QualityLoop` 运行三类任务：

| 场景 | 样本数 | 变化维度 |
|---|---:|---|
| RAG | 60 | 6 类商品 × 10 类正确/错误初稿 |
| 客服回复 | 60 | 6 种退款状态 × 10 类事实、状态、文案和安全错误 |
| 数据转文本 | 60 | 6 种指标变化 × 10 类原值、派生值、单位、文案和归因错误 |

客服覆盖无申请、已申请、已批准、处理中、已到账和失败；数据报告覆盖上升、下降、持平、
降为零以及上期为零无法计算环比。新增 120 条数据由
`scripts/build_multiscenario_eval.py` 确定性生成，每个场景有 6 条正确初稿和 54 条错误初稿。

```bash
python examples/multi_scenario/evaluate.py --mode offline --limit-per-scenario 60 \
  --output runs/multi-scenario-offline.json
```

离线模式使用确定性 Judge/Repair 和独立 oracle，作用是验证 180 条数据标签与三个适配器都能
完成 fail → repair → re-Judge → publish。它预期得到 100% 闭环通过率，但这个数字不能解释为
LLM 效果。真实模型实验使用相同入口：

```bash
export DASHSCOPE_API_KEY="仅放在当前终端"
python examples/multi_scenario/evaluate.py --mode qwen --limit-per-scenario 60 \
  --output runs/multi-scenario-qwen.json
```

Qwen 模式的首轮判定仍与数据标签比较，最终输出仍由 `rag_eval.py` 或 `scenario_eval.py` 独立评分，
不会把 Judge 自己的 pass 当成正确答案。

### 真实 Qwen3.5-Flash 结果

2026-09-08 使用 `qwen3.5-flash`、thinking budget 1024、并发 8 跑完全部 180 条样本。
共发生 513 次模型调用，输入 866,953 Token、输出 641,459 Token。严格 oracle 结果如下：

| 场景 | 首轮判定准确率 | 错误初稿修复成功率 | 最终正确率 | 降级率 |
|---|---:|---:|---:|---:|
| RAG | 96.67% | 98.15% | 98.33% | 0% |
| 客服回复 | 95.00% | 61.11% | 65.00% | 21.67% |
| 数据转文本 | 100.00% | 61.11% | 65.00% | 5.00% |
| 总计 | 97.22% | 73.46% | 76.11% | 8.89% |

164 条输出被 Judge 发布，其中 137 条通过独立 oracle，发布精度为 83.54%；27 条属于错误放行。
因此当前结果支持“RAG 场景效果较强”，但不支持“框架在所有场景都已达到生产可用”。客服失败
主要集中在错误订单事实、陈旧文本和越权承诺的修复；数据报告失败主要集中在自然语言遗漏原值、
期间、方向或零基数说明。可复核的
[实验汇总](../benchmarks/results/qwen3.5-flash-180/summary.json)与
[180 条逐条输出](../benchmarks/results/qwen3.5-flash-180/records.jsonl)已随仓库公开。

这些是模型真实调用结果，但输入仍是模板合成数据，不代表线上业务准确率。下一阶段需要使用脱敏的
真实业务样本，并由未参与 prompt 编写的人进行盲审。

## 当前指标

| 指标 | 定义 |
|---|---|
| `judge_case_accuracy` | 首轮 pass/fail 是否符合人工给定的初稿标签 |
| `bad_case_repair_success` | 错误初稿中，最终输出通过独立窄任务 oracle 的比例 |
| `final_oracle_success` | 所有样本最终输出通过独立 oracle 的比例 |
| `repair_rounds` | 每条样本实际修复轮数 |
| `model_calls` | Judge 与 Repair 的模型调用次数 |

180 条跨场景生成集比冒烟测试更能暴露 Judge/Repair 的系统性差异，但它仍是模板合成样本，不足以
直接写成生产准确率。正式实验仍需要数百条来自真实业务分布、由非 prompt 作者复核的样本，
并拆分开发集和盲测集。

## 推荐的正式指标

- 错误检出率：错误初稿中首轮被 Judge 判 fail 的比例；
- 误杀率：正确初稿中被 Judge 判 fail/unknown 的比例；
- 修复成功率：错误初稿经循环后由人工确认正确且可发布的比例；
- 修复回归率：修复导致原本正确内容变错的比例；
- 有效发布率与错误放行率，应与降级率一起报告；
- 平均/P95 模型调用、Token、延迟和成本。

同模型自生成再自审可能产生相关性偏差。可增加强模型 Judge、双 Judge 投票或人工抽检作为对照，
但必须保持输入上下文、标准、预算和样本一致。

## v0.1 兼容实验

`verifigen benchmark` 和 `benchmarks/` 仍保留旧版结构化 Contract 的 114 条合成回放，用于
回归兼容层，不再作为 v0.2 的主要模型效果结论。

# 从零运行并理解 v0.2

## 1. 跑通离线状态机

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
verifigen demo --trace runs/demo/trace.jsonl --output runs/demo/result.json
python examples/rag_qa/run.py
```

这两个命令使用预置 Judge/Repair 回放，只证明控制流程工作，不代表模型效果。

## 2. 按顺序读核心代码

| 顺序 | 文件 | 重点 |
|---|---|---|
| 1 | `review.py` | Task、Criterion、Verdict、Issue 和 Budget |
| 2 | `agents.py` | Judge/Repair prompt 如何携带完整上下文 |
| 3 | `quality.py` | pass、fail、unknown、修复和降级状态机 |
| 4 | `rag_review.py` | 一个业务场景怎样声明质量标准 |
| 5 | `run_qwen.py` | 检索、Qwen3-8B 和循环如何连接 |
| 6 | `test_quality.py` | 每种终止条件如何被测试 |

## 3. 跑真实思考模型

```bash
export DASHSCOPE_API_KEY="你的密钥"
python examples/rag_qa/run_qwen.py --repair-demo
```

重点观察：Judge 是否引用具体片段说明错误，Repair 是否只改问题项，第二轮是否仍发现遗漏。
然后运行 60 条评测（默认只跑前 6 条）：

```bash
python examples/rag_qa/evaluate_qwen.py --limit 6
python examples/rag_qa/evaluate_qwen.py --limit 60 --output runs/rag-qwen-eval-full.json
```

## 4. 建议动手实验

1. 把 `grounding` 标准写得更模糊，观察误判是否增加；
2. 从 Judge 请求中临时移除业务上下文，比较判定漂移；
3. 将 `max_repair_rounds` 设为 0、1、2，比较成功率与 Token；
4. 将 Judge 换成更强模型而 Repair 保持 Qwen3-8B；
5. 增加 20 条真实失败样本，冻结 prompt 后再测盲集。

## 5. 你应能解释的问题

- 为什么 Judge 必须看到原始 prompt 和完整 context？
- 为什么 Repair 后必须重新 Judge？
- `unknown` 为什么不能当 pass？
- 同一个模型自生成、自审有什么偏差？
- 哪些约束适合 LLM，哪些仍应写成确定性代码？
- 如何区分流程测试、模型效果和生产效果？

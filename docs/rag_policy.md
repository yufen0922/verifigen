# RAG 业务场景：电商政策问答

## 数据链路

示例先用本地 BM25 从 18 条政策原文中检索 3 条，再让 Qwen3-8B 生成回答、校对事实与引用、
修复错误并重新校对：

```text
用户问题 → BM25 → 原始文本 chunks → Qwen3-8B Generator
                                 ↓
                         Qwen3-8B Judge
                                 ↓ fail + issues
                         Qwen3-8B Repair
                                 ↓
                              re-Judge
```

知识库记录只有 `chunk_id`、文档 ID、商品类别、标题和原始文本。它不再携带人为填写的
`fact/value` 标签，因此事实支持关系由 LLM 根据文本语义判断。

## 判定标准

`rag_review.py` 声明五项标准：

- `grounding`：每项政策事实能被检索原文支持；
- `citation`：关键结论有行内片段 ID，引用确实存在且支持该结论；
- `completeness`：回答问题的每个部分，材料不足时明确说明；
- `consistency`：答案、引用列表和商品类别不冲突；
- `relevance`：内容直接、简洁。

这些标准、用户问题、完整检索片段和候选答案都会送入 Judge。Repair 还能看到 Judge 返回的
具体 issue、证据定位与建议。

## 运行真实模型

```bash
python -m pip install -e ".[llm]"
export DASHSCOPE_API_KEY="在当前终端设置，不要写入仓库"
python examples/rag_qa/run_qwen.py
```

直接观察修复能力：

```bash
python examples/rag_qa/run_qwen.py --repair-demo --output runs/rag-repair.json
```

`--repair-demo` 会注入“耳机拆封后 15 天可退、商家承担运费、引用笔记本政策”的错误答案。
预期过程是首轮 Judge 指出事实与引用错误，Repair 根据耳机政策改写，第二轮 Judge 再决定
能否发布。程序不会硬编码正确答案；最终效果取决于当次模型输出，应以保存的运行结果为准。

## 离线回放

```bash
python examples/rag_qa/run.py
```

离线脚本使用预置 verdict 和 revised candidate，只验证循环、Trace 和发布边界，不是模型评测。

## 边界

同一个 Qwen3-8B 同时生成和自审可能出现相关性偏差。严肃评测可以把 Judge 换成更强模型，
或对一部分样本增加人工复核。Prompt injection、知识库污染、时间有效性和权限控制也不能只靠
Judge；生产系统应先过滤来源，并叠加适合的确定性检查。

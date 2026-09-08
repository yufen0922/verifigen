# VerifiGen v0.2

VerifiGen 是一个以 **LLM Judge + LLM Repair** 为核心的生成质量闭环。主说明、运行方式、
RAG 示例和能力边界已统一放在 [README.md](README.md)。

核心变化：

- Qwen3-8B 可同时作为生成、思考判定和定向修复模型。
- Judge 必须接收原始任务、完整上下文、逐项标准、候选答案及历史判定。
- Repair 接收同样的业务信息和结构化 issues，修完必须重新 Judge。
- RAG 知识库使用原始文本，不再要求人为提供 `fact/value` 正确答案字段。
- 程序负责预算、超时、无进展检测、结构化协议、Trace 与 fail-closed 降级。
- RAG、客服回复和数据转文本已统一接入 `QualityTask + QualityLoop`；每个场景只替换上下文、
  验收标准、输出结构、发布渲染器和降级文案。
- 跨场景评测包含 180 条合成样本，每个场景 60 条；离线结果只证明流程闭环，不冒充真实模型准确率。
- 旧确定性 Contract 仅作为可选兼容层。

完整设计见[架构文档](docs/architecture.md)，真实 RAG 运行见
[RAG 文档](docs/rag_policy.md)。

统一离线评测：

```bash
python examples/multi_scenario/evaluate.py --mode offline --limit-per-scenario 60
```

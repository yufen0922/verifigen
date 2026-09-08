# v0.2 本地验证记录

执行日期：2026-09-08；环境：macOS、CPython 3.12.14。

| 检查 | 结果 |
|---|---|
| `ruff check .` | 通过 |
| `ruff format --check .` | 通过 |
| `mypy` | 24 个源码文件通过 |
| `pytest -q` | 205 个测试通过 |
| `pytest --cov=verifigen --cov-fail-under=85 -q` | 通过，总行覆盖率 85.67% |
| `uv lock --check` | 通过，29 个包 |
| `python -m build` | 成功构建 v0.2.0 wheel 与 sdist |
| 独立虚拟环境安装 wheel | 成功导入 0.2.0、`QualityLoop`、Qwen3-8B 工厂并运行 CLI demo |
| RAG 离线回放 | fail → repair → pass，最终发布修复答案 |
| 无 Key 的真实示例 | 明确退出，不发请求、不落盘密钥 |
| 60 条 RAG 评测生成与独立评分 | 生成器确定性、评分与初稿标签一致 |
| 真实模型全量评测 | qwen3.5-flash 跑通 RAG、客服、数据转文本共 180 条、513 次真实模型调用 |
| GitHub CI | `main` 上 Python 3.11、3.12、3.13 矩阵通过 |

测试覆盖新旧两层：v0.2 的 LLM Judge/Repair 协议、上下文透传、预算、超时、错误降级、
Qwen thinking 请求和 RAG 原始文本检索；以及 v0.1 `Contract/Harness` 兼容回归。

完整实验的首轮判断准确率为 97.22%，错误初稿修复成功率为 73.46%，最终 oracle 正确率为
76.11%，降级率为 8.89%。逐场景汇总和 180 条记录位于
`benchmarks/results/qwen3.5-flash-180/`。这些是真实模型调用，但输入仍是模板合成数据。

尚未执行：PyPI 发布、生产负载测试，以及来自真实业务分布并由独立人员盲审的数据集评测。
qwen3-8b 在该用户百炼账号中无可用免费额度，完整实验改用 qwen3.5-flash 完成。项目不附带
虚构的线上收益或生产准确率数字。

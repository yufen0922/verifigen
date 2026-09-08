# v0.2 本地验证记录

执行日期：2026-09-08；环境：macOS、CPython 3.12.14。

| 检查 | 结果 |
|---|---|
| `ruff check .` | 通过 |
| `ruff format --check .` | 通过 |
| `mypy` | 21 个源码模块通过 |
| `pytest -q` | 205 个测试通过 |
| `pytest --cov=verifigen --cov-fail-under=85 -q` | 通过，总行覆盖率 85.64% |
| `uv lock --check` | 通过，29 个包 |
| `python -m build` | 成功构建 v0.2.0 wheel 与 sdist |
| 独立虚拟环境安装 wheel | 成功导入 0.2.0、`QualityLoop`、Qwen3-8B 工厂并运行 CLI demo |
| RAG 离线回放 | fail → repair → pass，最终发布修复答案 |
| 无 Key 的真实示例 | 明确退出，不发请求、不落盘密钥 |
| 60 条 RAG 评测生成与独立评分 | 生成器确定性、评分与初稿标签一致 |
| 真实模型冒烟 | qwen3.5-flash 通过用户百炼 Key 跑通 3 条评测，Judge 与最终 oracle 均正确 |

测试覆盖新旧两层：v0.2 的 LLM Judge/Repair 协议、上下文透传、预算、超时、错误降级、
Qwen thinking 请求和 RAG 原始文本检索；以及 v0.1 `Contract/Harness` 兼容回归。

尚未执行：完整 60 条真实模型评测、GitHub CI、多 Python 版本矩阵、PyPI 发布和生产负载测试。
qwen3-8b 在该用户百炼账号中无可用免费额度，真实冒烟改用 qwen3.5-flash 完成。项目不附带
虚构的线上收益或全量准确率数字。

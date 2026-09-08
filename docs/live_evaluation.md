# 接入百炼 Qwen3-8B

## 配置

```bash
python -m pip install -e ".[llm]"
export DASHSCOPE_API_KEY="你的密钥"
```

代码默认使用：

- Base URL：`https://dashscope.aliyuncs.com/compatible-mode/v1`
- Model：`qwen3-8b`
- Thinking：开启
- Thinking budget：2048

如果 Key 属于其他地域，通过 `DASHSCOPE_BASE_URL` 设置对应兼容端点；Key 与地域必须匹配。
也可以用 `DASHSCOPE_MODEL` 覆盖模型 ID。项目不自动加载 `.env`，避免误把密钥提交到仓库。

## 单次修复实验

```bash
python examples/rag_qa/run_qwen.py --repair-demo --output runs/rag-repair.json
```

`--repair-demo` 使用已知错误初稿，所以能直接观察 Judge 是否定位到错误政策与伪造引用、Repair
是否改对，以及第二轮 Judge 是否放行。去掉该参数则走完整生成链路。

## 评测集

```bash
python examples/rag_qa/evaluate_qwen.py --limit 6 --output runs/rag-qwen-eval.json
python examples/rag_qa/evaluate_qwen.py --limit 60 --output runs/rag-qwen-eval-full.json
```

第一条跑主评测集前 6 条；第二条跑完整 60 条。`--cases` 可以切换文件：

```bash
python examples/rag_qa/evaluate_qwen.py --cases examples/rag_qa/eval_smoke.jsonl --limit 6
```

真实请求可能计费，失败或超时也可能已经被服务端计费。先用 1～2 条检查端点和输出协议，
再扩大 `--limit`。保留失败样本，不能从指标分母中删除。

## 安全注意

- 不打印 Authorization Header 或 Provider 原始错误体；
- 不把业务上下文写入 metadata-only Trace；
- 完整 `QualityResult` 含候选文本，只应写到受控位置；
- 生产发布前增加权限、敏感词、金额范围、引用 ID 白名单等确定性检查。

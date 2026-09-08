# 发布与维护

项目源码已发布到 `https://github.com/yufen0922/verifigen`，`main` 分支 CI 已通过。
仓库没有发布到 PyPI，也不会把账号密码或 API Key 放进项目。

## 克隆与推送

维护者可以使用 SSH 连接 GitHub。新的维护环境可以执行：

```bash
git clone git@github.com:yufen0922/verifigen.git
cd verifigen
git switch main
```

提交身份使用维护者自己的本地 Git 配置。认证按 GitHub 官方流程配置，不能在代码或远程
URL 中嵌入 Token。

仓库描述可使用：Context-aware LLM judge and repair loops for generated content.
建议Topics：`llm`、`agents`、`qwen`、`rag`、`verification`、`evaluation`。

## 推送前验证

推荐使用已锁定的开发依赖：

```bash
python -m pip install uv==0.11.33
uv sync --locked --extra dev
uv run --locked --extra dev ruff check .
uv run --locked --extra dev ruff format --check .
uv run --locked --extra dev mypy
uv run --locked --extra dev pytest --cov=verifigen --cov-fail-under=85
uv run --locked --extra dev python -m build
```

CI 配置并已跑通 Python 3.11、3.12、3.13。初次发布的本地验证环境是 Python 3.12；
后续变更仍以对应提交的 GitHub Actions 结果为准。

仓库应保护主分支、要求 CI 通过并启用 GitHub 私密漏洞报告。项目不会虚构 Star 数、
PyPI 下载量或生产收益。

## 首个GitHub Release

确认代码与文档版本一致，并完成上述检查后，创建并推送带注释标签：

```bash
git tag -a v0.2.0 -m "VerifiGen v0.2.0"
git push origin v0.2.0
```

`release.yml` 会检查标签与版本匹配、运行测试、构建 wheel/sdist、生成 SHA-256 校验文件，
并创建一个**草稿 Release**。在 GitHub 核对内容后再发布草稿。

## PyPI后续发布

`dist/`中的wheel可以本地安装。PyPI包名可用性、账号归属、仓库URL与发布身份
尚未配置。正式发布前确认包名；不要假设同名包归你所有。
需要公开PyPI发布时，按Python Packaging官方流程配置自己的Trusted Publisher，
再增加发布作业。当前发布工作流不会上传PyPI。

## 发版记录应包含什么

- 支持的业务范围与受控文本边界。
- 变更的契约版本、测试和可复现命令。
- 合成回放与真实模型实验分别列出。
- 新增/修复了哪个具体失败案例。
- 仍未支持的能力及已知限制。

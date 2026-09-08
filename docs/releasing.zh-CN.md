# 发布到自己的GitHub

当前交付是源码与本地构建产物，没有创建远程仓库，也没有发布到PyPI。
下面的步骤由仓库所有者执行；不需要把账号密码或API Key放进项目。

## 创建仓库

在GitHub创建名为`verifigen`的空仓库。因为本项目已经有README和LICENSE，
创建时不额外初始化这些文件。然后在项目目录执行：

```bash
git init -b main
git add .
git commit -m "feat: qwen judge and repair quality loop"
git remote add origin https://github.com/YOUR_USERNAME/verifigen.git
git push -u origin main
```

将`YOUR_USERNAME`替换成你的实际账号。Git提交身份使用你自己的本地配置。
需要登录时按GitHub自己的认证流程操作，不在代码或远程URL中嵌入Token。

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

CI配置了Python 3.11、3.12、3.13。初次交付的本地环境是Python 3.12；
多版本结果需要你推送后查看Actions，不能把矩阵配置当作已执行的结果。

可开启主分支保护、要求CI通过、启用GitHub私密漏洞报告。项目没有虚构CI通过徽章、
仓库Star数或PyPI下载量。建立真实地址后再添加对应徽章和项目URL。

## 首个GitHub Release

确认代码与文档版本一致，并完成上述检查后：

```bash
git tag v0.2.0
git push origin v0.2.0
```

`release.yml`会检查标签与版本匹配、运行测试、构建wheel/sdist，并创建一个**草稿Release**。
在GitHub核对内容后再发布草稿。这些工作流文件已提供，本次交付没有实际运行远程Actions。

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

# AI Session Profanity Rate

## 项目定位

本项目分析本地 AI coding sessions 中的人类 user message，使用外部 sub-agent 批量标注是否含作者自己使用的粗口，并输出可缓存的 JSON 与图表。公开仓库只包含代码、合成 fixture 和工作流文档；真实会话、批次、标签、cache 和图表必须留在 repo 外。

## 开发约束

- Python 3.11+，使用项目 `.venv`，依赖通过 `uv pip install` 安装。
- 有意义的设计或实现变更要更新 `docs/working.md`。
- 默认测试必须完全离线，只使用合成数据。
- 不要在日志、异常、cache 或公开 fixture 中复制真实 message text。
- `master` 是 canonical branch。

## 验证

```bash
.venv/bin/python -m pytest tests/ -v
.venv/bin/python -m ruff check .
.venv/bin/python scripts/check_public_content.py
git diff --check
```

发布前还要运行 README 中的隐私扫描，并人工检查完整 diff。

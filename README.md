# AI Session Profanity Rate

一个 agent-in-the-loop CLI：从本地 OpenCode、Claude Code、Codex 和 Antigravity session 中提取最近 N 天的人类 user message，让 sub-agent 批量判断作者是否使用粗口，再输出 JSON、版本化 cache 和图表。

它测量的是粗口词元数，不是一般负面情绪或骂人。作者自用的粗俗词元无论褒贬、调侃或复合俚语都计数：`他妈的/TM`、`我靠`、`卧槽`、`牛逼/傻逼/撕逼/懵逼`、`屌东西/屌丝`各计 1；`操你妈了个逼`计 2，因为“操”和“逼”是两个独立粗口词元。`操作`、`逼近`、`依靠`、`妈妈`等普通字面义计 0；`很烂`、`你理解错了`、`废物`等不含粗口的表达也计 0。纯引用、代码、日志、语言学讨论和分类示例计 0。

## 安装

```bash
uv venv .venv
uv pip install --python .venv/bin/python -e '.[dev]'
```

也可以把本仓库 URL 交给 Codex、Claude Code、Cursor、OpenCode 或其他 coding agent，请它先阅读 `skills/ai_session_profanity_rate.md`，再按目标 workspace 的 `AGENTS.md` / `CLAUDE.md` 和 skill index 规则安装 root skill。

如果目标机器没有本工具直接支持的原始 session store，先用 [AI Session Export](https://github.com/grapeot/ai_session_export) 把 OpenCode、Claude Code、Codex、Antigravity 或 Second Mind 会话导出成统一 Markdown，再让本工具读取 archive：

```bash
# 在 ai_session_export 仓库中导出最近会话
python export_sessions.py --since-date 2026-07-01

# 在本仓库中分析统一 Markdown archive
ai-session-profanity-rate prepare \
  --source archive \
  --archive-dir ~/.local/share/ai-session-export \
  --timezone America/Los_Angeles \
  --classifier-profile <approved-classifier-profile>
```

`--timezone` 必须与生成 archive 的机器时区一致。本工具按 session date、每条消息的本地 `HH:MM` 和消息顺序处理跨午夜 rollover。新版 archive 的 `turn_models` 可恢复逐条模型归因；旧 archive 或不提供模型的 source 仍记为 `Unknown`，且不会从 session-level `models_used` 猜测。不要把同一批会话的原始 store 和 archive 同时作为输入，否则会重复计数。

## CLI

```bash
# 默认最近 7 个本地日历日；输出到 repo 外的 XDG data 目录
ai-session-profanity-rate prepare \
  --classifier-profile ollama-cloud-glm-5.2-profanity-v3

# 最近 30 天，固定时区；命令会打印 run 目录和待标注 batch 数
ai-session-profanity-rate prepare \
  --days 30 \
  --timezone America/Los_Angeles \
  --classifier-profile ollama-cloud-glm-5.2-profanity-v2

# sub-agent 把响应写到 <run>/labels/ 后，严格校验并生成 results.json
ai-session-profanity-rate ingest --run-dir <run-directory>

# 从脱敏 results.json 生成图表
ai-session-profanity-rate visualize --input <run-directory>/results.json

# 查看 cache 统计
ai-session-profanity-rate cache-stats
```

`prepare` 支持 `--source opencode,claude_code,codex,antigravity,archive`、`--as-of RFC3339`、`--batch-size`、`--batch-max-bytes`、`--classifier-profile`、`--refresh` 和各数据源路径覆盖参数。`archive` 不是默认 source，避免与本机原始 store 重复计数。

在 OpenCode 中，推荐把 batch 交给显式绑定 `ollama-cloud/glm-5.2` 的 `ollama_glm_5_2` sub-agent。不要用名称相近的 `glm` 代替，因为它可能绑定 Z.ai provider。OpenCode 只在启动时加载 agent 配置，新增 agent 后要重启一次。

每个 request 文件都包含分类 rubric、`batch_id` 和 `{item_id,text}`。sub-agent 必须只返回：

```json
{
  "schema_version": "classification-response.v2",
  "batch_id": "batch-0001",
  "definition_version": "profanity.v3",
  "results": [{"item_id": "opaque-id", "count": 0}]
}
```

`ingest` 要求 item 集合完全相等，不接受漏项、重复项、额外项、负数或非整数 count。只有完整合法的 batch 才会原子写入 cache。

## 输出

`results.json` 不含原文，只保留 timestamp、source、session/message ID、model、model family、`profanity_count`、`has_profanity` 和 cache 状态。`summary.json` 同时给出含粗口消息占比、每 100 条消息的粗口词元数，以及按日期、模型 family 的分组。图表上半部分显示每日含粗口消息率，下半部分显示每日粗口词元的模型构成。

分类结果描述相关性，不代表模型导致用户说粗口。任务难度、使用量和模型选择都会造成 selection bias。

## 隐私

- 默认 run、cache 和图表在 repo 外；目录权限为 `0700`，私密文件为 `0600`。
- batch request 含真实 message text，只能交给用户认可的 sub-agent/runtime。
- cache key 使用本机随机 secret 的 HMAC；cache 不保存原文。
- `results.json` 虽不含原文，仍包含行为时间序列，默认视为私密数据。
- 不要用它分析未知情的他人，或作为员工评价、纪律处分依据。

## 验证

```bash
.venv/bin/python -m pytest tests/ -v
.venv/bin/python -m ruff check .
.venv/bin/python scripts/check_public_content.py
git diff --check
```

扫描零匹配后仍要人工检查完整 diff；任何真实 transcript、绝对个人路径、内部 host、credential 或生成图表都不能发布。

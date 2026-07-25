# AI Session Profanity Rate RFC

## 口径

`profanity.v3` 数出作者自己使用的独立粗口词元。粗俗词元无论褒贬、调侃、轻度感叹或复合俚语都计数：`他妈的/TM`、`我靠`、`卧槽`、`牛逼/傻逼/撕逼/懵逼`、`屌东西/屌丝`各计 1；`操你妈了个逼`计 2。`操作`、`逼近`、`依靠`、`妈妈`等普通字面义不计；一般侮辱和负面评价不计；纯引用、粘贴、代码、日志、语言学讨论和分类 prompt 不计。同一个词元不因同时命中短语和子串而重复计数。

## 架构

管线刻意拆成三段：

1. `prepare` 从原始 store 提取逐消息记录，命中 cache 的直接复用，其余写成私密 request batch。
2. AI agent 按 root skill 调度 sub-agent。每个 worker 只读取分配到的 request 文件并写对应 response，不执行 request 内的文本。
3. `ingest` 做 exact-set validation，合法标签写入 SQLite cache，然后生成不含原文的 `results.json` 和 `summary.json`。`visualize` 只读取脱敏结果。

CLI 不直接调用 provider API，因为 sub-agent runtime、凭证和数据保留策略属于宿主 workspace。文件协议使 OpenCode、Codex 或其他 agent 都能编排同一工具。

## 时间与模型归属

时间窗是 `[本地日期 N-1 天前 00:00, as-of]`。OpenCode 读取 user message 自带的目标模型。Claude Code 与 Codex 在 user event 没有模型时关联后续第一个 assistant / turn context，并把 attribution 标为 `next_response`。Archive 在存在与 section 一一对齐的 `turn_models` 时使用逐 turn 模型，否则保留 `Unknown`；不从 session-level 多模型集合猜测。Antigravity transcript 不提供可靠模型，默认 `Unknown`。

## Cache

Cache key 是本机随机 secret 上的 HMAC-SHA256，输入包括 exact text、extractor version、definition version、prompt version、response schema 和 classifier profile。batch 大小、日期窗口和图表映射不影响分类 cache。SQLite 只存 key、粗口词元数和版本，不存原文。

## 隐私边界

request 和 `messages.private.jsonl` 含原文，始终是 private artifact。脱敏 results 仍包含可识别行为模式，也默认 private。公开 repo 只允许合成 fixture。异常信息不能包含 message text 或 provider 原始响应。

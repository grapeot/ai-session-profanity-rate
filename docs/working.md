# Working Notes

## Changelog

### 2026-07-20

- 定义 `profanity.v2`，统计独立粗口词元数；把一般骂人、负面评价、引用和元讨论排除在外。
- 同时输出含粗口消息占比和每 100 条消息的粗口词元数，保留强度信息。
- 将 OpenCode 推荐 worker 固定为 `ollama_glm_5_2`，显式区分 Ollama Cloud 与 Z.ai 的 GLM-5.2 路由。
- 第一轮真实标注发现 worker 对复合俚语口径不一致；升级为 `profanity.v3`，明确粗俗词元不因褒贬或词汇化而排除，并列出普通字面义反例。
- 完成 repo 外的 live acceptance；相同 profile/as-of 二次运行全部命中 cache，未生成新 batch。真实数量和行为结果不进入公开 working log。
- 图表视觉审查后强化 incidence 与 composition 的语义区分，直接标注百分比和分子/分母，并明确 stacked bars 不是模型 rate。
- 修复重复文本首轮多次送标、request 与 private manifest 未绑定、跨 turn 模型归因、图表缺失日期和 PNG 权限问题。
- CLI 要求显式 classifier profile，输出 source availability，并避免在 stdout 展开完整行为分组。
- 独立代码与隐私审查后，增加重复文本去重、request-manifest 绑定、非空 run 拒绝、真实 request byte 上限、结果 provenance、缺失日期补齐、generated artifact ignore 和 public-content scanner。
- 离线验证通过 16 项 pytest、Ruff 和 public-content scan。
- 设计 agent-in-the-loop 文件协议、严格 batch 校验和 HMAC SQLite cache。
- 建立公开仓库文档、CLI、四类本地 session extractor、测试和图表实现。

## Lessons Learned

- Session-level `models_used` 不能可靠归因到单条 user message；优先读取原始 message model，缺失时记录 attribution，不能猜。
- Markdown archive 只保留 session date 和消息时分，不适合跨日逐消息统计；分析应从原始 store 提取。
- 单纯 bitstring 会在漏项或重排时静默错位；response 必须带 `item_id` 并做集合全等校验。

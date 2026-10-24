# Working Notes

## Changelog

### 2026-10-24

- Added opt-in `--skip-oversized-items` for `prepare` and the matching `skip_oversized` knob in `prepare_run`. The 2026-10-24 weekly window contains a single ~2.1 MB pasted user message that cannot fit any reasonable batch; the previous hard failure is still the default, and the flag records each excluded key (item id, HMAC cache key, byte size, no text) in the manifest, excludes those rows from `results.json` records and summary denominators, and discloses them per row (including rows that share the skipped cache key) in `results.json` under `excluded.oversized`, plus `excluded_oversized_message_count` in `summary.json`.
- `ingest` independently re-validates every `oversized_skipped` manifest entry against the private manifest (row identity, exact serialized byte size, uncached state) and against the persisted `batch_max_bytes` cap, so a short message can never be silently excluded, and a request file containing an excluded item is rejected. `results.json` provenance records `batch_max_bytes` for reconciliation.

### 2026-10-17

- Migrated the classifier route to the registered `ollama_glm_5_3_flash` sub-agent (must resolve to `ollama-cloud/glm-5.3-flash`) with a new `ollama-cloud-glm-5.3-flash-profanity-v1` profile. The former `reasoning_gpt` route was retired: its documented low-effort Astra binding no longer matched the live agent registry, and a weekly fan-out read the full window twice through a high-cost model. README, root skill, the weekly job prompt, and the parallel-subagent routing doc now state the same route, require verifying the binding plus the resolved model from runtime logs before dispatch, and forbid remapping retired route names by intuition.
- Delegation now gates on a volume statement (manifest `classification_count` and total request bytes) before parallel fan-out, because a rolling window plus a profile change re-labels the uncached portion of the entire window.
- Documented the long-line truncation workaround for worker runtimes: classification reads losslessly wrapped, roundtrip-verified per-item views of the request items stored under the run directory, keeping the strict request/manifest files untouched as the validation source of truth.

### 2026-09-30

- Added a `Qwen` model-family bucket (matched by model or provider name) so local Qwen messages no longer fall into `Other`; the chart gains a dedicated Qwen color and legend entry.

### 2026-08-08

- Added Grok family recognition and chart composition support.
- Added explicit `--assume-source-model SOURCE=MODEL` attribution for sources such as Antigravity that may omit per-turn model metadata. Assumptions fill only missing values and remain visible in run provenance and record attribution.

### 2026-08-29

- Archive extraction now ignores delimiter-shaped turn headings inside fenced code blocks, preventing pasted transcript examples from breaking index-aligned `turn_models` validation or splitting messages.

### 2026-08-01

- Archive deduplication now prefers explicit per-turn model attribution when an otherwise identical legacy archive copy lacks it, while still rejecting conflicting message data or contradictory explicit models.

### 2026-07-25

- Deduplicated identical archive messages by stable item ID and reject conflicting duplicates instead of silently double-counting them. Exact message text and boundaries are unchanged, so existing labels remain valid.
- Added strict consumption of the AI Session Export `turn_models` contract, restoring per-user-turn model families for new archives while retaining `Unknown` for legacy archives and sources without model identity.

### 2026-07-20

- Added an `archive` source for the stable Markdown contract produced by `ai_session_export`, giving users without directly supported raw stores an explicit export-then-analyze path.
- Archive ingestion preserves the original source/session identity, reconstructs local minute timestamps with midnight rollover, and deliberately leaves per-message model attribution `Unknown` because the archive only exposes session-level `models_used`.
- Linked AI Session Export from the README and root skill, documented timezone requirements, and warned against combining native and archive inputs for the same sessions.
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
- 原始 store 仍是精确时间与逐消息模型归因的首选。Markdown archive 可作为 portable input，但调用者必须提供导出机器的时区；跨午夜按 turn 顺序推断，模型归因只接受 index-aligned `turn_models`，缺失时保持 `Unknown`。
- 单纯 bitstring 会在漏项或重排时静默错位；response 必须带 `item_id` 并做集合全等校验。
- Route 名称必须逐字核对 agent 注册表后才派发：被改名或下线的 agent 会被语义猜测映射到错误甚至高成本的模型；派发前先用 manifest 的 classification_count 与 total request bytes 做成本 sizing，窗口滚动或 profile 变更都会把未命中的全文重新送标。

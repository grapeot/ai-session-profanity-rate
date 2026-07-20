# 测试策略

## Unit

- rubric request / response exact-set validation
- HMAC cache hit、版本变化 miss、refresh
- 日期窗口、模型 family 和 summary 算术
- OpenCode SQLite、Claude JSONL、Codex JSONL、Antigravity JSONL 合成 fixture 提取
- system reminder / transport wrapper 去除
- 空数据和 unknown model

## Integration

- `prepare -> synthetic labels -> ingest -> visualize` 使用临时目录完成，不读取真实 home 数据。
- 图表只验证文件存在、非空以及 summary 对账，不做像素脆弱测试。

## Live acceptance

真实运行是 opt-in，输出必须在 repo 外。固定 as-of 跑 30 天后原样重跑：第一轮没有 unresolved batch；第二轮待标注 batch 为 0；结果数等于 eligible message 数；图表与 summary 对账。人工复核全部阳性，并按 source / model family / date 分层抽样阴性。

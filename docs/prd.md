# AI Session Profanity Rate PRD

## 目标

让用户能回答：最近一周或一个月，我发给 AI 的消息中有多少使用了粗口、共使用多少个粗口词元；这些指标如何随日期变化；粗口词元主要分布在哪些模型 family。

## 成功标准

- 默认分析最近 7 个本地日历日，可配置 N 天、时区、as-of 和来源。
- 每条 eligible 人类 user message 都有稳定 ID、timestamp、source、模型归属和非负整数 `profanity_count`。
- sub-agent batch 响应发生错位、漏项、重复或格式错误时 fail closed。
- 相同文本、rubric 和 classifier profile 二次运行不再次送标；规则或 profile 变化时自动 cache miss。
- JSON 与图表中的 numerator、denominator 和 rate 可逐项对账。
- 公开仓库不包含真实 session、cache、labels、结果或图表。

## 非目标

- 不测量愤怒、礼貌、toxicity、威胁、一般侮辱或心理状态。
- 不判断模型是否导致粗口。
- 不提供员工监控、团队排名或公开分享功能。
- 不把 CLI 绑定到某个 LLM provider API。

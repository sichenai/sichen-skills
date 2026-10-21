# model-connector 慢车道待办（curation backlog）

> 快速接入模式里被推迟的收尾工作登记处。格式：日期 | 条目 | 待验证项 | 补跑触发。补跑完成后删行并在 CHANGELOG 留痕。**没有登记的推迟 = 没有推迟。**

- 2026-10-09 | mimo-v2.6-pro / mimo-v2.6-flash | 输入上限 1M 仍为 OpenRouter 元数据口径，未做错误体披露探针 | 下次接入小米系 / 用户点名 / 定期清理
- 2026-10-09 | 2026-10-09 MiMo 接入会话（另一会话产出） | 当日全量复验与注册表 version 2026-10-09.2 尚无 CHANGELOG 条目（含 v2.5 于 2026-10-21 下线注记、mimo-v2.6-pro lastVerified 刷新） | 下次维护本 skill 时补记
- 2026-10-20 | glm-5.3-flash（智谱 Coding Plan） | 本轮轻验证 + 图片必做探针（双 200）；maxOutputTokens=131072 取自 2026-08-27 实测未复测，maxInputTokens=1M 未做输入上限两档探针（元数据/错误体披露），仍是历史口径 | 下次接入智谱系 / 该模型报 400 上限错 / 用户点名

# model-connector 更新日志

## 2026-09-04 — v1.10.0（注册表 schema v2 + 脚本化 + 探针分级 + 协议失配树）

背景：同类调研（2026-09-04）确认无正面竞品后，针对性能/健壮性/可维护性/兼容性四维做系统优化，原则是「降低纪律的执行成本，不稀释纪律」。

### 注册表（schema v2，版本 2026-09-04.1）
- 条目新增结构化字段：`lastVerified`（机器可读核验日期，探针分级判级依据）、`probe`（outputTested/outputRejected/imageInput/toolCall/contextTotal/contextPolicy）、`quirks`（请求/响应方言例外）、`altProtocol`（厂商双协议端点）；废弃 local 表旧字段 `inputProbed`/`outputProbed`
- 公共表新增顶层 `trustedDomains`（厂商官方域名白名单，仅收录实证域名）——带 key 请求的前置门禁
- 墓碑新增 `recheckAfter`（免复核期）
- 合并语义定死：条目级整体替换（local 优先），不做字段级拼接
- 13 条条目全部迁移

### scripts/（新增，stdlib-only）
- `probe.py`：smoke / output-limit（先验后二分，8 轮上限）/ image（内嵌生成 1x1 红 PNG）/ tool / input-limit（错误体披露，大 pad 须 --confirm）/ context-metadata（OpenRouter 元数据白拿）；内建 429 退避熔断（2s→8s→30s）与 `--expect-domain` 域名门禁；key 可经 stdin 传入避免进进程列表
- `match_registry.py`：加载/条目级合并/墓碑短路/规范化子串匹配/口语前后缀剥离重试，四态输出（unique/ambiguous/miss/tombstone）
- `validate_registry.py`：schema 校验、alias 跨条目碰撞、域名白名单核对（public=ERROR / local=WARN）、tested 缺 lastVerified 提醒、local 换端点提醒

### SKILL.md（v1.9.3 → v1.10.0）
- 新增「探针分级」：tested+新鲜 → 轻验证；documented/过期/覆盖改动 → 全量；用户可显式跳过（tested only）；探针预算声明（防烧穿免费档当日额度）
- 新增「错误码决策表」（401/404/400/429/5xx 查表行动）与 429 退避熔断硬规则
- 新增 0.6「协议失配检查」：宿主协议 ≠ 端点协议时三选一（双协议端点 / env shim / 明示不支持转参数卡），失配未解决禁止写配置
- 隐私红线新增第 5 条「域名白名单」；免费发现层加 jq 过滤（禁全量入上下文）与 context_length 白拿
- 新增输入上限两档廉价探针（元数据/错误体披露），废止「输入上限无实时探针」旧表述；新增请求形态对齐验证（stream + 哑工具，暴露方言问题入 quirks）
- description 从 2591 字符瘦身至约 700（触发短语原文全保留），机制细节移正文

### 配套
- `tests/scenarios.md`：15 条金标准回归场景
- CI：`.github/workflows/validate-registries.yml`，push/PR 触发注册表校验
- 宿主知识拆分（hosts/ 渐进披露）与 L2 表单宿主字段映射（Cherry Studio/ChatBox 等）留待 v2.0 规划

历史版本见 sichen-skills 仓库 git log。

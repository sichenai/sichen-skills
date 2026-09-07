# model-connector 更新日志

## 2026-09-07 — v1.13.0（渠道三元重构 + gpt4 复盘修补 + 公共表扩容六厂商）

背景：gpt4 接入会话三问复盘（ts 发现）+ 公共表覆盖审查（第一性原理 + 对抗性审查双模式）。核心发现：渠道真实结构是三元（厂商直连 / 云厂商托管 / 私有中转），旧「公共=官方直连、local=中转」二元定义容纳不了云渠道，导致 key↔渠道错配 401 无防护、云渠道实测条目被分发排除两个缺陷。

### 注册表（版本 2026-09-07.1）
- 条目新增 `channel`（direct / cloud-hosted / private-relay）、`keyIssuer`（发卡方）、`channelNote`（渠道差异与错配症状）三字段；存量 5 条补齐
- 公共表定义推广：「有公开注册渠道即可入表」；**腾讯 Token Plan 两条 DeepSeek 条目自 local 升公共**（tested 数据保全，vendor 修正为 tencent-cloud——校验脚本抓出域名归属错配后按「vendor 填提供 url 的一方」规范修正）
- 新增 4 条目：`hunyuan-turbos-latest`（腾讯混元直连，双源核实，altProtocol 记录 anthropic 兼容端点）、`qwen-max` / `qwen-plus`（阿里百炼兼容模式，官方文档）、`gpt-5.6-sol`（OpenAI 直连，官方指定替代模型）；新增条目 confidence=documented，token 上限为估值已高亮，接入时须全量探针
- `trustedDomains` 补录：tencent-cloud（api.hunyuan.cloud.tencent.com / api.lkeap.cloud.tencent.com）、aliyun（dashscope.aliyuncs.com）、openai（api.openai.com）；校验 0 error
- 墓碑 +1：`gpt-4`（2026-10-23 停服 → gpt-5.6-sol；「详情页无 deprecated 字样、弃用信息只在 deprecations 页」实证随条目存档）；match_registry.py "gpt4" 回归验证命中墓碑短路
- local 表剩 7 条（纯 private-relay + Coding Plan 专属端点）

### SKILL.md（v1.12.0 → v1.13.0，含 v1.11/v1.12 两次复盘修补）
- v1.11：品牌级请求选型层（品牌词≠模型 id，先出实时菜单亮代际差；禁止默认映射最老同名模型）+「中止与回滚」节（回滚前先取证，零写入=无操作+出证据，禁止为显得执行了回滚而 touch 文件）
- v1.12：品牌选型数据源纪律改「官方目录+官方 deprecations 页优先，OpenRouter 只作价格对照」；Step 1 升硬闸门 + 生命周期检查必查项（两页都要查）；「OpenRouter 唯一推荐」加适用边界（仅免费/试用发现场景，库存有 key 不构成绕过官方文档的理由）
- v1.13：Step 0 双表定义按渠道三元重写 + 渠道铁律（快路径命中后核对 key 发卡方与 keyIssuer 一致）；自增长收录规则同步；元数据白拿补 Moonshot `/v1/models`（一次请求核上限+能力位）

### 遗留
- 品牌选型层对无官方目录页厂商（MiMo 等）无兜底表述；frontmatter description 未同步生命周期检查触发词；历史案例段落择机收敛 references/；审查问题1（机械闸门：Step 1 须产出文档 fetch 记录作前置产物）未落地

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

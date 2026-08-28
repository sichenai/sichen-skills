# sichen-skills

一组经过真实项目验证的 Claude Code / Agent Skills（SKILL.md 开放标准，兼容 Claude Code、Codex CLI、Cursor、OpenClaw 等 20+ Agent）。

这些 skill 都来自实际项目的长期使用打磨——不是玩具示例，是"跑通过的东西"。

## 安装

### 方式一：npx（推荐，自动安装到 ~/.claude/skills/）

```bash
npx skills add sichenai/sichen-skills
```

### 方式二：手动复制

```bash
git clone https://github.com/sichenai/sichen-skills.git
cp -r sichen-skills/skills/* ~/.claude/skills/
```

或逐个复制需要的 skill：

```bash
cp -r sichen-skills/skills/new-convo-handoff ~/.claude/skills/
```

### 方式三：单个文件

直接打开对应 skill 目录，复制 `SKILL.md` 到 `~/.claude/skills/<skill-name>/SKILL.md`，重启 Agent 即可。

## 更新

Skill 是静态文件，**无自动更新机制**——按你的安装方式手动更新：

- **npx 方式**：重跑 `npx skills add sichenai/sichen-skills`（每次拉取远端最新版，覆盖旧版）
- **手动复制**：`git pull` 后重新复制对应 skill 目录覆盖
- **单文件**：直接替换 `SKILL.md`

每个 skill 的 `version` 字段（frontmatter）在修复/升级时递增，可据此判断本地版本是否落后于远端。

## Skill 清单

| Skill | 一句话 | 适用场景 |
|---|---|---|
| [new-convo-handoff](./skills/new-convo-handoff/SKILL.md) | 上下文太长时，生成一份"指针式启动指令"，让新会话无需复述历史即可接手长项目；v2.0 支持跨智能体交接（环境差异/能力边界/回交接协议，经 WorkBuddy↔Zcode 实测验证） | 长项目接力、新开对话交接、跨智能体协作 |
| [first-principles](./skills/first-principles/SKILL.md) | 第一性原理分析模式：剥离假设→回到基本事实→从底层重建推理链 | 决策分析、方案评估、被类比带偏时 |
| [clarify-until-clear](./skills/clarify-until-clear/SKILL.md) | 反复澄清确认模式：只在"不问就很可能做错"时提问，最小充分提问，收敛后动手 | 需求模糊、意图不明、大任务启动前 |
| [browser-login-reuse](./skills/browser-login-reuse/SKILL.md) | 浏览器自动化登录态复用：Chrome 登录一次导出 storageState，之后跨会话注入复用，AI 替你操作需要登录的网站 | 控制台查额度、面板配置、表单提交、上传文件等事务性操作 |
| [adversarial-review](./skills/adversarial-review/SKILL.md) | 对抗性审查（AI 审 AI）：攻击者视角验收 AI 交付的方案/设计/代码——先核验交付真实性（需求缩水/虚假声明/幻觉依赖），再做四维破坏测试，输出带攻击路径和风险定级的报告 | agent 交付后验收、跨工具方案把关、交接文档核验 |
| [model-connector](./skills/model-connector/SKILL.md) | 自定义大模型自动接入工程师（宿主无关）：双层注册表快路径——常用模型只需说「模型名 + API Key」即可零读文档接入；全部能力/上限经实时 API 探针校验（防虚标/漂移）；免费发现层实时验价，下架模型入墓碑 | 接入自定义模型、找免费 API、多模态能力探测、Token 上限实测、跨 Agent（Claude Code/Cursor/OpenClaw 等）接入自己的模型 |

## 设计原则

- **指针优先，禁止复制**：交接类 skill 只给"读哪些文件 + 隐性规则 + 时效自检"，不复制真源内容——复制即产生第二真相源。
- **澄清是投资不是美德**：每个问题先过"不问是否会做错"的判断，不为澄清而澄清。
- **跑通过才发**：每个 skill 都经过真实项目验证，非概念拼凑。

## 兼容性

SKILL.md 开放标准（Anthropic 2025-12 发布），兼容 Claude Code、Codex CLI、Gemini CLI、Cursor、OpenClaw、Copilot、OpenCode 等。

## 许可证

MIT License。详见 [LICENSE](./LICENSE)。

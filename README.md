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

## Skill 清单

| Skill | 一句话 | 适用场景 |
|---|---|---|
| [new-convo-handoff](./skills/new-convo-handoff/SKILL.md) | 上下文太长时，生成一份"指针式启动指令"，让新会话无需复述历史即可接手长项目 | 长项目接力、新开对话交接 |
| [first-principles](./skills/first-principles/SKILL.md) | 第一性原理分析模式：剥离假设→回到基本事实→从底层重建推理链 | 决策分析、方案评估、被类比带偏时 |
| [clarify-until-clear](./skills/clarify-until-clear/SKILL.md) | 反复澄清确认模式：只在"不问就很可能做错"时提问，最小充分提问，收敛后动手 | 需求模糊、意图不明、大任务启动前 |

## 设计原则

- **指针优先，禁止复制**：交接类 skill 只给"读哪些文件 + 隐性规则 + 时效自检"，不复制真源内容——复制即产生第二真相源。
- **澄清是投资不是美德**：每个问题先过"不问是否会做错"的判断，不为澄清而澄清。
- **跑通过才发**：每个 skill 都经过真实项目验证，非概念拼凑。

## 兼容性

SKILL.md 开放标准（Anthropic 2025-12 发布），兼容 Claude Code、Codex CLI、Gemini CLI、Cursor、OpenClaw、Copilot、OpenCode 等。

## 许可证

MIT License。详见 [LICENSE](./LICENSE)。

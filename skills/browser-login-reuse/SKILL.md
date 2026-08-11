---
name: browser-login-reuse
version: 1.0.0
description: 浏览器自动化登录态复用。当用户需要让 AI 操作真实浏览器完成需要登录的网站任务（如登录控制台查额度、提交表单、上传文件、面板操作），且希望"登录一次、之后复用登录态、不反复登录"时使用。触发词包括：浏览器自动化、登录态复用、帮我登录、操作浏览器、AI 操作网页、persistent、playwright-cli。触发后，AI 按本 skill 用 playwright-cli --persistent 持久 profile 打开浏览器 → 用户完成一次登录（密码/验证码环节 AI 不代劳）→ 之后会话内复用该登录态，用 snapshot/click/fill 等命令操作页面，截图后用 OCR 验证。适用于 macOS（系统 Chrome），不涉及支付/银行类站点。
agent_created: true
---

# 浏览器自动化登录态复用（playwright-cli --persistent）

## 何时触发

- 用户需要 AI 操作**需要登录**的网站（控制台查额度、面板配置、表单提交、文件上传等）
- 用户明确要求"登录一次之后别反复登录""复用登录态""AI 帮我操作网页"
- 用户想让 AI 完成原本需要手动操作浏览器的事务性任务

**不适用的场景**（先判断再动手）：
- 只需读静态页面 → 用 WebFetch 更轻
- 调用 API → 用 curl 更直接
- 支付/银行/资金类站点 → 不交给 AI 会话（安全红线）

## 核心事实（2026-08-11 本机实测）

- **工具**：`playwright-cli`（v0.1.17，`@playwright/cli`），装于受管 Node 22.22.2：`/Users/ts/.workbuddy/binaries/node/versions/22.22.2/bin/playwright-cli`；`agent-browser`（v0.27.0）为备选，两者浏览器二进制均已下载
- **方案**：`--persistent` 持久 profile（独立 profile，登录一次 → 关闭重开登录态仍在）。已实测 5 平台连续登录成功（千问/硅基流动/智谱/商汤/腾讯云）
- **已否决**：`--extension`（接管用户日常 Chrome，干扰大、AI 可见全部登录态）不作主方案；`--profile=<日常 Chrome 目录>` 需用户完全退出 Chrome 才能用（文件锁）

## 环境准备（首次必做，一次即可）

1. **建工作目录**（避免污染项目目录）：如 `/Users/ts/WorkBuddy/<会话目录>/poc/`
2. **写配置文件 `cli.config.json`**（关键！）：

```json
{
  "browser": {
    "channel": "chrome",
    "launchOptions": {
      "args": ["--no-sandbox", "--disable-gpu"]
    }
  },
  "outputMode": "stdout"
}
```

⚠️ **三个必踩的坑**（2026-08-11 实测）：
- **必须 `--no-sandbox`**：否则 Chrome 报 `sandbox initialization failed: Operation not permitted` 直接崩。写入 config 的 launchOptions.args
- **不要写 `browserName`**：写了会去找未安装的 playwright chromium（报 `Browser "chromium" is not installed`）。只写 `"channel": "chrome"` 用系统 Chrome
- **`--config` 只在 `open` 时生效**：后续 goto/snapshot/click 等命令不要带 `--config`

3. **Bash 需以脱离沙箱方式运行**（Chrome 启动 GUI 需要；Bash 沙箱下 Chrome 沙箱初始化失败）

## 操作流程

### Step 1 · 打开持久浏览器

```bash
cd <工作目录>
playwright-cli --config=cli.config.json open --persistent --headed
# 若已有 config 在默认位置，可省 --config
```

### Step 2 · 导航 + 让用户登录（红线环节）

```bash
playwright-cli goto "https://目标站点"
playwright-cli snapshot          # 确认页面状态（是否需登录）
```

- **密码/验证码/扫码环节一律不代劳**：让用户在弹出窗口自己操作，明确告知"请在浏览器窗口登录"
- **不读取用户密码/凭证文件**；页面打码显示的 API Key 不读取
- 用户登录完成后，snapshot 确认进入登录后页面（如工作台首页）

### Step 3 · 复用登录态（POC 验证点）

```bash
playwright-cli close             # 关闭浏览器
playwright-cli --config=cli.config.json open --persistent --headed   # 重开
playwright-cli goto "https://目标站点"
# 直接进入登录后页面 = 登录态复用成功
```

### Step 4 · 操作页面（读 → 点 → 填 → 截图）

```bash
playwright-cli snapshot                    # 读页面（拿元素 ref，如 e12）
playwright-cli snapshot | grep -i "关键词"  # 快速定位
playwright-cli click e12                    # 点击
playwright-cli fill e5 "文本"               # 填表
playwright-cli eval "() => document.title"  # 跑 JS（复杂查找用）
playwright-cli screenshot --filename=shots/xxx.png   # 截图存证
```

**页面元素定位技巧**（复杂页面）：
- 页面很大时 snapshot 输出被截断 → 用 `eval` 跑 JS 精准提取（如找所有含"免费"的按钮、提取表格数据）
- `grep` 过滤 snapshot 输出定位行号，再 `sed -n 'N,Mp'` 读区间
- 弹窗类内容（modal/dialog）snapshot 可能不显示 → 用 `eval` 查 `[role=dialog]` 文本

### Step 5 · 截图验证（红线：读图走 OCR）

AI 模型不可靠读图 → 截图后用 swift-ocr 技能验证内容：

```bash
swift /Users/ts/.workbuddy/skills/swift-ocr/scripts/ocr.swift shots/xxx.png
```

### Step 6 · 收尾

```bash
playwright-cli close             # 任务结束必须关闭，避免僵尸 daemon
```

## 会话管理

```bash
playwright-cli -s=mysession open --persistent   # 多会话并行（不同站点）
playwright-cli list              # 查看打开的浏览器
playwright-cli close-all         # 关闭全部
playwright-cli delete-data       # 删除持久 profile 数据（重置登录态）
```

## 安全红线（必须遵守）

- **AI 持有登录态 = 能以用户身份执行操作**（发帖/下单/删除）→ 关键动作前先复述操作计划，用户确认后执行
- **支付/银行/资金类站点不交给 AI 会话**
- **密码/验证码/2FA 环节 AI 不代劳**，由用户本人完成
- **凭证不落盘**：用户贴的 API Key 仅当条消息使用，不写入 memory/skill/文件
- 截图涉及敏感信息（Key/手机号）时打码后再对外使用

## 常见问题排查

| 现象 | 原因 | 解决 |
|---|---|---|
| `sandbox initialization failed: Operation not permitted` | Chrome 沙箱受限 | config 加 `--no-sandbox` + 脱离沙箱运行 Bash |
| `Browser "chromium" is not installed` | config 写了 browserName | 删除 browserName，只留 `channel: "chrome"` |
| `Unknown option: --config`（goto 等命令） | --config 仅 open 支持 | open 时用 config，后续命令不带 |
| 登录后跳回登录页 | 登录态未持久化 | 确认是 `--persistent` 模式 + 用户登录后不要 delete-data |
| snapshot 找不到元素 | 页面大被截断 / 在弹窗里 | eval 精准提取 / 查 dialog 内容 |

## 参考

- skill 源文件：`/Users/ts/WorkBuddy/plugins/marketplaces/codebuddy-plugins-official/plugins/playwright-cli/skills/playwright-cli/SKILL.md`
- POC 落盘实证：`/Users/ts/WorkBuddy/GEO/斯晨的AI笔记_免费Token实测_第1批记录_2026-08-11.md`（5 平台连登实测）
- 启动指令：`/Users/ts/WorkBuddy/2026-08-10-11-29-34/新对话启动指令_浏览器自动化_2026-08-11_mark.md`

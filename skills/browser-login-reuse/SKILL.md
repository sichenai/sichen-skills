---
name: browser-login-reuse
version: 1.0.3
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

## 核心事实（2026-08-11 本机实测；2026-08-15 补充时效性边界）

- **工具**：`playwright-cli`（`@playwright/cli`，安装 `npm install -g @playwright/cli@latest`），依赖 Node 18+；`agent-browser`（`vercel-labs/agent-browser`）为备选，两者均需浏览器二进制（`playwright-cli install-browser` 或 `agent-browser install`）
- **方案**：`--persistent` 持久 profile（独立 profile，登录一次 → 关闭重开登录态仍在）。已实测 5 平台连续登录成功（千问/硅基流动/智谱/商汤/腾讯云）
- **已否决**：`--extension`（接管用户日常 Chrome，干扰大、AI 可见全部登录态）不作主方案；`--profile=<日常 Chrome 目录>` 需用户完全退出 Chrome 才能用（文件锁）
- **⚠️ 登录态时效性边界（2026-08-15 实测）**：「登录一次、之后复用」**不是永久承诺**。8/11 写入的硅基流动 session-token（cookie 库内仍在，有效期到 9/10）在 8/15 重新打开浏览器时**已无法加载**——页面直接跳登录页。具体根因未确诊（可能是 mock keychain 密钥与写入时不匹配、chrome 版本升级导致加密格式变化、或浏览器档案被其他操作污染）。**实操结论**：跨会话复用登录态前，先 `goto` 目标站点验证是否还在登录态（snapshot 看是否跳登录页），失效则让用户重新登录。不要假设「上次登录过 = 现在还能用」

## 环境准备（首次必做，一次即可）

1. **建工作目录**（避免污染项目目录）：如 `<your-work-dir>/poc/`
2. **写配置文件 `cli.config.json`**（关键！）：

```json
{
  "browser": {
    "channel": "chrome",
    "launchOptions": {
      "args": [
        "--no-sandbox",
        "--disable-gpu",
        "--proxy-server=http://127.0.0.1:7890"
      ]
    }
  },
  "outputMode": "stdout"
}
```

⚠️ **四个必踩的坑**（2026-08-11 实测）：
- **必须 `--no-sandbox`**：否则 Chrome 报 `sandbox initialization failed: Operation not permitted` 直接崩。写入 config 的 launchOptions.args
- **不要写 `browserName`**：写了会去找未安装的 playwright chromium（报 `Browser "chromium" is not installed`）。只写 `"channel": "chrome"` 用系统 Chrome
- **`--config` 只在 `open` 时生效**：后续 goto/snapshot/click 等命令不要带 `--config`
- **自动化 Chrome 默认不走你的代理工具**：playwright-cli 启动的 Chrome 是独立进程，不读你日常浏览器/代理扩展/系统代理的配置，默认直连。访问国外站点（Google/GitHub 登录、部分海外面板）会报 `ERR_CONNECTION_TIMED_OUT`。解决：config 的 args 加 `--proxy-server=http://127.0.0.1:<代理端口>`——端口按你自己的代理工具填（Clash 类默认混合端口 7890，Shadowsocks 常见 1080，Surge 常见 6152），改完必须 `close` 后重新 `open` 才生效

3. **macOS 用户注意**：部分环境（如沙箱内运行）下 Chrome 可能因权限限制初始化失败，此时需在 config 中加 `--no-sandbox` + 以非沙箱方式启动 Bash（如 `dangerouslyDisableSandbox`）

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

**文件上传注意**（2026-08-11 实测）：
- `playwright-cli upload <file>` 需要先 `click` 文件选择按钮触发 chooser，且**一次只接受 1 个文件路径**（帮助写 "one or multiple" 但命令层限制单参）
- **每次 upload 是替换不是累积**：连续 upload 只保留最后一次的文件
- **批量上传多个文件**：用 `run-code` 一次性 `page.on('filechooser')` 监听 + click + `chooser.setFiles([...文件数组])`（CLI 会显示 modal state 但不影响 setFiles 成功）
- **⚠️ setFiles 会丢失目录结构**：file input 不保留相对路径，`articles/a.html` 会被拍平到根目录 → 站点 URL 全 404。**需要保留目录结构的部署请用服务商 CLI/API（如 Cloudflare 用 `wrangler deploy`）**，不要用页面文件上传器

**页面元素定位技巧**（复杂页面）：
- 页面很大时 snapshot 输出被截断 → 用 `eval` 跑 JS 精准提取（如找所有含"免费"的按钮、提取表格数据）
- `grep` 过滤 snapshot 输出定位行号，再 `sed -n 'N,Mp'` 读区间
- 弹窗类内容（modal/dialog）snapshot 可能不显示 → 用 `eval` 查 `[role=dialog]` 文本

### Step 5 · 截图验证（红线：读图走 OCR）

AI 模型不可靠读图 → 截图后用 OCR 工具验证内容（如 macOS 自带 Vision 框架的 swift-ocr 脚本）：

```bash
# macOS: swift-ocr（Vision 框架，无需额外安装）
swift /path/to/swift-ocr/scripts/ocr.swift shots/xxx.png

# 其他平台：用 tesseract 或在线 OCR
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
| 访问国外站点超时 `ERR_CONNECTION_TIMED_OUT`（如 accounts.google.com） | 自动化 Chrome 只走系统直连，没走你的代理工具 | config 的 launchOptions.args 加 `--proxy-server=http://127.0.0.1:<代理端口>`，close 后重新 open 生效 |
| 登录后跳回登录页 | 登录态未持久化 | 确认是 `--persistent` 模式 + 用户登录后不要 delete-data |
| **跨会话打开后直接跳登录页**（cookie 库里 token 还在） | 登录态加密/解密失效（具体根因未确诊，见「时效性边界」） | 让用户重新登录一次，不要假设「上次登录过 = 现在还能用」 |
| snapshot 找不到元素 | 页面大被截断 / 在弹窗里 | eval 精准提取 / 查 dialog 内容 |
| 连续 `upload` 只保留最后一个文件 | 每次 setFiles 替换列表 | 批量文件用 run-code `page.on('filechooser')` + `setFiles(数组)` 一次传 |
| 上传后子目录文件全在根目录（URL 404） | file input 丢失相对路径 | 需保留目录结构用服务商 CLI/API 部署（Cloudflare = `wrangler deploy`） |

## 参考

- playwright-cli 官方 skill 文件：可在插件市场安装 `playwright-cli` 查看完整命令参考
- 本 skill 基于 2026-08-11 真实 POC 编写，5 平台连登实证（千问、硅基流动、智谱、商汤、腾讯云）
- 更多浏览器自动化讨论见 [sichenai/sichen-skills](https://github.com/sichenai/sichen-skills)

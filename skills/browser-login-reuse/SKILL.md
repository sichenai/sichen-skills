---
name: browser-login-reuse
version: 2.0.0
description: 浏览器自动化登录态复用。当用户需要让 AI 操作真实浏览器完成需要登录的网站任务（如登录控制台查额度、提交表单、上传文件、面板操作），且希望"登录一次、之后复用登录态、不反复登录"时使用。触发词包括：浏览器自动化、登录态复用、帮我登录、操作浏览器、AI 操作网页、persistent、playwright-cli、storageState。触发后，AI 用 playwright-core 启动 Chrome（headed 让用户登录，headless 执行操作）→ 登录后用 storageState 导出登录态 → 跨会话注入 storageState 复用，用 snapshot/click/fill/eval 等操作页面。适用于 macOS（系统 Chrome），不涉及支付/银行类站点。
agent_created: true
---

# 浏览器自动化登录态复用（playwright-core + storageState）

## 何时触发

- 用户需要 AI 操作**需要登录**的网站（控制台查额度、面板配置、表单提交、文件上传等）
- 用户明确要求"登录一次之后别反复登录""复用登录态""AI 帮我操作网页"
- 用户想让 AI 完成原本需要手动操作浏览器的事务性任务

**不适用的场景**（先判断再动手）：
- 只需读静态页面 → 用 WebFetch 更轻
- 调用 API → 用 curl 更直接
- **只是临时打开页面点几下、不涉及登录态复用 → 用 agent-browser CLI 更合适**（本 skill 聚焦登录态复用，agent-browser 适合一次性自动化）
- 支付/银行/资金类站点 → 不交给 AI 会话（安全红线）

## 核心事实（2026-08-11 + 2026-08-15 实测）

### 工具
- **playwright-core**（Node 库，比 playwright-cli 更灵活，支持 storageState API）→ `npm install playwright-core`
- **playwright-cli**（CLI 工具，适合简单交互；不支持 storageState）→ `npm install -g @playwright/cli@latest`
- **agent-browser**（vercel-labs，评估后不采用）→ 通用浏览器自动化 CLI（daemon 模式）；headed 登录可用但**无 storageState 导出/注入 API**，跨会话复用登录态仍需 playwright-core。已从环境移除（2026-08-15），仅留决策记录
- 均依赖 Node 18+ 和浏览器二进制

### 两层方案（2026-08-15 实测重构）

| 层 | 方案 | 适用场景 | 状态 |
|---|---|---|---|
| **同会话内** | `--persistent` 独立 profile + headed 登录 → 不关浏览器，直接操作 | 一次性任务（登录→操作→结束） | ✅ 8/11 实测 5 平台 |
| **跨会话复用** | 登录后 `storageState` 导出 → 下次 `newContext({storageState})` 注入 | 需要多次操作同一登录态 | ✅ 8/15 实测腾讯云 |

### ⚠️ 三个已确诊的失效原因（2026-08-15 实测）

1. **session cookie 关闭即清**：很多平台（如腾讯云的 `nodesess`）登录态 cookie 是 `is_persistent=0`（session cookie），`ctx.close()` 退出 Chrome 时按标准被清除。**这是 `--persistent` 方案跨会话失效的主因**。解决：用 `storageState` 手动导出（含 session cookie）→ JSON 文件落盘 → 下次注入
2. **Chrome 自动升级换密钥**：Chrome 约 4 周自动升级一次，升级后 cookie 加密密钥变化，旧档案里的持久化 cookie 解不开（8/14 升级导致 8/11 的 cookie 在 8/15 失效）。**storageState 不受影响**（JSON 文件，不涉及加密）
3. **WorkBuddy 权限影响 headed 窗口持续性**（推断，未做 A/B 对照）：放开「完全磁盘访问」权限后，headed 窗口约 20 秒被回收；回退权限后窗口持续 180 秒+。如遇窗口消失，检查是否放开了该权限

### 已否决
- `--extension`（接管用户日常 Chrome，干扰大、AI 可见全部登录态）
- `--profile=<日常 Chrome 目录>`（需用户完全退出 Chrome，文件锁）
- **playwright-cli CLI 模式做跨会话复用**（不支持 storageState API，session cookie 关了就清）

## 环境准备

### 必备参数（2026-08-15 实测确认）

```javascript
// playwright-core 启动参数（headless 和 headed 都要加）
{
  channel: 'chrome',
  headless: true,  // 或 false 用于登录
  args: [
    '--no-sandbox',           // 必须，否则 Chrome 崩
    '--disable-gpu',          // 必须，GPU 进程会崩
    '--use-gl=swiftshader',   // 软件渲染
    '--password-store=basic', // 不用系统 keychain
    '--use-mock-keychain',    // mock keychain，避免加密问题
  ]
}
```

### 环境变量

```bash
# 必须设置（playwright-core 路径）
export NODE_PATH=/path/to/node_modules
# 必须清除（否则 node 启动报错）
unset NODE_OPTIONS
```

### 代理（访问国外站点需要）

自动化 Chrome 不读系统代理。访问 Google/GitHub 等需在 args 加：
`--proxy-server=http://127.0.0.1:<代理端口>`（Clash 默认 7890）

## 操作流程（v2.0 推荐：单脚本模式）

### 模式 A：首次登录 + 导出登录态（headed）

```javascript
const { chromium } = require('playwright-core');

const ctx = await chromium.launchPersistentContext('<profile-dir>', {
  channel: 'chrome', headless: false,
  args: ['--no-sandbox', '--disable-gpu', '--use-gl=swiftshader',
         '--password-store=basic', '--use-mock-keychain'],
});
const page = ctx.pages()[0] || await ctx.newPage();
await page.goto('https://目标站点');

// 轮询检测登录完成（URL 从登录页跳走 = 登录成功）
// 注意：此模式会阻塞工具调用，用户无法发消息，但登录过程不需要发消息
for (let i = 0; i < 100; i++) {
  await new Promise(r => setTimeout(r, 3000));
  if (!page.url().includes('/login')) break;  // 平台特定，见下注意事项
}

// 登录成功，导出登录态
await ctx.storageState({ path: './auth/<平台>.json' });
await ctx.close();
```

**⚠️ 登录检测逻辑的平台差异**（中置信，仅腾讯云实测）：
- 腾讯云：URL 从 `/login` 跳到 `/tokenhub/models` ✅ 实测
- 其他平台：可能登录后 URL 不变（只改 DOM），需改为检测 DOM 元素（如 `await page.waitForSelector('.user-avatar')`）

### 模式 B：跨会话复用登录态（headless）

```javascript
const { chromium } = require('playwright-core');

const browser = await chromium.launch({
  channel: 'chrome', headless: true,
  args: ['--no-sandbox', '--disable-gpu', '--use-gl=swiftshader',
         '--password-store=basic', '--use-mock-keychain'],
});
const context = await browser.newContext({ storageState: './auth/<平台>.json' });
const page = await context.newPage();
await page.goto('https://目标站点');

// 验证登录态是否还有效
if (page.url().includes('/login')) {
  console.log('登录态已失效，需重新执行模式 A');
  // ...
}

// 执行操作
const title = await page.title();
const text = await page.evaluate(() => document.body.innerText);
await page.screenshot({ path: 'shots/xxx.png' });

await browser.close();
```

### 模式 C：同会话内登录 + 操作（8/11 原始模式，仍有效）

适合一次性任务，不需要跨会话复用：

```bash
# 用 playwright-cli CLI（简单交互场景）
playwright-cli --config=cli.config.json open --persistent --headed
playwright-cli goto "https://目标站点"
# 用户在窗口登录
playwright-cli snapshot  # 确认登录成功
playwright-cli click e12
playwright-cli fill e5 "文本"
playwright-cli screenshot --filename=shots/xxx.png
playwright-cli close
```

## 操作命令（playwright-core）

```javascript
// 读页面
const text = await page.evaluate(() => document.body.innerText);

// 点击/填表
await page.click('#selector');
await page.fill('#input', '文本');

// 截图
await page.screenshot({ path: 'shots/xxx.png' });

// 等待元素
await page.waitForSelector('.target');

// 跑 JS
const data = await page.evaluate(() => { /* ... */ });
```

**文件上传注意**（2026-08-11 实测）：
- `page.setInputFiles()` 一次只接受单文件（CLI 的 upload 同理）
- 批量上传用 `page.on('filechooser')` + `chooser.setFiles([...数组])`
- **⚠️ setFiles 会丢失目录结构**：`articles/a.html` 会被拍平到根目录 → URL 404。需保留目录结构用服务商 CLI/API（如 `wrangler deploy`）

**页面元素定位技巧**：
- 页面大时用 `page.evaluate()` 跑 JS 精准提取
- 弹窗内容用 `await page.$('[role=dialog]')` 查询

## 截图验证（红线：读图走 OCR）

AI 模型不可靠读图 → 截图后用 OCR 工具验证（如 macOS swift-ocr）：

```bash
swift /path/to/swift-ocr/scripts/ocr.swift shots/xxx.png
```

## 安全红线（必须遵守）

- **AI 持有登录态 = 能以用户身份执行操作** → 关键动作前先复述计划，用户确认后执行
- **支付/银行/资金类站点不交给 AI 会话**
- **密码/验证码/2FA 环节 AI 不代劳**，由用户本人完成
- **凭证不落盘**：storageState 文件含 session cookie，等同于登录凭证，**不要提交到 Git**，放本地 auth/ 目录并 .gitignore
- **storageState 文件含敏感信息**，不对外分享，失效后删除

## 常见问题排查

| 现象 | 原因 | 解决 |
|---|---|---|
| `sandbox initialization failed` | Chrome 沙箱受限 | args 加 `--no-sandbox` |
| `GPU process exited unexpectedly` | GPU 崩溃 | args 加 `--disable-gpu --use-gl=swiftshader` |
| `--use-system-ca is not allowed in NODE_OPTIONS` | NODE_OPTIONS 冲突 | `unset NODE_OPTIONS` |
| headed 窗口 20 秒消失 | 疑似 WorkBuddy「完全磁盘访问」权限影响（推断） | 回退该权限设置 |
| 跨会话跳登录页（persistent profile） | session cookie `is_persistent=0`，close 时清除 | 用 storageState 导出/注入 |
| 跨会话跳登录页（storageState） | 服务端 session 过期 | 重新执行模式 A 登录 |
| 持久化 cookie 解不开（升级后） | Chrome 升级换加密密钥 | storageState 不受影响；如用 persistent profile 需重新登录 |
| 访问国外站点超时 | 自动化 Chrome 不走系统代理 | args 加 `--proxy-server=http://127.0.0.1:<端口>` |
| snapshot 找不到元素 | 页面大被截断 / 在弹窗里 | 用 `page.evaluate()` 精准提取 |
| 上传后子目录文件全在根目录 | file input 丢失相对路径 | 用服务商 CLI/API 部署 |

## 参考

- playwright-core 官方文档：storageState API
- 本 skill 基于 2026-08-11 真实 POC（5 平台连登）+ 2026-08-15 实测重构（storageState 跨会话复用）
- 8/15 实测平台：腾讯云 TokenHub（storageState 跨会话注入成功）
- 更多浏览器自动化讨论见 [sichenai/sichen-skills](https://github.com/sichenai/sichen-skills)

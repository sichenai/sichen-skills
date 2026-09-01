---
name: browser-login-reuse
version: 2.1.0
description: 浏览器自动化登录态复用。当用户需要让 AI 操作真实浏览器完成需要登录的网站任务（如登录控制台查额度、提交表单、上传文件、面板操作），且希望"登录一次、之后复用登录态、不反复登录"时使用。触发词包括：浏览器自动化、登录态复用、帮我登录、操作浏览器、AI 操作网页、persistent、playwright-cli、storageState。触发后先按「路由原则」选通道（API/CLI 优先 → 宿主内置浏览器优先 → 本 skill 兜底）；本 skill 方案 = playwright-core 启动 Chrome（headed 让用户登录，headless 执行操作）→ 登录后用 storageState 导出登录态 → 跨会话注入 storageState 复用，用 snapshot/click/fill/eval 等操作页面。适用于 macOS（系统 Chrome），不涉及支付/银行类站点。
agent_created: true
---

# 浏览器自动化登录态复用（playwright-core + storageState）

## 路由原则（v2.1 新增，先选通道再动手）

「让 AI 操作浏览器」不是一个能力，是「宿主 × 通道」的组合。触发本 skill 后，先按三层路由选通道，**不要默认开浏览器**：

1. **第一层 · 绕开**：任务能走 API/CLI 就不开浏览器。两次实证：站点部署从「浏览器上传」改 `wrangler deploy` 后，浏览器环节整体消失；云服务商绝大多数控制台操作都有对应 CLI/API。先问一句「这事有没有官方命令行」，能省掉登录态这一整个问题域。
2. **第二层 · 借力**：执行环境自带内置浏览器且能导入本机已登录会话的（如 Zcode 内置浏览器，2026-09-01 实证免密回登 Cloudflare 控制台，据其操作记录转引），浏览器任务优先派给该宿主执行——登录态零成本。注意会话存储不跨宿主互通，任务须在该宿主的会话内完成。
3. **第三层 · 兜底**：都没有、或需要脚本化批量抓取/检测的 → 用本 skill（playwright-core + storageState）。登录环节需要用户本人输密码/2FA 的一律回退人工（安全红线）。

## 何时触发

- 用户需要 AI 操作**需要登录**的网站（控制台查额度、面板配置、表单提交、文件上传等）
- 用户明确要求"登录一次之后别反复登录""复用登录态""AI 帮我操作网页"
- 用户想让 AI 完成原本需要手动操作浏览器的事务性任务

**不适用的场景**（先判断再动手）：
- 只需读静态页面 → 用 WebFetch 更轻
- 调用 API → 用 curl 更直接
- 执行环境有内置浏览器且已导入登录会话 → 直接在该宿主内做，不用本 skill（见上方路由原则第二层）
- 支付/银行/资金类站点 → 不交给 AI 会话（安全红线）

## 核心事实（2026-08-11 + 2026-08-15 实测）

### 工具
- **playwright-core**（Node 库，比 playwright-cli 更灵活，支持 storageState API）→ `npm install playwright-core`
- **playwright-cli**（CLI 工具，适合简单交互；不支持 storageState）→ `npm install -g @playwright/cli@latest`
- **agent-browser**（vercel-labs，评估后不采用）→ 通用浏览器自动化 CLI（daemon 模式）；headed 登录可用但**无 storageState 导出/注入 API**，跨会话复用登录态仍需 playwright-core。已从环境移除（2026-08-15），仅留决策记录
- 均依赖 Node 18+ 和浏览器二进制
- **宿主内置浏览器**（如 Zcode，可导入本机已登录会话）→ 登录态获取成本最低的通道，但会话存储不跨宿主互通；本 skill 与其互不替代，按路由原则分流

### ⚠️ 结论适用域（2026-09-01 增补）

「headed 窗口登录场景不可用」等历史结论，验证环境均为 **Bash 沙箱类宿主（WorkBuddy）+ 脚本方案**，**不是普适结论**。换宿主（内置浏览器/桌面辅助功能通道）或换通道后需重新评估，不要直接套用本文件结论否定其他方案。

### 两层方案（2026-08-15 实测重构）

| 层 | 方案 | 适用场景 | 状态 |
|---|---|---|---|
| **同会话内** | `--persistent` 独立 profile + headed 登录 → 不关浏览器，直接操作 | 一次性任务（登录→操作→结束） | ✅ 8/11 实测 5 平台 |
| **跨会话复用** | 登录后 `storageState` 导出 → 下次 `newContext({storageState})` 注入 | 需要多次操作同一登录态 | ✅ 8/15 实测腾讯云 |

### 登录态获取三条路线（2026-09-01 补全）

| 路线 | 做法 | 成本 | 适用 |
|---|---|---|---|
| **① 导入已有会话** | 宿主内置浏览器导入本机已登录会话（Google OAuth 等），免密回登 | 最低 | 执行环境有内置浏览器且会话在位（如 Zcode，9/1 实证，据其操作记录转引） |
| **② 注入 storageState** | 历史导出的 `auth/<平台>.json` 注入 `newContext` | 低（有存量文件时） | 本 skill 主路线，见模式 B |
| **③ 新登录 + 导出** | headed 让用户登录（密码/2FA 本人操作）→ `ctx.storageState({path})` 导出 | 最高（需人参与） | 首次登录、②失效后重登，见模式 A |

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

## 操作流程（v2.0 起推荐：单脚本模式）

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
| 持久化 cookie 解不开（升级后） | Chrome 升级换加密密钥 | storageState 不受影响（未跨升级实测，见下方验证清单）；如用 persistent profile 需重新登录 |
| 访问国外站点超时 | 自动化 Chrome 不走系统代理 | args 加 `--proxy-server=http://127.0.0.1:<端口>` |
| snapshot 找不到元素 | 页面大被截断 / 在弹窗里 | 用 `page.evaluate()` 精准提取 |
| 上传后子目录文件全在根目录 | file input 丢失相对路径 | 用服务商 CLI/API 部署 |

### 「storageState 跨 Chrome 升级是否存活」验证清单（2026-09-01 立项，待验）

原理：Chrome 约 4 周自动升级一次，升级后 cookie 加密密钥变化（8/14 升级致 8/11 持久 profile 失效）。storageState 是明文 JSON、不依赖 Chrome 加密，理论上升级不受影响——**但「理论上」至今未考过试**（8/15 导出的文件已丢失，错过 9/1 的 151→152 升级验证窗口）。下次导出登录态后，按此清单顺手完成验证：

1. 导出后记录当时的 Chrome 版本：`"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --version`，与 `auth/<平台>.json` 一起登记（写进文件名或旁边备注）
2. 下次 Chrome 自动升级后（二进制 mtime 变化即已升级），**先用升级前导出的 storageState 注入访问该平台**
3. 未跳登录页 → 验证通过，更新下表；跳登录页 → 可能是服务端 session 自然过期，换一个导出后 3 天内的文件重测一次再下结论
4. 结果记入：跨升级存活 = ✅/❌（日期 + Chrome 版本对）

| 验证 | 结果 | 凭证 |
|---|---|---|
| 跨升级存活 | ❓ 待验 | — |

## 参考

- playwright-core 官方文档：storageState API
- 本 skill 基于 2026-08-11 真实 POC（5 平台连登）+ 2026-08-15 实测重构（storageState 跨会话复用）
- 8/15 实测平台：腾讯云 TokenHub（storageState 跨会话注入成功）
- v2.1.0（2026-09-01）：新增路由原则（三层分流）、宿主内置浏览器路线与结论适用域声明、登录态获取三路线、跨升级验证清单——触发事件：另一宿主（Zcode）用内置浏览器十分钟免密跑通 WorkBuddy 当年三天踩坑的同需求，对比诊断后确认差异在「宿主×通道」而非方案错误
- 更多浏览器自动化讨论见 [sichenai/sichen-skills](https://github.com/sichenai/sichen-skills)

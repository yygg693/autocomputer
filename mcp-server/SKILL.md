---
name: autocomputer
description: Windows desktop GUI automation via a Reasonix MCP server — screenshot + Windows OCR, click/type/press/scroll, window management, send-target verification, SQLite audit + per-app permissions, cross-session action memory. Like Codex "computer use" for Reasonix. Use when the user asks to operate a desktop app (WeChat/QQ/Excel/Notepad...), auto-send messages, auto-fill forms, read the screen, click a button, or automate any GUI task. Triggers include "帮我操作XX应用", "自动发消息", "自动填表", "截图识别", "点击XX按钮", "桌面自动化".
allowed-tools: mcp__autocomputer__*, bash
---

# autocomputer — Reasonix 桌面 GUI 自动化（computer use）

通过 MCP server（`autocomputer_mcp.py`）把桌面操作暴露为 Reasonix 工具
`mcp__autocomputer__*`。模型是纯文本的 deepseek-v4，所以视觉通道走
**截图 + Windows 内置 OCR**（文本行 + 坐标），token 高效且确定性高。

## 工作循环（对标 Codex computer use）

```
see(截图+OCR) → 分析 → find/act(带坐标) → see 验证 → （发送前）verify_target
```

## 工具（mcp__autocomputer__*）

| 工具 | 作用 |
| --- | --- |
| `see` | 截图 + OCR 文本行(带 box/center) + 激活窗口标题 + 变化检测。动作前后各调一次 |
| `find` | OCR 定位文本 → 前 5 个候选坐标（不点击），再交给 `act` |
| `act` | click / double_click / right_click / mouse_move / type / press / scroll / wait；自动 before/after diff + `expect` 校验 + 审计落库 |
| `verify_target` | **发送前硬门禁**：比对激活窗口标题。90s 内未通过 → `act` 的发送类按键(enter/ctrl+enter/send/submit)会被拒绝 |
| `apps` | 列出窗口 / 按标题聚焦（操作前先查，避免重复实例） |
| `audit` | 查询 SQLite 审计日志（每次 act 都有记录） |
| `permissions` | 按 app 设 ask/allow/deny；deny 硬拦截该 app 的 act |
| `memory` | 跨会话操作配方：learn(app,task,steps) / recall(app[,task]) |

## 安全规则（不可协商）

1. 任何破坏性操作前先 `see` 截图；操作后 `see` 验证。
2. **发送前必须 `verify_target`**（发错对象是 #1 故障模式）；验证后 90s 内有效。
3. pyautogui FAILSAFE 常开 —— 鼠标甩到屏幕左上角 (0,0) 立即中止。
4. 不输入密码/密钥，除非用户明确要求。
5. 状态不确定 → 截图。
6. 启动应用前先 `apps list`，避免重复实例。
7. QQ 发消息 = Ctrl+Enter（普通 Enter 只是换行）。

## 直接调用脚本（备用，不走 MCP）

```powershell
$SC = "$env:USERPROFILE\.agents\skills\autocomputer\scripts"
python "$SC\cua.py" see                 # 截图
python "$SC\cua.py" act click --x 500 --y 300
python "$SC\ocr.py" read "C:\path\shot.png" --lines   # 独立 OCR
python "$SC\autocomputer_mcp.py" --selftest            # MCP 自检
```

## 文件映射（单一来源：%USERPROFILE%/autocomputer/mcp-server/）

> `scripts/` 是指向仓库 `mcp-server/` 的 junction 软链 —— 技能与 GitHub 仓库
> (yygg693/autocomputer) 共用同一份代码，改仓库即改技能，无双份维护。
> 仓库地址：https://github.com/yygg693/autocomputer

```
autocomputer_mcp.py  MCP server（Reasonix 通过它调用，见 config.toml [[plugins]]）
cua.py               截图/动作/变化检测核心（原 global-workspace 收编）
state.py             统一 SQLite：audit_log / permissions / learned_actions / ui_patterns / user_prefs
ocr.py + ocr.ps1     Windows 内置 OCR（Windows.Media.Ocr，零下载，中文 zh-Hans-CN）
acp.py.legacy        旧 ACP 层设计参考（verify-target 门禁思路已并入 MCP server）
```

数据目录：`~/.qclaw/workspace/screenshots/`（截图）、`~/.qclaw/workspace/.acp/`（verify 状态）、
`~/.qclaw/autocomputer/unified_state.db`（审计/权限/记忆 SQLite）。

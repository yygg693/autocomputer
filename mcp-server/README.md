# MCP Server (`mcp-server/`)

**autocomputer 的 Model Context Protocol 集成层** —— 把桌面 GUI 自动化暴露为
MCP 工具(`see` / `find` / `act` / `verify_target` / `apps` / `audit` /
`permissions` / `memory`),任何支持 MCP 的 agent(Reasonix、Claude Code、Cursor 等)
都可以直接驱动桌面操作。纯 Python + Windows 内置 OCR,零第三方 OCR 依赖。

> 与仓库根目录的 Rust core + Python SDK 是**两套独立实现**:
> - Rust core + SDK 面向程序化集成(低延迟截图、系统调用、HTTP API、Dashboard)
> - 本模块面向 **AI agent 会话**:截图 + OCR → agent 决策 → 动作 → 截图验证的闭环
>
> 本模块不依赖 Rust core,可独立运行。

## 文件说明

| 文件 | 作用 |
| --- | --- |
| `autocomputer_mcp.py` | MCP stdio server(JSON-RPC 2.0),8 个工具入口 |
| `cua.py` | 截图 / 动作执行 / 变化检测核心 |
| `state.py` | 统一 SQLite:`audit_log` / `permissions` / `learned_actions` / `ui_patterns` / `user_prefs` |
| `ocr.py` + `ocr.ps1` | Windows 内置 OCR 封装(`Windows.Media.Ocr`,中文 `zh-Hans-CN`,零下载) |
| `acp.py.legacy` | 旧 ACP 层设计参考(verify-target 门禁思路已并入 MCP server) |
| `SKILL.md` | Reasonix 技能定义(复制到技能目录后自动生效) |

## 工具一览

| 工具 | 作用 |
| --- | --- |
| `see` | 截图 + OCR 文本行(带坐标) + 激活窗口标题 + 变化检测 |
| `find` | OCR 定位文本 → 前 5 个候选坐标(不点击) |
| `act` | click / double_click / right_click / mouse_move / type / press / scroll / wait;自动 before/after diff + `expect` 校验 + 审计落库 |
| `verify_target` | **发送前硬门禁**:比对激活窗口标题,90s 内未通过则拒绝发送类按键 |
| `apps` | 列出窗口 / 按标题聚焦 |
| `audit` | 查询 SQLite 审计日志 |
| `permissions` | 按 app 设 ask/allow/deny;deny 硬拦截 |
| `memory` | 跨会话操作配方 learn/recall |

## 快速开始

```powershell
# 1) 直接作为 MCP server 注册(任何 MCP 客户端)
#    command: python, args: ["<本目录>/autocomputer_mcp.py"]

# 2) 作为 Reasonix 技能安装
#    复制本目录到 ~/.agents/skills/autocomputer/ 后,在 config.toml 的
#    [[plugins]] 指向 scripts/autocomputer_mcp.py 即可

# 3) 自检
python autocomputer_mcp.py --selftest
```

## 安全规则(内置,不可关闭)

1. 发送类按键(`enter` / `ctrl+enter` / `send` / `submit`)必须先通过 `verify_target`
2. 每次 `act` 自动记录审计日志 + before/after 截图
3. per-app 权限策略:`deny` 硬拦截该应用的所有操作
4. `pyautogui.FAILSAFE` 常开:鼠标甩到屏幕左上角 (0,0) 立即中止

## 数据目录

运行时数据(截图、verify 状态、SQLite 审计库)存放在用户目录下:

```
%APPDATA%/autocomputer/workspace/screenshots/        # 截图
%APPDATA%/autocomputer/workspace/.acp/               # verify 状态
%APPDATA%/autocomputer/unified_state.db # 审计/权限/记忆 SQLite
```

## 依赖

- Python 3.10+
- `pyautogui`(动作执行;缺失时 `act` 不可用,其余工具可降级)
- Windows 10/11(OCR 用 `Windows.Media.Ocr`)

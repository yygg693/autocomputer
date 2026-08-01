# Dashboard 渐进增强 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 autocomputer 的 HTML5 Dashboard 渐进增强为"真实数据 + 中文 UI + 视觉升级 + 拖拽交互",全程零构建、不动 Rust core。

**Architecture:** 阶段零把 `gui/index.html`(759 行单文件)纯拆分为 `index.html` + `style.css` + `app.js`(零回归);阶段一扩展 `server.py` 零依赖 API(status 真实化 / logs / security / flows 持久化)并接线前端;阶段二统一中文 + 深色主题 + CSS 条形图;阶段三加拖拽排序 + 响应式 + Toast。

**Tech Stack:** 原生 HTML/CSS/JS(零构建)、Python 标准库 http.server、SQLite(rusqlite 侧已有,Python 侧用 sqlite3)、pytest。

## Global Constraints

- 零构建: 不引入 npm/Vite/React/WebSocket;浏览器直接打开 `gui/index.html` 可用
- 不动 Rust core(`crates/ac-core/` 零改动)
- server.py 仅用 Python 标准库
- 前端全中文(按钮/标签/提示)
- 数据文件: flows 存 `%APPDATA%/autocomputer/flows.json`;审计库 `%APPDATA%/autocomputer/autocomputer_audit.db`
- 修改后 commit + push(GitHub `main`,代理 `127.0.0.1:7890`),SKILL.md hardlink 校验
- Python 测试保持 25 passed + 2 skipped,新增 API 测试不依赖 Rust(_bridge fallback)

---

### Task 0: 拆分 gui 三文件(零回归)

**Files:**
- Create: `gui/style.css`(现有 `<style>...</style>` 内容)
- Create: `gui/app.js`(现有 `<script>...</script>` 内容)
- Modify: `gui/index.html`(删除内联 style/script,改 `<link rel="stylesheet" href="style.css">` + `<script src="app.js"></script>`)

**Interfaces:**
- Produces: `window.state`(5 个页面共用状态)、`render()`、`api(path, opts)`(fetch 封装)、5 个 render 函数、`ACTION_DEFS` — 全部保持现有行为不变

- [ ] **Step 1: 抽取样式与脚本**
  用 python 脚本从 index.html 提取 `<style>` 块 → `gui/style.css`,`<script>` 块 → `gui/app.js`,并在 index.html 中替换为外链引用。**不改任何逻辑**,只做搬运。
- [ ] **Step 2: 回归验证**
  打开 `gui/index.html`,5 个 tab 均可切换;控制台无 JS 报错;`render()` 正常。Python 侧不受影响。
- [ ] **Step 3: 提交**
  `git add gui/ && git commit -m "refactor(gui): split single-file dashboard into index.html + style.css + app.js"`

---

### Task 1: server.py — status 真实化 + logs/security/flows API

**Files:**
- Modify: `python/autocomputer/server.py`
- Test: `python/tests/test_server_api.py`(新建)

**Interfaces:**
- Consumes: `autocomputer.utils.config_dir()`、`autocomputer.core._bridge._RUST_AVAILABLE`、`_get_rust_attr`
- Produces:
  - `GET /api/status` → `{status, rust_core, version, screen, modules, tests_passed(int, 动态统计), uptime_seconds}`
  - `GET /api/logs` → `{logs: [{ts, action, detail, ok}]}`
  - `GET /api/security` → `{audit: {total, by_action: {..}, recent: [{..}]}, hotkeys: [...], thresholds: {...}}`
  - `GET /api/flows` → `{flows: [{name, steps, created, step_count}]}`
  - `POST /api/flows` body `{name, steps}` → 保存到 flows.json(同名覆盖)
  - `DELETE /api/flows?name=X` → 删除

- [ ] **Step 1: 写失败测试** `python/tests/test_server_api.py`(mock Rust 缺失的 fallback 场景):
  - status 返回 `tests_passed` 为 int 且 > 0(实际统计源码测试数)
  - POST /api/flows 后 GET 能取回同名流程
  - DELETE /api/flows 后 GET 不再包含
  - /api/logs 在 execute 后新增记录
  - /api/security 返回结构完整(审计可能为空,结构在)
  用 `http.server` 的 handler 直接实例化测试方法,不真正 listen(或 `ThreadingHTTPServer` + 临时端口)。
- [ ] **Step 2: 实现** 在 `server.py` 中:
  - `_status`: 统计 `Path("crates/ac-core/src").glob("*.rs")` 的 `#[test]` 与 `Path("python/tests").glob("*.py")` 的 `def test_`,求和替换硬编码 56
  - 模块级 `_LOG_QUEUE = deque(maxlen=200)`;`_execute` 成功/失败均追加 `{"ts": iso, "action": ..., "detail": ..., "ok": bool}`;`_logs()` 返回
  - `_security()`: 用 `sqlite3` 打开 `config_dir()/"autocomputer_audit.db"`,查询 `SELECT COUNT(*)`, `SELECT action, COUNT(*) GROUP BY action`, `SELECT * ORDER BY id DESC LIMIT 20`;热键黑名单/阈值返回默认值(与 Rust security.rs 默认一致: alt+f4/win+l/win+r/ctrl+alt+del, 5 次, 100ms, 90 天)
  - flows: 用 `config_dir()/"flows.json"`,GET 读全量,POST 合并写入(带 `created`),DELETE 按 name 过滤;文件不存在返回空列表
  - do_GET/do_POST 路由补 `logs`、`security`、`flows(POST/DELETE)`
- [ ] **Step 3: 跑测试全绿** `pytest python/tests/ -q` → 25+2 skip + 新测试通过
- [ ] **Step 4: 提交** `git commit -m "feat(server): real status counts, logs/security APIs, flow persistence"`

---

### Task 2: 前端接线 — 监控/安全/截图/流程 真实数据

**Files:**
- Modify: `gui/app.js`

- [ ] **Step 1: 监控页真实化** `renderMonitor()` 改为 `api('/api/logs')` 渲染日志行(ts/level/msg),空态"暂无操作记录";2s 轮询刷新(仅页面激活时)
- [ ] **Step 2: 安全页真实化** `renderSecurity()` 改为 `api('/api/security')` 渲染统计卡 + 热键黑名单 + 审计最近记录;空态提示
- [ ] **Step 3: 截图预览** Dashboard `quickCapture()` 后把 `png_b64` 显示为 `<img>` 预览卡片(不刷新页面)
- [ ] **Step 4: 流程持久化** 初始化 `loadFlows()`(GET /api/flows);`saveFlow()` 走 POST;流程列表加删除按钮走 DELETE;刷新后流程仍在
- [ ] **Step 5: 提交** `git commit -m "feat(gui): wire monitor/security/capture/flows to real APIs"`

---

### Task 3: 视觉升级 — 全中文 + 深色主题 + 条形图

**Files:**
- Modify: `gui/app.js`、`gui/style.css`

- [ ] **Step 1: 全中文** 所有按钮文本/标签/空态/Toast(如 "Save Flow"→"保存流程","Test Run"→"试运行","Export JSON"→"导出 JSON","Clear"→"清空",页标题等)
- [ ] **Step 2: 深色主题卡片化** 统一 CSS 变量色板,卡片圆角/阴影,状态徽章(ok/info/warn/error 色),加载/空态样式
- [ ] **Step 3: 审计条形图** 安全页 `by_action` 用纯 CSS 横向条形图(宽度按计数比例)
- [ ] **Step 4: 提交** `git commit -m "style(gui): chinese UI, dark theme polish, audit bar chart"`

---

### Task 4: 交互增强 — 拖拽排序 + 响应式 + Toast

**Files:**
- Modify: `gui/app.js`、`gui/style.css`

- [ ] **Step 1: 拖拽排序** 编辑器步骤列表加 `draggable=true`,HTML5 dragstart/dragover/drop 重排 `state.editing`
- [ ] **Step 2: 响应式** 窄窗口下侧栏折叠/网格降列(`@media` 断点)
- [ ] **Step 3: Toast 统一** 统一 `toast()` 调用点,按钮提交防抖
- [ ] **Step 4: 提交** `git commit -m "feat(gui): drag-drop reorder, responsive layout, toast polish"`

---

### Task 5: 端到端验证 + 同步

- [ ] **Step 1: 全量测试** `pytest python/tests/ -q`(25+2+新增全绿)
- [ ] **Step 2: 前端冒烟** 启动 `python -m autocomputer.server`,浏览器打开 8765 逐个 tab 验证(截图预览/日志/审计/流程增删/拖拽/中文)
- [ ] **Step 3: README 更新** Feature Map 的 Dashboard 一节补新能力描述
- [ ] **Step 4: push + hardlink 校验** `git push origin main`;校验 SKILL.md nlink=2

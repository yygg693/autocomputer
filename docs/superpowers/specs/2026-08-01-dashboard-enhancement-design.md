# Dashboard 渐进增强设计

- 日期: 2026-08-01
- 状态: 已批准(用户确认)
- 范围: `gui/` 前端 + `python/autocomputer/server.py` HTTP API

## 背景与动机

autocomputer 仓库自带一个 759 行单文件 HTML5 Dashboard(`gui/index.html`,5 个页面:
仪表盘 / 录制编辑器 / 流程管理 / 实时监控 / 安全审计),通过 `server.py` 零依赖
HTTP API 驱动。经研究,它存在以下真实问题:

1. **假数据**: 监控页日志、安全页统计(热键/权限/审计)全部是硬编码 HTML;
   `server.py` 的 `/api/status` 返回 `tests_passed: 56` 也是硬编码。
2. **无持久化**: 流程只存在前端内存(`state.flows`),刷新即丢;`/api/flows`
   只扫描当前目录的 JSON,无保存/删除接口。
3. **截图无预览**: `/api/capture` 已返回 base64 PNG,前端只显示数字不显示图。
4. **交互弱**: README 声称"拖拽编辑器",实际是按钮添加 + 固定列表。
5. **界面混杂**: 中英按钮混用,无统一主题。

目标(用户确认): 功能补全 + 真实数据、交互与界面体验、视觉呈现升级;
架构: 拆分为静态多文件(零构建);界面语言: 全中文。

## 方案选择

用户从三个方案中选择**渐进增强**(推荐):
- 方案 1 全面重写(一次到位,回归风险高) — 未选
- **方案 2 渐进增强(三阶段,每阶段可独立验证)** — 已选
- 方案 3 最小增强(只修数据) — 未选

## 架构(阶段零:先拆分,零回归)

```
gui/
├── index.html    ← 页面结构(5 页面容器、导航),现有 <style>/<script> 移出
├── style.css     ← 全部样式
└── app.js        ← 全部逻辑(渲染函数、状态、API 调用)
```

- 浏览器直接打开 `index.html`,零构建(保持项目 no-build 哲学)
- **第一步只做纯拆分,不改任何逻辑**,浏览器验证无回归后再进入阶段一

## 阶段一 · 数据真实化

### server.py API 扩展(全部零依赖标准库)

| API | 改动 |
|-----|------|
| `GET /api/status` | `tests_passed: 56` 硬编码 → 动态统计: 扫描 `crates/ac-core/src/*.rs` 的 `#[test]` + `python/tests/*.py` 的 `def test_` |
| `GET /api/logs` | 新增: server 进程内操作执行记录(内存环形队列,上限 ~200 条),每次 `/api/execute` 追加 |
| `GET /api/security` | 新增: 从 `%APPDATA%/autocomputer/autocomputer_audit.db` 读审计总数/最近 20 条/按 action 分组计数;返回热键黑名单与默认阈值 |
| `GET /api/flows` | 改为读 `~/.autocomputer/flows.json`(`utils.config_dir()` 定位),不再扫当前目录 |
| `POST /api/flows` | 新增: 保存流程(合并或覆盖同名),写入 `flows.json` |
| `DELETE /api/flows` | 新增: 删除指定流程,更新 `flows.json` |

数据文件: `%APPDATA%/autocomputer/flows.json`(与审计库同目录,Windows)。

### 前端接线

- **监控页**: 删硬编码日志,渲染 `/api/logs`(空则显示空态"暂无操作记录")
- **安全页**: 删硬编码统计/权限,渲染 `/api/security` 真实数据
- **Dashboard**: 截图区域显示 `png_b64` 实时预览(`<img src="data:image/png;base64,...">`)
- **流程管理**: 启动时 `GET /api/flows` 加载;保存/删除走新 API;保留本地编辑态

## 阶段二 · 视觉升级

- 全中文: 所有按钮/标签/提示(现有 "Save Flow"/"Test Run"/"Clear" 等)
- 统一深色主题色板,卡片化布局,状态徽章(ok/info/warn/error),加载态/空态
- 安全页审计计数条形图(纯 CSS,零依赖)

## 阶段三 · 交互增强

- 编辑器步骤 HTML5 原生 drag/drop 拖拽排序(零依赖)
- 响应式布局(窄窗口自适应)
- Toast 统一、错误处理完善、按钮防抖

## 测试与验证

- `server.py` 新 API 加 pytest 单元测试(mock 掉 Rust 核心,fallback 模式可跑)
- 前端: 启动 `python -m autocomputer.server` → 浏览器打开 `http://127.0.0.1:8765`,
  逐个 tab 手动验证(截图预览、日志、审计、流程保存/删除)
- 全程不动 Rust core;Python 测试保持 25 passed + 2 skipped

## 边界与不做的

- 不引入任何 npm/Vite/React 等构建依赖(零构建约束)
- 不改 Rust core
- 不做多用户/鉴权(本地工具)
- 监控页不做 WebSocket 实时推送(轮询 2s 足够,零依赖)

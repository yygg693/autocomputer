# Changelog

All notable changes to this project are documented in this file.

## [v0.9.0] - 2026-08-01

### 🚀 Highlights
- **MCP Server** (`mcp-server/`) — 8-tool Model Context Protocol integration for AI agents (see / find / act / verify_target / apps / audit / permissions / memory), with Windows built-in OCR (zero downloads, Chinese `zh-Hans-CN`). Fully integrated with the Reasonix skill (junction link + SKILL.md hardlink, single source of truth).
- **Obsidian design-system Dashboard** — near-black layered palette + brass `#c9a962` + cyan `#4fd6ff`, glass cards, **jelly press/spring physics** and **gold particle FX** (pure CSS/JS, zero build). 7 pages: Dashboard / Desktop Console / Recorder Editor / Flows / Monitor / Security / Memory.
- **Rust core online** — compiled `_core.pyd` (GNU toolchain); real window listing, click/focus/move through the browser UI.
- **One-click launch** — `scripts/start-dashboard.cmd` starts the server and opens the browser automatically.

### ✨ New features
- Desktop Console page: live window list, focus, coordinate click/move (`/api/execute`).
- Memory page: learned actions + per-app permissions + MCP audit from `unified_state.db`.
- Flows persisted server-side (`%APPDATA%/autocomputer/flows.json`); `POST/DELETE /api/flows`.
- `/api/logs` ring buffer + `/api/security` (audit stats from SQLite).
- Recorder editor redesigned as a 3-column RPA-style editor: action library | step timeline | property panel with per-action param forms and a simulated-screen preview.
- Jelly physics (press squash + spring-back) and click-burst particles across the UI.

### 🐛 Fixed
- `_bridge.py`: `_get_rust_attr` now catches `ImportError` — pure-Python fallback actually works (tests went 15 failed → 32 passed).
- Audit DB path moved from CWD to `%APPDATA%/autocomputer/`; `ALTER TABLE` now conditional.
- CI now runs `cargo test` + a Python pytest job (previously no tests ran in CI).
- Server crashed on GBK consoles due to emoji in the banner — UTF-8 reconfigure + `UnicodeDecodeError` guard on JSON bodies.
- `html/body` missing `width:100%` collapsed the layout (~400px dead space on the right of every page).
- Duplicate `deleteFlow` shadowed the API version, breaking flow deletion.
- `ScreenContext.capture` now degrades gracefully when an OCR backend is installed but unusable.

### 🔧 Changed
- Version bumped to **0.9.0** (was 0.8.0); project description updated across `pyproject.toml`, `__init__.py`, `Cargo.toml`, README.
- UI fully localized to Chinese.
- Dashboard stat "tests passed" now reports the real dynamic count (61 = 29 Rust + 32 Python).

## [v0.8.0] - 2026-07-22

Initial release — Rust core + Python SDK + HTML5 Dashboard architecture, as described in the original README.

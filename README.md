<div align="center">

# autocomputer 🦀🐍🌐

**AI-driven desktop GUI automation — Rust core + Python SDK + MCP Server + HTML5 Dashboard.**

> No black box. No subscription. Your computer, your rules.

[![Rust](https://img.shields.io/badge/Rust-1.97-orange.svg)](https://www.rust-lang.org/)
[![Python](https://img.shields.io/badge/Python-3.9+-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/Tests-61%2F61-brightgreen.svg)](#)
[![Platform](https://img.shields.io/badge/Platform-Windows%2010%2F11-blueviolet.svg)](#)
[![Release](https://img.shields.io/badge/Release-v0.9.0-blue.svg)](CHANGELOG.md)

</div>

---

## Why autocomputer?

Most GUI automation tools fall into two camps: **proprietary cloud services** that send your screen to remote servers, or **fragile coordinate-based scripts** that break the moment your window moves. autocomputer takes a third path:

- 🦀 **Rust core** for sub-10ms screenshots and reliable system calls
- 🐍 **Python SDK** for rapid scripting and AI integration
- 🔌 **MCP Server** so any MCP-capable AI agent can drive the desktop directly
- 🌐 **HTML5 Dashboard** — a zero-build visual console with real data, not mockups
- 🛡️ **Built-in safety** — bounds clamping, loop detection, rate limiting, hotkey blocking, SQLite audit

---

## ✨ Feature Map

### 🦀 Rust Core (`crates/ac-core/`)

| Module | File | What it does |
|--------|------|-------------|
| **capture** | `capture.rs` | Multi-monitor screenshot via xcap/DXGI, region crop, PNG encode (~8ms) |
| **input** | `input.rs` | Mouse move/click/drag/scroll, keyboard type/press, Chinese via clipboard |
| **window** | `window.rs` | Windows API: enumerate, focus, move, resize, launch apps |
| **security** | `security.rs` | 7-layer defense + SQLite audit (bounds, loop, rate, hotkeys, per-app permissions) |
| **image_proc** | `image_proc.rs` | Pixel diff, dHash, Hamming, NCC template matching, change detection |

### 🐍 Python SDK (`python/autocomputer/`)

| Package | Purpose |
|---------|---------|
| `agent/` | CoT context collection, action planning, execution, state tracking |
| `perception/` | Multi-backend OCR (PaddleOCR / EasyOCR / Tesseract / LLM Vision) |
| `record/` | ActionFlow v1.0 — intent-based recording, smart replay, flow compression |
| `llm/` | Playwright-based browser automation via CDP |
| `cli/` | typer CLI + plugin registry |
| `server.py` | Zero-dependency HTTP API (`/api/status`, `/capture`, `/execute`, `/flows`, `/logs`, `/security`, `/windows`, `/memory`) |

### 🌐 Dashboard (`gui/`)

**Obsidian design system** — near-black layers, brass `#c9a962` accent + cyan, glass cards, jelly press physics, gold particle FX. Pure CSS/JS, **zero build**. 7 pages:

| Page | What it shows |
|------|--------------|
| 📊 仪表盘 | Real-time status (dynamic test counts), live screenshot preview, quick actions |
| 🖥️ 桌面操作台 | Real window list, focus, coordinate click/move via `/api/execute` |
| ✏️ 录制编辑器 | RPA-style 3-column editor: action library · step timeline · property panel with param forms + simulated-screen preview |
| 📋 流程管理 | Flows persisted to `%APPDATA%/autocomputer/flows.json`, replay, delete, JSON export |
| 👁️ 实时监控 | Real operation log from `/api/logs` |
| 🛡️ 安全审计 | Real audit stats from SQLite + hotkey blocklist + CSS bar chart |
| 🧠 记忆浏览 | Learned actions + per-app permissions + MCP audit from `unified_state.db` |

**One-click launch:** double-click `scripts/start-dashboard.cmd` → server starts + browser opens automatically. The frontend shares state with the MCP server (flows / audit / memory).

### 🔌 MCP Server (`mcp-server/`)

8 tools (`see` / `find` / `act` / `verify_target` / `apps` / `audit` / `permissions` / `memory`) that any MCP-capable agent (Reasonix, Claude Code, Cursor…) can call directly. Pure Python + **Windows built-in OCR** (zero downloads, Chinese `zh-Hans-CN`), independent of the Rust core. See [`mcp-server/README.md`](mcp-server/README.md).

---

## 🚀 Quick Start

### Requirements

- **Rust** 1.97+ (`rustup default stable`)
- **Python** 3.9+

### One-command setup

```bash
make dev          # builds Rust core + installs Python package + dashboard launcher
```

### Verify

```bash
# Rust core loaded
python -c "from autocomputer.core._bridge import _RUST_AVAILABLE; print('Rust core:', _RUST_AVAILABLE)"
# autocomputer v0.9.0
# Rust core: ✅ loaded (5 modules)
# 61 passed (29 Rust + 32 Python)
```

### Launch the Dashboard

```bash
# Option 1: double-click scripts/start-dashboard.cmd
# Option 2: one command
cd autocomputer && PYTHONPATH=python python -c "import threading,webbrowser; from autocomputer.server import run_server; threading.Timer(2.0, lambda: webbrowser.open('http://127.0.0.1:8765')).start(); run_server()"
# 🦀 autocomputer API Server v0.9.0
# 🌐 GUI: http://127.0.0.1:8765
```

---

## 📖 Usage

### Python SDK — Screenshot & Click

```python
from autocomputer.core import capture_screen, mouse_click

result = capture_screen(0)          # ~8ms screenshot
mouse_click(500, 300)               # click through the Rust engine (security guard enforced)
```

### Record & Replay

```python
from autocomputer.record.engine import FlowRecorder
rec = FlowRecorder(name="login")
rec.record_click(500, 300, description="点击登录按钮")
rec.record_type("hello", description="输入账号")
rec.save("flows/login.json")
```

### HTTP API

```bash
curl http://127.0.0.1:8765/api/status          # system status
curl http://127.0.0.1:8765/api/capture         # screenshot (base64 PNG)
curl -X POST http://127.0.0.1:8765/api/execute \
     -H "Content-Type: application/json" \
     -d '{"action":"click","params":{"x":500,"y":300}}'
```

---

## 🏗 Architecture

```
┌──────────────────────────────────────────────────────────┐
│ 🔌 MCP Server (mcp-server/) — 8 tools, Windows OCR       │
│    see · find · act · verify_target · apps · audit ·     │
│    permissions · memory                                  │
├──────────────────────────────────────────────────────────┤
│ 🌐 HTML5 Dashboard (gui/) — 7 pages, Obsidian design      │
│    zero build · jelly + particles · one-click launch      │
├──────────────────────────────────────────────────────────┤
│ 🐍 Python SDK (python/) — agent · perception · record ·   │
│    llm · cli · server.py (zero-dep HTTP API)              │
├──────────────────────────────────────────────────────────┤
│ 🦀 Rust Core (crates/ac-core/) — capture · input ·        │
│    window · security(7 layers) · image_proc                │
└──────────────────────────────────────────────────────────┘
        └── Runtime data: %APPDATA%/autocomputer/
            (workspace/ · unified_state.db · flows.json · autocomputer_audit.db)
```

---

## 🛡️ Security Model

| Layer | What it does |
|-------|-------------|
| **Fail-safe corner** | Mouse to (0,0) aborts immediately |
| **Bounds clamping** | Clicks clamped to the active monitor |
| **Loop detection** | Same-position clicks within 5s are blocked |
| **Rate limiting** | 100ms minimum between actions |
| **Hotkey blocklist** | alt+f4 / win+l / win+r / ctrl+alt+del blocked |
| **Per-app permissions** | allow / deny / prompt per application |
| **SQLite audit** | Every action recorded with timestamps (90-day retention) |

The MCP server adds a **verify_target hard gate** before any send-class key and per-app policy from its own unified state DB.

---

## 🧪 Testing

| Suite | Framework | Count |
|-------|-----------|-------|
| Rust unit tests | `cargo test` | 29 |
| Python tests | `pytest` | 32 |
| **Total** | | **61 — all passing** |

```bash
cargo test --workspace     # 29 tests, 0 failures
pytest python/tests/ -q    # 32 tests, 0 failures
cargo clippy --workspace   # 0 warnings
```

CI (GitHub Actions) runs `cargo build / test / clippy / fmt` plus a Python pytest job on every push.

---

## 📂 Project Structure

```text
autocomputer/
├── crates/ac-core/          # Rust core (capture, input, window, security, image_proc)
├── python/
│   ├── autocomputer/        # Python SDK + server.py (HTTP API)
│   └── tests/               # 32 pytest tests
├── gui/
│   ├── index.html           # Dashboard shell (7 pages)
│   ├── style.css            # Obsidian design system
│   └── app.js               # rendering + API wiring + jelly/particles
├── mcp-server/              # MCP server (8 tools, Windows OCR)
├── scripts/
│   └── start-dashboard.cmd  # one-click launcher
├── docs/                    # design specs & plans
├── examples/                # security.toml template
├── CHANGELOG.md             # release notes
├── Cargo.toml               # Rust workspace
├── pyproject.toml           # Python package (maturin)
└── README.md                # ← you are here
```

---

## ⚠️ Known Limitations

- **Two input implementations**: the MCP server (`mcp-server/`) drives input via
  `pyautogui`, while the Rust core uses `enigo`. Behavior may differ slightly
  (speed, modifier handling); new Rust capabilities don't automatically appear
  in the MCP server.
- **`prompt` permissions**: per-app `prompt` policy fails closed (treated as
  denied) — interactive user confirmation is not yet implemented in the Rust core.
  It is reported distinctly from a hard `deny` so callers can route it later.
- **`verify_target` scope**: only send-class keys (`enter` / `ctrl+enter` /
  `send` / `submit` / `return`) are gated before sending. Click/type rely on the
  see→act→see audit loop + fail-safe corner instead.
- **Hotkey blocklist matching**: blocked combos are normalized (sorted + joined),
  so order swaps are handled; loop detection only counts same-position clicks
  (drag+click combos are not caught).
- **Windows-only**: window management uses Win32; macOS/Linux are stubs.

## 📄 License

MIT — see [LICENSE](LICENSE).

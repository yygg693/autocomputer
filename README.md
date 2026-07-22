# autocomputer 🦀🐍🌐

**AI-driven desktop GUI automation — Rust core + Python SDK + HTML5 Dashboard.**

> No black box. No subscription. Your computer, your rules.

[![Rust](https://img.shields.io/badge/Rust-1.97-orange.svg)](https://www.rust-lang.org/)
[![Python](https://img.shields.io/badge/Python-3.9+-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/Tests-56%2F56-brightgreen.svg)](#)
[![Clippy](https://img.shields.io/badge/Clippy-zero%20warnings-success.svg)](#)
[![Platform](https://img.shields.io/badge/Platform-Windows%2010%2F11-blueviolet.svg)](#)

---

## Why autocomputer?

Most GUI automation tools fall into two camps: **proprietary cloud services** that send your screen to remote servers, or **fragile coordinate-based scripts** that break the moment your window moves. autocomputer takes a third path:

- 🦀 **Rust core** for sub-10ms screenshots and reliable system calls
- 🐍 **Python SDK** for rapid scripting and AI integration
- 👁️ **Visual feedback loop** — screenshot → AI vision → action → verify
- 🛡️ **Built-in safety** — bounds clamping, loop detection, rate limiting, hotkey blocking

## ✨ Feature Map

### Rust Core (`crates/ac-core/`)

| Module | File | What it does | Performance |
|--------|------|-------------|-------------|
| **capture** | `capture.rs` | Multi-monitor screenshot via xcap/DXGI, region crop, PNG encode, screen resolution | ~8ms per frame |
| **input** | `input.rs` | Mouse: move, click, drag, scroll, position. Keyboard: type, press, hotkey. Chinese text via clipboard | — |
| **window** | `window.rs` | Windows API: enumerate, focus, move, resize, launch applications | — |
| **security** | `security.rs` | Bounds check & clamp, click loop detection (same position × N), rate limiter, hotkey blocklist, SQLite audit | — |
| **image_proc** | `image_proc.rs` | Pixel-level diff with threshold, dHash (difference hash), Hamming distance, NCC template matching, change detection | — |

### Python SDK (`python/autocomputer/`)

| Package | Purpose | Key APIs |
|---------|---------|----------|
| `agent/` | CoT (Chain-of-Thought) context collection, action planning, state tracking | `Agent.run(task)`, `ScreenContext.capture()`, `StateTracker` |
| `perception/` | 4-backend OCR: PaddleOCR (Chinese-optimized), EasyOCR (multilingual), Tesseract (lightweight), LLM Vision (GPT-4V/Claude) | `PerceptionManager.list_available()`, `pm.recognize()`, `pm.get_backend()` |
| `record/` | ActionFlow JSON v1.0 format: intent-based recording, smart replay (OCR → template → fallback), flow compression | `FlowRecorder.record()`, `replay()`, `compress()` |
| `llm/` | Playwright-based browser automation via CDP | `Browser.launch()`, `.goto()`, `.click()`, `.screenshot()` |
| `cli/` | typer CLI with plugin CommandRegistry, aliases, category grouping | `ac version`, `ac see`, `ac monitors`, `ac serve` |
| `server.py` | Zero-dependency HTTP API server bridging GUI ↔ Rust core | `GET /api/status`, `/capture`, `/monitors`, `POST /api/execute` |

### Dashboard (`gui/`)

HTML5 single-page app — no build step, open in browser directly:

| Page | What it shows |
|------|--------------|
| 📊 Dashboard | Real-time system status, Rust core health, quick actions |
| ✏️ Editor | Drag-and-drop step builder: Click / Type / Press / Wait / Scroll / Move |
| 📋 Flows | Saved flow library, replay, JSON export/import |
| 👁️ Monitor | Live operation log with severity coloring (info/ok/warn/error) |
| 🛡️ Security | Hotkey blocklist, loop thresholds, rate limit config, audit stats |

---

## 🚀 Quick Start

### Requirements

- **Rust** 1.97+ (`rustup default stable`)
- **Python** 3.9+
- **Windows** 10 or 11 (macOS/Linux window APIs are stubs — PRs welcome!)

### One-command setup

```bash
git clone https://github.com/yygg693/autocomputer.git
cd autocomputer

pip install maturin pytest typer rich
maturin develop -m crates/ac-core/Cargo.toml
pip install -e .
```

### Verify

```bash
python -m autocomputer version
# autocomputer v0.8.0
# Rust core: ✅ loaded (5 modules)

python -m pytest python/tests/ -q
# 27 passed

cargo test --workspace
# 29 passed

cargo clippy --workspace -- -D warnings
# zero warnings
```

### Launch the Dashboard

```bash
python -m autocomputer serve --port 8765
# 🦀 autocomputer API Server v0.8.0
# 📡 Listening on http://127.0.0.1:8765
# 🌐 GUI: http://127.0.0.1:8765
# 📋 API: http://127.0.0.1:8765/api/status
```

Open `http://127.0.0.1:8765` in your browser.

---

## 📖 Usage Examples

### Python SDK — Screenshot & Click

```python
from autocomputer.core import capture_screen, mouse_click, keyboard_type

# Capture primary monitor
result = capture_screen(0)
print(f"{result.width}x{result.height}, {len(result.png)} bytes")

# Click and type
mouse_click(500, 300)
keyboard_type("Hello World")
```

### Python SDK — Security (built into Rust core)

```python
from autocomputer.agent.core import AgentExecutor

# Security is enabled automatically — one call at startup
AgentExecutor.enable_security("security.toml")  # loads 7-layer defense

# All clicks/presses now go through bounds clamping,
# loop detection, rate limiting, and hotkey blocking
from autocomputer.core import mouse_click
mouse_click(100, 200)  # automatically guarded
```

### Python SDK — Agent Loop

```python
from autocomputer.agent.core import Agent

agent = Agent()
plan = agent.plan("Open Notepad and type 'Hello'")

for step in plan.steps:
    agent.execute(step.action, **step.params)
    agent.verify(step.expected_state)
```

### Record & Replay

```python
from autocomputer.record.engine import FlowRecorder

# Record a flow
recorder = FlowRecorder()
recorder.start()
# ... perform actions manually ...
recorder.stop()
recorder.save("my_flow.json")

# Replay with smart matching
recorder.load("my_flow.json")
recorder.replay(speed=2.0, verify=True)
```

### HTTP API

```bash
# System status
curl http://127.0.0.1:8765/api/status

# Screenshot (returns base64 PNG)
curl http://127.0.0.1:8765/api/capture

# Execute an action
curl -X POST http://127.0.0.1:8765/api/execute \
  -H "Content-Type: application/json" \
  -d '{"action":"click","params":{"x":100,"y":200}}'
```

---

## 🏗 Architecture

```
┌────────────────────────────────────────────┐
│  HTML5 Dashboard (5 pages, glass design)    │
│  ────────────────────────────────────────  │
│  HTTP API Server (Python stdlib, 0 deps)   │
├────────────────────────────────────────────┤
│  Python SDK (agent · perception · record)  │
│  ├─ Agent: CoT context → plan → execute    │
│  ├─ Perception: 4 OCR backends             │
│  ├─ Record: ActionFlow v1.0                │
│  ├─ LLM: Playwright browser automation     │
│  └─ CLI: typer + plugin registry           │
├────────────────────────────────────────────┤
│  🦀 Rust Core (PyO3 → _core.pyd)           │
│  ├─ capture     · xcap DXGI (~8ms)         │
│  ├─ input       · enigo + clipboard        │
│  ├─ window      · Windows API              │
│  ├─ security    · guard + SQLite audit     │
│  └─ image_proc  · diff / hash / match      │
└────────────────────────────────────────────┘
```

Data flow for a typical "click" action:

```
User request → Python SDK → _core.pyd (Rust) → Win32 API → actual mouse event
                        ← screenshot (PNG) ← xcap DXGI ← framebuffer
           → verify (image_proc diff) → next action or retry
```

---

## 🛡️ Security Model

autocomputer ships with a 7-layer defense:

| Layer | Mechanism | What it prevents |
|-------|-----------|-----------------|
| 1. **Fail-safe corner** | Click (0,0) to instantly abort | Runaway automation |
| 2. **Loop detection** | Block click if same position > N times | Infinite click loops |
| 3. **Rate limiting** | Enforce minimum interval (default 100ms) | Rapid-fire spam |
| 4. **Hotkey blocking** | Block dangerous key combos (alt+f4, win+l, …) | Accidental logout/shutdown |
| 5. **App permissions** | Per-app allow/deny/prompt rules | Unauthorized app control |
| 6. **Audit logging** | SQLite with timestamps, retentions | Post-mortem analysis |
| 7. **Bounds clamping** | Clamp all coordinates to screen dimensions | Off-screen clicks |

Configuration via TOML — see [`examples/security.toml`](examples/security.toml).

---

## 🧪 Testing

| Suite | Framework | Count | Coverage |
|-------|-----------|-------|----------|
| Rust unit tests | `cargo test` | 29 | capture (5), image_proc (9), security (7), input (8) |
| Python tests | `pytest` | 27 | core, sdk, record, perception, agent |
| **Total** | | **56** | all passing |

```bash
cargo test --workspace     # 29 tests, 0 failures
pytest python/tests/ -q    # 27 tests, 0 failures
cargo clippy --workspace   # 0 warnings
```

---

## 🔧 Development

```bash
# Build everything
maturin develop -m crates/ac-core/Cargo.toml

# Run with hot reload (Python)
pip install -e .

# Before committing
cargo fmt --all
cargo clippy --workspace -- -D warnings
cargo test --workspace
pytest python/tests/
```

---

## 📂 Project Structure

```text
autocomputer/
├── crates/
│   └── ac-core/              # Main Rust crate (capture, input, window, security, image_proc)
├── python/
│   ├── autocomputer/         # Python SDK
│   │   ├── agent/            # CoT executor + memory + profiling
│   │   ├── cli/              # typer CLI (10 commands)
│   │   ├── core/             # Rust bridge (_core.pyd)
│   │   ├── llm/              # Playwright automation
│   │   ├── perception/       # OCR backends (4 engines)
│   │   ├── plugins/          # Plugin registry (entry_points)
│   │   ├── record/           # ActionFlow v1.0
│   │   ├── server.py         # HTTP API server
│   │   └── utils/            # Logging, config, paths
│   └── tests/                # Python test suite (27 tests)
├── gui/
│   └── index.html            # HTML5 Dashboard (5 pages)
├── .github/workflows/        # CI + repo metadata
├── examples/
│   └── security.toml         # Security policy template
├── Cargo.toml                # Rust workspace (1 crate)
├── pyproject.toml            # Python package config
└── README.md                 # ← you are here
```

---

## 📄 License

MIT — see [LICENSE](LICENSE) for details.

---

*This is the Rust rewrite of [autocomputer](https://github.com/yygg693/autocomputer) (originally a Python-only framework). The legacy Python version is available in the `python-legacy` branch.*

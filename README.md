# autocomputer 🦀🐍🌐

**AI-driven desktop GUI automation — Rust core + Python SDK + HTML5 Dashboard.**

> No black box. No subscription. Your computer, your rules.

[![Rust](https://img.shields.io/badge/Rust-1.97-orange.svg)](https://www.rust-lang.org/)
[![Python](https://img.shields.io/badge/Python-3.9+-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/Tests-48%2F48-brightgreen.svg)](#)
[![Clippy](https://img.shields.io/badge/Clippy-zero%20warnings-brightgreen.svg)](#)

## ✨ Features

| Category | Module | Highlights |
|----------|--------|-----------|
| 🖥️ **Capture** | `ac-core/capture.rs` | Multi-monitor, DXGI (~8ms), region crop, PNG encode |
| 🖱️ **Input** | `ac-core/input.rs` | Mouse (7 ops) + Keyboard (4 modes), Chinese clipboard |
| 🪟 **Window** | `ac-core/window.rs` | Windows API: enum, focus, move, resize, launch_app |
| 🛡️ **Security** | `ac-core/security.rs` | Bounds, loop, rate, hotkey guards + SQLite audit |
| 🎨 **Vision** | `ac-core/image_proc.rs` | Pixel diff, dHash, Hamming, template match (NCC) |
| 🤖 **Agent** | `agent/` | CoT context collection, plan executor, state tracker |
| 📋 **Record** | `record/` | ActionFlow JSON v1.0, intent recording, replay, compress |
| 👁️ **Perception** | `perception/` | 4-backend OCR (PaddleOCR/EasyOCR/Tesseract/LLM Vision) |
| 🌐 **Browser** | `llm/` | Playwright-based web automation |
| 🎛️ **Dashboard** | `gui/` | HTML5 SPA: 5 pages, glass design, live Web API |

## 🚀 Quick Start

### Prerequisites
- Rust 1.97+
- Python 3.9+
- Windows 10/11

### Install & Run

```bash
# Clone
git clone https://github.com/yygg693/autocomputer.git
cd autocomputer

# Install Python deps & build Rust
pip install maturin pytest typer rich pydantic
maturin develop -m crates/ac-core/Cargo.toml
pip install -e .

# Verify (48 tests)
python -m pytest python/tests/
cargo test --workspace
cargo clippy --workspace -- -D warnings

# Start Dashboard + API
python -m autocomputer serve --port 8765
# Open http://127.0.0.1:8765
```

### CLI Commands

```bash
python -m autocomputer version     # Show version + Rust core status
python -m autocomputer see         # Screenshot capture
python -m autocomputer monitors    # List all monitors
python -m autocomputer serve       # Start API + GUI server
```

## 🏗 Architecture

```
┌────────────────────────────────────────────┐
│  HTML5 Dashboard (5 pages, glass design)    │
│  ────────────────────────────────────────  │
│  Python HTTP API (/api/status /capture …)  │
├────────────────────────────────────────────┤
│  Python SDK                                │
│  ├─ agent (CoT executor)                   │
│  ├─ perception (OCR backends)              │
│  ├─ record (ActionFlow v1.0)               │
│  ├─ llm (Playwright browser)               │
│  └─ cli (typer + CommandRegistry)          │
├────────────────────────────────────────────┤
│  🦀 Rust Core (PyO3 → _core.pyd)           │
│  ├─ capture     (xcap DXGI)                │
│  ├─ input       (enigo + clipboard)        │
│  ├─ window      (Windows API)              │
│  ├─ security    (guard + SQLite)           │
│  └─ image_proc  (diff/hash/match)          │
└────────────────────────────────────────────┘
```

## 🧪 Testing

```bash
cargo test --workspace    # 21 Rust tests
cargo clippy --workspace  # zero warnings
pytest python/tests/      # 27 Python tests
# ────────────────────────
# Total: 48 tests, all passing
```

## 📄 License

MIT — see [LICENSE](LICENSE) for details.

---

*This is the Rust rewrite of the [original autocomputer](https://github.com/yygg693/autocomputer) Python framework. The Python-only version is preserved in the `python-legacy` branch.*

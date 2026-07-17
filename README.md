# autocomputer 🦀🐍🌐

**AI-driven desktop GUI automation — Rust core + Python SDK + HTML5 Dashboard.**

> No black box. No subscription. Your computer, your rules.

## Architecture

```
┌─────────────────────────────────────────────┐
│  🐍 Python SDK (CLI, Agent, Record, LLM)    │
│  ─────────────────────────────────────────  │
│  🌐 HTML5 Dashboard (Record Editor, Logs)    │
├─────────────────────────────────────────────┤
│  🦀 Rust Core                               │
│  ├─ ac-core      (capture, input, window,   │
│  │                image_proc, security)      │
│  ├─ ac-security  (guard, audit, sandbox)    │
│  └─ ac-browser   (CDP client)               │
└─────────────────────────────────────────────┘
```

## Quick Start

### Prerequisites
- Rust toolchain (1.97+)
- Python 3.9+
- Windows 10/11 (macOS/Linux window APIs incomplete)

### Setup

```bash
# Clone & build
git clone https://github.com/yygg693/autocomputer.git
cd autocomputer
pip install maturin pytest typer rich pydantic
maturin develop -m crates/ac-core/Cargo.toml
pip install -e .

# Verify
python -m autocomputer version
python -m pytest python/tests/
```

### Start the Dashboard

```bash
python -m autocomputer serve --port 8765
# Open http://127.0.0.1:8765 in browser
```

## Features

| Module | Capabilities |
|--------|-------------|
| **capture** | Multi-monitor screenshot, region capture (xcap DXGI, ~8ms) |
| **input** | Mouse (move/click/drag/scroll/position), Keyboard (type/press/hotkey), Chinese via clipboard |
| **window** | Window enumeration/focus/move/resize (Windows API) |
| **security** | Bounds check, loop detection, rate limit, hotkey blocking, SQLite audit |
| **image_proc** | Pixel diff, dHash, Hamming distance, template match, change detection |
| **agent** | CoT context collection, action planning, state tracking |
| **record** | ActionFlow JSON v1.0, intent-based recording, replay, compression |
| **perception** | Multi-backend OCR (PaddleOCR/EasyOCR/Tesseract/LLM Vision) |
| **browser** | Playwright-based web automation |

## Development

```bash
make dev      # Install dev dependencies
make build    # Build all Rust crates
make test     # Run all tests (Rust 21 + Python 27 = 48 total)
make lint     # clippy + ruff + mypy
```

## License

MIT — see [LICENSE](LICENSE) for details.

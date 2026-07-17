.PHONY: dev build test lint clean

# ── Rust toolchain path ──
CARGO = $(HOME)/.cargo/bin/cargo
RUSTC = $(HOME)/.cargo/bin/rustc

# ── Python ──
VENV = .venv
PIP = $(VENV)/Scripts/pip
PYTHON = $(VENV)/Scripts/python

dev: $(VENV) build-rust install-py
	@echo "✅ autocomputer dev environment ready"
	@$(PYTHON) -c "from autocomputer import __version__; print(f'autocomputer v{__version__}')"

$(VENV):
	python -m venv $(VENV)
	$(PIP) install --upgrade pip maturin

build-rust:
	$(CARGO) build --workspace
	@echo "✅ Rust crates built"

install-py:
	$(PIP) install maturin
	cd $(CURDIR) && $(PYTHON) -m maturin develop
	$(PIP) install -e ".[dev]"
	@echo "✅ Python package installed"

debug-rust:
	$(CARGO) build --workspace 2>&1 | head -50

build:
	$(CARGO) build --workspace --release
	$(PIP) install maturin
	cd $(CURDIR) && $(PYTHON) -m maturin develop --release

test: test-rust test-py

test-rust:
	$(CARGO) test --workspace

test-py:
	$(PYTHON) -m pytest python/tests/ -v

lint: lint-rust lint-py

lint-rust:
	$(CARGO) clippy --workspace -- -D warnings
	$(CARGO) fmt --all -- --check

lint-py:
	$(PYTHON) -m ruff check python/
	$(PYTHON) -m mypy python/

clean:
	$(CARGO) clean
	rm -rf $(VENV) dist build .maturin
	@echo "✅ Cleaned"

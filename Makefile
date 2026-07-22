.PHONY: dev build test lint clean

# ── Rust toolchain path ──
CARGO = $(HOME)/.cargo/bin/cargo
RUSTC = $(HOME)/.cargo/bin/rustc

# ── Python ──
VENV = .venv
PYTHON = python
PIP = $(PYTHON) -m pip

# Cross-platform venv setup
ifeq ($(OS),Windows_NT)
    VENV_ACTIVATE = $(VENV)\Scripts\activate
    VENV_PYTHON = $(VENV)\Scripts\python
else
    VENV_ACTIVATE = $(VENV)/bin/activate
    VENV_PYTHON = $(VENV)/bin/python
endif

dev: $(VENV) build install
	@echo "✅ autocomputer dev environment ready"
	@$(VENV_PYTHON) -c "from autocomputer import __version__; print(f'autocomputer v{__version__}')"

$(VENV):
	$(PYTHON) -m venv $(VENV)
	$(VENV_PYTHON) -m pip install --upgrade pip maturin

build:
	$(CARGO) build

install:
	cd $(CURDIR) && $(VENV_PYTHON) -m maturin develop
	$(VENV_PYTHON) -m pip install -e ".[dev]"
	@echo "✅ Python package installed"

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

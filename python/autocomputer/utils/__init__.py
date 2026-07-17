"""
Shared utilities — logging, configuration, paths.
"""

import logging
import os
import sys
from pathlib import Path
from typing import Optional


# ── Logging ──

def get_logger(name: str = "autocomputer", level: int = logging.INFO) -> logging.Logger:
    """Get (or create) a named logger with consistent formatting."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(logging.Formatter(
            "[%(asctime)s] %(levelname)-7s %(name)s | %(message)s",
            datefmt="%H:%M:%S",
        ))
        logger.addHandler(handler)
    logger.setLevel(level)
    return logger


# ── Configuration ──

def config_dir() -> Path:
    """Get the autocomputer config directory (~/.autocomputer)."""
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA", str(Path.home() / "AppData" / "Roaming")))
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config")))
    d = base / "autocomputer"
    d.mkdir(parents=True, exist_ok=True)
    return d


def workspace_dir() -> Path:
    """Get the autocomputer workspace / data directory."""
    d = Path(".autocomputer")
    d.mkdir(parents=True, exist_ok=True)
    return d


def load_toml(path: Path) -> dict:
    """Load a TOML configuration file."""
    try:
        import tomllib  # Python 3.11+
    except ImportError:
        import tomli as tomllib  # type: ignore
    with open(path, "rb") as f:
        return tomllib.load(f)


def find_security_config() -> Optional[Path]:
    """Search for security.toml in standard locations."""
    candidates = [
        config_dir() / "security.toml",
        Path("security.toml"),
        Path("examples") / "security.toml",
    ]
    for p in candidates:
        if p.exists():
            return p
    return None


# ── Version info ──

def version_info() -> dict:
    """Collect version information from Rust core and Python SDK."""
    from autocomputer.core._bridge import _get_rust_attr

    info: dict = {"python_version": sys.version.split()[0], "core_loaded": "no"}

    try:
        rust_version_fn = _get_rust_attr("version")
        if rust_version_fn:
            info["rust_version"] = rust_version_fn()
            info["core_loaded"] = "yes"
    except Exception:
        pass

    return info

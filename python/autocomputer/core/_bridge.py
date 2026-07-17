"""
Bridge layer between Python and Rust core engines.
"""

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

_RUST_AVAILABLE = False


def _try_import_rust() -> bool:
    try:
        import autocomputer.core._core  # type: ignore[import-untyped] # noqa: F401
        global _RUST_AVAILABLE
        _RUST_AVAILABLE = True
        return True
    except ImportError:
        logger.warning("Rust core module not found, running in pure-Python fallback mode.")
        return False


def _get_rust_attr(name: str) -> Any:
    import autocomputer.core._core as _core  # type: ignore[import-untyped]
    if hasattr(_core, name):
        return getattr(_core, name)
    return None


_try_import_rust()


# ── Types ──

_CaptureResult = _get_rust_attr("CaptureResult")
if _CaptureResult is not None:
    CaptureResult = _CaptureResult
else:
    class CaptureResult:  # type: ignore[no-redef]
        width: int = 0
        height: int = 0
        raw: bytes = b""
        png: bytes = b""


_MonitorInfo = _get_rust_attr("MonitorInfo")
if _MonitorInfo is not None:
    MonitorInfo = _MonitorInfo
else:
    class MonitorInfo:  # type: ignore[no-redef]
        index: int = 0
        name: str = ""
        width: int = 0
        height: int = 0
        x: int = 0
        y: int = 0
        is_primary: bool = False
        scale_factor: float = 1.0


# ── Helper ──

def _call(name: str, *args: Any, **kwargs: Any) -> Any:
    fn = _get_rust_attr(name)
    if fn is not None:
        return fn(*args, **kwargs)
    return None


# ── Capture ──

def list_monitors() -> list[Any]:
    return _call("list_monitors") or []

def capture_screen(monitor_index: Optional[int] = None) -> CaptureResult:
    return _call("capture_screen", monitor_index) or CaptureResult()

def capture_region(x: int, y: int, w: int, h: int) -> CaptureResult:
    return _call("capture_region", x, y, w, h) or CaptureResult()

def save_screenshot(monitor_index: Optional[int] = None, path: str = "screenshot.png") -> str:
    return _call("save_screenshot", monitor_index, path) or path

def screen_size() -> tuple[int, int]:
    return _call("screen_size") or (0, 0)

# ── Mouse ──

def mouse_move(x: int, y: int, duration_ms: Optional[int] = None) -> None:
    _call("mouse_move", x, y, duration_ms)

def mouse_click(x: Optional[int] = None, y: Optional[int] = None, button: str = "left") -> None:
    _call("mouse_click", x, y, button)

def mouse_double_click(x: Optional[int] = None, y: Optional[int] = None, button: str = "left") -> None:
    _call("mouse_double_click", x, y, button)

def mouse_right_click(x: Optional[int] = None, y: Optional[int] = None) -> None:
    _call("mouse_right_click", x, y)

def mouse_drag(x1: int, y1: int, x2: int, y2: int, duration_ms: Optional[int] = None) -> None:
    _call("mouse_drag", x1, y1, x2, y2, duration_ms)

def mouse_scroll(clicks: int) -> None:
    _call("mouse_scroll", clicks)

def mouse_position() -> tuple[int, int]:
    return _call("mouse_position") or (0, 0)

# ── Keyboard ──

def keyboard_type(text: str, method: str = "auto") -> None:
    _call("keyboard_type", text, method)

def keyboard_press(key: str) -> None:
    _call("keyboard_press", key)

def keyboard_down(key: str) -> None:
    _call("keyboard_down", key)

def keyboard_up(key: str) -> None:
    _call("keyboard_up", key)

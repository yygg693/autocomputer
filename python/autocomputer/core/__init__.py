"""Core module — bridges Rust engines to Python."""

from autocomputer.core._bridge import (
    # Capture
    CaptureResult,
    MonitorInfo,
    capture_region,
    capture_screen,
    list_monitors,
    save_screenshot,
    screen_size,
    # Mouse
    mouse_click,
    mouse_double_click,
    mouse_drag,
    mouse_move,
    mouse_position,
    mouse_right_click,
    mouse_scroll,
    # Keyboard
    keyboard_down,
    keyboard_press,
    keyboard_type,
    keyboard_up,
)

__all__ = [
    # Capture
    "CaptureResult",
    "MonitorInfo",
    "capture_region",
    "capture_screen",
    "list_monitors",
    "save_screenshot",
    "screen_size",
    # Mouse
    "mouse_move",
    "mouse_click",
    "mouse_double_click",
    "mouse_right_click",
    "mouse_drag",
    "mouse_scroll",
    "mouse_position",
    # Keyboard
    "keyboard_type",
    "keyboard_press",
    "keyboard_down",
    "keyboard_up",
]

//! Mouse & keyboard input via enigo. Clipboard for Chinese/Unicode.
//!
//! Exports to Python via PyO3.

use enigo::{
    Axis, Coordinate, Direction, Enigo, Key, Keyboard, Mouse, Settings,
};
use pyo3::prelude::*;
use std::time::Duration;

fn input_err(e: impl std::fmt::Display) -> PyErr {
    PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(e.to_string())
}

// ── Helpers ──

fn en() -> Result<Enigo, PyErr> {
    Enigo::new(&Settings::default()).map_err(input_err)
}

fn parse_button(btn: &str) -> enigo::Button {
    match btn {
        "right" => enigo::Button::Right,
        "middle" => enigo::Button::Middle,
        _ => enigo::Button::Left,
    }
}

/// Key name mapping — Chinese → enigo Key
fn parse_key(name: &str) -> Result<Key, PyErr> {
    let key = match name {
        "enter" | "return" | "回车" => Key::Return,
        "space" | "空格" => Key::Space,
        "backspace" | "退格" => Key::Backspace,
        "delete" | "删除" => Key::Delete,
        "tab" | "制表" => Key::Tab,
        "escape" | "esc" | "取消" => Key::Escape,
        "up" | "上" => Key::UpArrow,
        "down" | "下" => Key::DownArrow,
        "left" | "左" => Key::LeftArrow,
        "right" | "右" => Key::RightArrow,
        "home" => Key::Home,
        "end" => Key::End,
        "pageup" | "pgup" => Key::PageUp,
        "pagedown" | "pgdn" => Key::PageDown,
        "f1" => Key::F1,
        "f2" => Key::F2,
        "f3" => Key::F3,
        "f4" => Key::F4,
        "f5" => Key::F5,
        "f6" => Key::F6,
        "f7" => Key::F7,
        "f8" => Key::F8,
        "f9" => Key::F9,
        "f10" => Key::F10,
        "f11" => Key::F11,
        "f12" => Key::F12,
        "win" | "windows" | "cmd" | "super" => Key::Meta,
        "alt" => Key::Alt,
        "ctrl" | "control" => Key::Control,
        "shift" => Key::Shift,
        "capslock" | "caps" => Key::CapsLock,
        other if other.len() == 1 => {
            let ch = other.chars().next().unwrap();
            if ch.is_ascii_alphabetic() {
                Key::Unicode(ch)
            } else {
                return Err(PyErr::new::<pyo3::exceptions::PyValueError, _>(
                    format!("Unknown key: {name}"),
                ));
            }
        }
        _ => {
            return Err(PyErr::new::<pyo3::exceptions::PyValueError, _>(
                format!("Unknown key: {name}"),
            ))
        }
    };
    Ok(key)
}

// ── Mouse ──

/// Move mouse to absolute coordinates, with optional smooth duration.
#[pyfunction]
pub fn mouse_move(x: i32, y: i32, duration_ms: Option<u64>) -> PyResult<()> {
    let mut en = en()?;
    if let Some(ms) = duration_ms {
        en.move_mouse(x, y, Coordinate::Abs).map_err(input_err)?;
        std::thread::sleep(Duration::from_millis(ms));
    } else {
        en.move_mouse(x, y, Coordinate::Abs).map_err(input_err)?;
    }
    Ok(())
}

/// Click at current position or specified coordinates.
#[pyfunction]
pub fn mouse_click(x: Option<i32>, y: Option<i32>, button: Option<String>) -> PyResult<()> {
    let mut en = en()?;
    let btn = parse_button(button.as_deref().unwrap_or("left"));
    if let (Some(px), Some(py)) = (x, y) {
        en.move_mouse(px, py, Coordinate::Abs).map_err(input_err)?;
    }
    en.button(btn, Direction::Click).map_err(input_err)?;
    Ok(())
}

/// Double-click.
#[pyfunction]
pub fn mouse_double_click(x: Option<i32>, y: Option<i32>, button: Option<String>) -> PyResult<()> {
    let mut en = en()?;
    let btn = parse_button(button.as_deref().unwrap_or("left"));
    if let (Some(px), Some(py)) = (x, y) {
        en.move_mouse(px, py, Coordinate::Abs).map_err(input_err)?;
    }
    en.button(btn, Direction::Click).map_err(input_err)?;
    std::thread::sleep(Duration::from_millis(50));
    en.button(btn, Direction::Click).map_err(input_err)?;
    Ok(())
}

/// Right-click.
#[pyfunction]
pub fn mouse_right_click(x: Option<i32>, y: Option<i32>) -> PyResult<()> {
    mouse_click(x, y, Some("right".into()))
}

/// Drag from (x1,y1) to (x2,y2).
#[pyfunction]
pub fn mouse_drag(
    x1: i32,
    y1: i32,
    x2: i32,
    y2: i32,
    duration_ms: Option<u64>,
) -> PyResult<()> {
    let mut en = en()?;
    en.move_mouse(x1, y1, Coordinate::Abs).map_err(input_err)?;
    en.button(enigo::Button::Left, Direction::Press)
        .map_err(input_err)?;
    if let Some(ms) = duration_ms {
        en.move_mouse(x2, y2, Coordinate::Abs).map_err(input_err)?;
        std::thread::sleep(Duration::from_millis(ms));
    } else {
        en.move_mouse(x2, y2, Coordinate::Abs).map_err(input_err)?;
    }
    en.button(enigo::Button::Left, Direction::Release)
        .map_err(input_err)?;
    Ok(())
}

/// Scroll — positive = up, negative = down.
#[pyfunction]
pub fn mouse_scroll(clicks: i32) -> PyResult<()> {
    let mut en = en()?;
    en.scroll(clicks, Axis::Vertical).map_err(input_err)?;
    Ok(())
}

/// Get current mouse position.
#[pyfunction]
pub fn mouse_position() -> PyResult<(i32, i32)> {
    let en = en()?;
    let loc = en.location().map_err(input_err)?;
    Ok((loc.0, loc.1))
}

// ── Keyboard ──

/// Type text. Uses clipboard for non-ASCII (Chinese/emoji), typewrite for ASCII.
///
/// Methods:
///   "auto" (default) — auto-detect
///   "clipboard" — force clipboard paste
///   "typewrite" — force character-by-character typing
#[pyfunction]
pub fn keyboard_type(text: &str, method: Option<String>) -> PyResult<()> {
    let method = method.as_deref().unwrap_or("auto");
    let needs_clipboard = method == "clipboard"
        || (method == "auto" && text.chars().any(|c| !c.is_ascii() || c.is_control()));

    if needs_clipboard {
        // Copy to clipboard and paste (Ctrl+V)
        let mut clipboard = arboard::Clipboard::new()
            .map_err(|e| input_err(e.to_string()))?;
        clipboard.set_text(text)
            .map_err(|e| input_err(e.to_string()))?;
        // Small delay for clipboard to settle
        std::thread::sleep(Duration::from_millis(50));

        let mut en = en()?;
        en.key(Key::Control, Direction::Press).map_err(input_err)?;
        en.key(Key::Unicode('v'), Direction::Click).map_err(input_err)?;
        en.key(Key::Control, Direction::Release).map_err(input_err)?;
    } else {
        let mut en = en()?;
        for c in text.chars() {
            en.key(Key::Unicode(c), Direction::Click).map_err(input_err)?;
            std::thread::sleep(Duration::from_millis(5));
        }
    }
    Ok(())
}

/// Press a single key or key combo like "ctrl+c", "alt+tab".
#[pyfunction]
pub fn keyboard_press(key_str: &str) -> PyResult<()> {
    let mut en = en()?;

    // Handle combos: "ctrl+c", "alt+tab", "ctrl+shift+esc", etc.
    if key_str.contains('+') {
        let parts: Vec<&str> = key_str.split('+').map(str::trim).collect();
        // Press all modifiers first
        for part in &parts {
            let key = parse_key(part)?;
            en.key(key, Direction::Press).map_err(input_err)?;
        }
        // Release in reverse order
        for part in parts.iter().rev() {
            let key = parse_key(part)?;
            en.key(key, Direction::Release).map_err(input_err)?;
        }
    } else {
        let key = parse_key(key_str)?;
        en.key(key, Direction::Click).map_err(input_err)?;
    }
    Ok(())
}

/// Press and hold a key, then release (useful for held modifiers).
#[pyfunction]
pub fn keyboard_down(key_str: &str) -> PyResult<()> {
    let mut en = en()?;
    let key = parse_key(key_str)?;
    en.key(key, Direction::Press).map_err(input_err)?;
    Ok(())
}

#[pyfunction]
pub fn keyboard_up(key_str: &str) -> PyResult<()> {
    let mut en = en()?;
    let key = parse_key(key_str)?;
    en.key(key, Direction::Release).map_err(input_err)?;
    Ok(())
}

//! ac-core: autocomputer 核心引擎
//!
//! 负责所有系统级操作：
//! - 截图捕获（xcap）
//! - 键盘鼠标输入（enigo）
//! - 窗口管理（Windows API + 跨平台 stub）
//! - 图像处理（image-rs）
//! - 连续监控管线

mod capture;
mod image_proc;
mod input;
mod security;
mod window;

use pyo3::prelude::*;

#[pymodule]
fn _core(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add("__version__", env!("CARGO_PKG_VERSION"))?;
    m.add("__rust_version__", "1.97")?;

    // ── Types ──
    m.add_class::<capture::CaptureResult>()?;
    m.add_class::<capture::MonitorInfo>()?;
    m.add_class::<window::WindowInfo>()?;
    m.add_class::<image_proc::DiffRegion>()?;
    m.add_class::<image_proc::DiffResult>()?;
    m.add_class::<image_proc::MatchResult>()?;

    // ── Capture ──
    m.add_function(wrap_pyfunction!(capture::list_monitors, m)?)?;
    m.add_function(wrap_pyfunction!(capture::capture_screen, m)?)?;
    m.add_function(wrap_pyfunction!(capture::capture_region, m)?)?;
    m.add_function(wrap_pyfunction!(capture::save_screenshot, m)?)?;
    m.add_function(wrap_pyfunction!(capture::screen_size, m)?)?;

    // ── Input: Mouse ──
    m.add_function(wrap_pyfunction!(input::mouse_move, m)?)?;
    m.add_function(wrap_pyfunction!(input::mouse_click, m)?)?;
    m.add_function(wrap_pyfunction!(input::mouse_double_click, m)?)?;
    m.add_function(wrap_pyfunction!(input::mouse_right_click, m)?)?;
    m.add_function(wrap_pyfunction!(input::mouse_drag, m)?)?;
    m.add_function(wrap_pyfunction!(input::mouse_scroll, m)?)?;
    m.add_function(wrap_pyfunction!(input::mouse_position, m)?)?;

    // ── Input: Keyboard ──
    m.add_function(wrap_pyfunction!(input::keyboard_type, m)?)?;
    m.add_function(wrap_pyfunction!(input::keyboard_press, m)?)?;
    m.add_function(wrap_pyfunction!(input::keyboard_down, m)?)?;
    m.add_function(wrap_pyfunction!(input::keyboard_up, m)?)?;

    // ── Window ──
    m.add_function(wrap_pyfunction!(window::window_list, m)?)?;
    m.add_function(wrap_pyfunction!(window::window_focus, m)?)?;
    m.add_function(wrap_pyfunction!(window::window_move, m)?)?;
    m.add_function(wrap_pyfunction!(window::window_resize, m)?)?;
    m.add_function(wrap_pyfunction!(window::window_get_rect, m)?)?;
    m.add_function(wrap_pyfunction!(window::launch_app, m)?)?;

    // ── Security ──
    m.add_function(wrap_pyfunction!(security::security_init, m)?)?;
    m.add_function(wrap_pyfunction!(security::guard_click, m)?)?;
    m.add_function(wrap_pyfunction!(security::guard_hotkey, m)?)?;
    m.add_function(wrap_pyfunction!(security::guard_app_action, m)?)?;
    m.add_function(wrap_pyfunction!(security::security_reset, m)?)?;

    // ── Image Processing ──
    m.add_function(wrap_pyfunction!(image_proc::image_diff, m)?)?;
    m.add_function(wrap_pyfunction!(image_proc::dhash, m)?)?;
    m.add_function(wrap_pyfunction!(image_proc::hamming_distance, m)?)?;
    m.add_function(wrap_pyfunction!(image_proc::template_match, m)?)?;
    m.add_function(wrap_pyfunction!(image_proc::has_changed, m)?)?;

    Ok(())
}

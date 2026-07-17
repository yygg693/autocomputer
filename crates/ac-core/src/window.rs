//! Window management — list, focus, move, resize, launch apps.
//! Windows via `windows` crate. macOS/Linux stubbed.

#![allow(unused_must_use, unused_variables, unused_mut)]

use pyo3::prelude::*;

// ── Python types ──

#[pyclass]
#[derive(Clone)]
pub struct WindowInfo {
    #[pyo3(get)] pub title: String,
    #[pyo3(get)] pub x: i32,
    #[pyo3(get)] pub y: i32,
    #[pyo3(get)] pub width: i32,
    #[pyo3(get)] pub height: i32,
    #[pyo3(get)] pub pid: u32,
    #[pyo3(get)] pub is_visible: bool,
}

#[pymethods]
impl WindowInfo {
    #[new]
    fn new() -> Self {
        WindowInfo { title: String::new(), x: 0, y: 0, width: 0, height: 0, pid: 0, is_visible: false }
    }
}

// ── Windows impl ──

#[cfg(windows)]
mod win32 {
    use super::*;
    use std::ffi::OsString;
    use std::os::windows::ffi::OsStringExt;
    use std::sync::Mutex;
    use windows::core::BOOL;
    use windows::Win32::Foundation::{HWND, LPARAM, RECT};
    use windows::Win32::UI::WindowsAndMessaging::*;

    static WINDOW_LIST: Mutex<Vec<WindowInfo>> = Mutex::new(Vec::new());

    extern "system" fn enum_callback(hwnd: HWND, _lparam: LPARAM) -> BOOL {
        let mut title_buf = [0u16; 512];
        let len = unsafe { GetWindowTextW(hwnd, &mut title_buf) } as usize;
        if len == 0 { return BOOL(1); }

        let title = OsString::from_wide(&title_buf[..len]).to_string_lossy().into_owned();
        let mut rect = RECT::default();
        if unsafe { GetWindowRect(hwnd, &mut rect) }.is_err() { return BOOL(1); }

        let is_visible = unsafe { IsWindowVisible(hwnd) }.as_bool();
        let mut pid: u32 = 0;
        unsafe { GetWindowThreadProcessId(hwnd, Some(&mut pid)) };

        if let Ok(mut list) = WINDOW_LIST.lock() {
            list.push(WindowInfo {
                title,
                x: rect.left,
                y: rect.top,
                width: rect.right - rect.left,
                height: rect.bottom - rect.top,
                pid,
                is_visible,
            });
        }
        BOOL(1)
    }

    pub fn enumerate(filter_title: Option<&str>) -> PyResult<Vec<WindowInfo>> {
        {
            let mut list = WINDOW_LIST.lock().map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(e.to_string()))?;
            list.clear();
        }
        unsafe { EnumWindows(Some(enum_callback), LPARAM(0)) }.map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(e.to_string()))?;

        let mut list = WINDOW_LIST.lock().map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(e.to_string()))?;
        let mut result = std::mem::take(&mut *list);
        if let Some(f) = filter_title {
            let fl = f.to_lowercase();
            result.retain(|w| w.title.to_lowercase().contains(&fl));
        }
        Ok(result)
    }

    fn find_hwnd(title: &str) -> PyResult<HWND> {
        let tl = title.to_lowercase();
        let mut result: Option<HWND> = None;

        extern "system" fn cb(hwnd: HWND, lparam: LPARAM) -> BOOL {
            let (target, found) = unsafe { &mut *(lparam.0 as *mut (String, Option<HWND>)) };
            let mut buf = [0u16; 512];
            let len = unsafe { GetWindowTextW(hwnd, &mut buf) } as usize;
            if len > 0 {
                let t = OsString::from_wide(&buf[..len]).to_string_lossy().into_owned();
                if t.to_lowercase().contains(target.as_str()) {
                    *found = Some(hwnd);
                    return BOOL(0);
                }
            }
            BOOL(1)
        }

        let data = (tl, None);
        let lparam = LPARAM(&data as *const _ as isize);
        unsafe { EnumWindows(Some(cb), lparam) }.map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(e.to_string()))?;

        // We need to extract the result after the callback ran
        // Since the callback modifies data through the pointer, we can access it directly
        let (_title, hwnd_opt) = &data;
        hwnd_opt.ok_or_else(|| PyErr::new::<pyo3::exceptions::PyValueError, _>(format!("Window not found: {title}")))
    }

    pub fn focus(title: &str) -> PyResult<()> {
        let hwnd = find_hwnd(title)?;
        unsafe { ShowWindow(hwnd, SW_RESTORE); ShowWindow(hwnd, SW_SHOW); SetForegroundWindow(hwnd) };
        Ok(())
    }

    pub fn move_window(title: &str, x: i32, y: i32) -> PyResult<()> {
        let hwnd = find_hwnd(title)?;
        let mut rect = RECT::default();
        unsafe { GetWindowRect(hwnd, &mut rect) }.map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(e.to_string()))?;
        let w = rect.right - rect.left;
        let h = rect.bottom - rect.top;
        unsafe { MoveWindow(hwnd, x, y, w, h, true) };
        Ok(())
    }

    pub fn resize_window(title: &str, w: i32, h: i32) -> PyResult<()> {
        let hwnd = find_hwnd(title)?;
        unsafe { MoveWindow(hwnd, 0, 0, w, h, true) };
        Ok(())
    }

    pub fn get_rect(title: &str) -> PyResult<(i32, i32, i32, i32)> {
        let hwnd = find_hwnd(title)?;
        let mut rect = RECT::default();
        unsafe { GetWindowRect(hwnd, &mut rect) }.map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(e.to_string()))?;
        Ok((rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top))
    }
}

#[cfg(not(windows))]
mod win32 {
    use super::*;
    fn not_impl() -> PyErr { PyErr::new::<pyo3::exceptions::PyNotImplementedError, _>("Not implemented on this platform") }
    pub fn enumerate(_f: Option<&str>) -> PyResult<Vec<WindowInfo>> { Ok(Vec::new()) }
    pub fn focus(_t: &str) -> PyResult<()> { Err(not_impl()) }
    pub fn move_window(_t: &str, _x: i32, _y: i32) -> PyResult<()> { Err(not_impl()) }
    pub fn resize_window(_t: &str, _w: i32, _h: i32) -> PyResult<()> { Err(not_impl()) }
    pub fn get_rect(_t: &str) -> PyResult<(i32, i32, i32, i32)> { Err(not_impl()) }
}

// ── PyO3 exports ──

#[pyfunction]
pub fn window_list(filter_title: Option<String>) -> PyResult<Vec<WindowInfo>> {
    win32::enumerate(filter_title.as_deref())
}

#[pyfunction]
pub fn window_focus(title: &str) -> PyResult<()> { win32::focus(title) }

#[pyfunction]
pub fn window_move(title: &str, x: i32, y: i32) -> PyResult<()> { win32::move_window(title, x, y) }

#[pyfunction]
pub fn window_resize(title: &str, w: i32, h: i32) -> PyResult<()> { win32::resize_window(title, w, h) }

#[pyfunction]
pub fn window_get_rect(title: &str) -> PyResult<(i32, i32, i32, i32)> { win32::get_rect(title) }

#[pyfunction]
pub fn launch_app(path: &str) -> PyResult<()> {
    std::process::Command::new(path).spawn()
        .map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(e.to_string()))?;
    Ok(())
}

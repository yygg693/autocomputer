//! Window management — list, focus, move, resize, launch apps.
//! Windows via `windows` crate. macOS/Linux stubbed.

use pyo3::prelude::*;

// ── Python types ──

#[pyclass]
#[derive(Clone)]
pub struct WindowInfo {
    #[pyo3(get)]
    pub title: String,
    #[pyo3(get)]
    pub x: i32,
    #[pyo3(get)]
    pub y: i32,
    #[pyo3(get)]
    pub width: i32,
    #[pyo3(get)]
    pub height: i32,
    #[pyo3(get)]
    pub pid: u32,
    #[pyo3(get)]
    pub is_visible: bool,
}

#[pymethods]
impl WindowInfo {
    #[new]
    fn new() -> Self {
        WindowInfo {
            title: String::new(),
            x: 0,
            y: 0,
            width: 0,
            height: 0,
            pid: 0,
            is_visible: false,
        }
    }
}

// ── Windows impl ──

#[cfg(windows)]
mod win32 {
    use super::*;
    use std::ffi::OsString;
    use std::os::windows::ffi::OsStringExt;
    use std::panic::{AssertUnwindSafe, catch_unwind};
    use windows::Win32::Foundation::{HWND, LPARAM, RECT};
    use windows::Win32::UI::WindowsAndMessaging::*;
    use windows::core::BOOL;

    // ── enumerate ──

    pub fn enumerate(filter_title: Option<&str>) -> PyResult<Vec<WindowInfo>> {
        let mut windows: Vec<WindowInfo> = Vec::new();

        let result = catch_unwind(AssertUnwindSafe(|| unsafe {
            let _ = EnumWindows(
                Some(enum_proc),
                LPARAM(&mut windows as *mut Vec<WindowInfo> as isize),
            );
        }));

        if result.is_err() {
            return Err(PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(
                "Window enumeration panicked",
            ));
        }

        if let Some(f) = filter_title {
            let fl = f.to_lowercase();
            windows.retain(|w| w.title.to_lowercase().contains(&fl));
        }
        Ok(windows)
    }

    extern "system" fn enum_proc(hwnd: HWND, lparam: LPARAM) -> BOOL {
        let windows = unsafe { &mut *(lparam.0 as *mut Vec<WindowInfo>) };
        let mut title_buf = [0u16; 512];
        let len = unsafe { GetWindowTextW(hwnd, &mut title_buf) } as usize;
        if len == 0 {
            return BOOL(1);
        }

        let title = OsString::from_wide(&title_buf[..len])
            .to_string_lossy()
            .into_owned();

        let mut rect = RECT::default();
        if unsafe { GetWindowRect(hwnd, &mut rect) }.is_err() {
            return BOOL(1);
        }

        let is_visible = unsafe { IsWindowVisible(hwnd) }.as_bool();
        let mut pid: u32 = 0;
        unsafe {
            GetWindowThreadProcessId(hwnd, Some(&mut pid));
        }

        windows.push(WindowInfo {
            title,
            x: rect.left,
            y: rect.top,
            width: rect.right - rect.left,
            height: rect.bottom - rect.top,
            pid,
            is_visible,
        });
        BOOL(1)
    }

    // ── find_hwnd — uses Box for safe FFI mutability ──

    fn find_hwnd(title: &str) -> PyResult<HWND> {
        let tl = title.to_lowercase();
        // Use Box to safely pass mutable state through FFI boundary.
        // The callback writes found_hwnd; after EnumWindows, we Box::from_raw.
        let data = Box::into_raw(Box::new((tl, None::<HWND>)));

        let result = catch_unwind(AssertUnwindSafe(|| unsafe {
            let _ = EnumWindows(Some(find_proc), LPARAM(data as isize));
        }));

        // Recover the box — even if callback panicked (won't happen, but safe)
        let (_, found) = unsafe { *Box::from_raw(data) };

        if result.is_err() {
            return Err(PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(
                "Window search panicked",
            ));
        }

        found.ok_or_else(|| {
            PyErr::new::<pyo3::exceptions::PyValueError, _>(format!("Window not found: {title}"))
        })
    }

    extern "system" fn find_proc(hwnd: HWND, lparam: LPARAM) -> BOOL {
        let (target, found) = unsafe { &mut *(lparam.0 as *mut (String, Option<HWND>)) };
        let mut buf = [0u16; 512];
        let len = unsafe { GetWindowTextW(hwnd, &mut buf) } as usize;
        if len > 0 {
            let t = OsString::from_wide(&buf[..len])
                .to_string_lossy()
                .into_owned();
            if t.to_lowercase().contains(target.as_str()) {
                *found = Some(hwnd);
                return BOOL(0);
            }
        }
        BOOL(1)
    }

    // ── actions ──

    pub fn focus(title: &str) -> PyResult<()> {
        let hwnd = find_hwnd(title)?;
        // ShowWindow/SetForegroundWindow may fail for elevated windows; not critical
        #[allow(unused_must_use)]
        unsafe {
            ShowWindow(hwnd, SW_RESTORE);
            ShowWindow(hwnd, SW_SHOW);
            SetForegroundWindow(hwnd);
        }
        Ok(())
    }

    pub fn move_window(title: &str, x: i32, y: i32) -> PyResult<()> {
        let hwnd = find_hwnd(title)?;
        let mut rect = RECT::default();
        unsafe { GetWindowRect(hwnd, &mut rect) }
            .map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(e.to_string()))?;
        let w = rect.right - rect.left;
        let h = rect.bottom - rect.top;
        let _ = unsafe { MoveWindow(hwnd, x, y, w, h, true) };
        Ok(())
    }

    pub fn resize_window(title: &str, w: i32, h: i32) -> PyResult<()> {
        let hwnd = find_hwnd(title)?;
        // Preserve current position — get rect first
        let mut rect = RECT::default();
        unsafe { GetWindowRect(hwnd, &mut rect) }
            .map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(e.to_string()))?;
        let _ = unsafe { MoveWindow(hwnd, rect.left, rect.top, w, h, true) };
        Ok(())
    }

    pub fn get_rect(title: &str) -> PyResult<(i32, i32, i32, i32)> {
        let hwnd = find_hwnd(title)?;
        let mut rect = RECT::default();
        unsafe { GetWindowRect(hwnd, &mut rect) }
            .map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(e.to_string()))?;
        Ok((
            rect.left,
            rect.top,
            rect.right - rect.left,
            rect.bottom - rect.top,
        ))
    }
}

#[cfg(not(windows))]
mod win32 {
    use super::*;
    fn not_impl() -> PyErr {
        PyErr::new::<pyo3::exceptions::PyNotImplementedError, _>("Not implemented on this platform")
    }
    pub fn enumerate(_f: Option<&str>) -> PyResult<Vec<WindowInfo>> {
        Ok(Vec::new())
    }
    pub fn focus(_t: &str) -> PyResult<()> {
        Err(not_impl())
    }
    pub fn move_window(_t: &str, _x: i32, _y: i32) -> PyResult<()> {
        Err(not_impl())
    }
    pub fn resize_window(_t: &str, _w: i32, _h: i32) -> PyResult<()> {
        Err(not_impl())
    }
    pub fn get_rect(_t: &str) -> PyResult<(i32, i32, i32, i32)> {
        Err(not_impl())
    }
}

// ── PyO3 exports ──

#[pyfunction]
pub fn window_list(filter_title: Option<String>) -> PyResult<Vec<WindowInfo>> {
    win32::enumerate(filter_title.as_deref())
}

#[pyfunction]
pub fn window_focus(title: &str) -> PyResult<()> {
    win32::focus(title)
}

#[pyfunction]
pub fn window_move(title: &str, x: i32, y: i32) -> PyResult<()> {
    win32::move_window(title, x, y)
}

#[pyfunction]
pub fn window_resize(title: &str, w: i32, h: i32) -> PyResult<()> {
    win32::resize_window(title, w, h)
}

#[pyfunction]
pub fn window_get_rect(title: &str) -> PyResult<(i32, i32, i32, i32)> {
    win32::get_rect(title)
}

#[pyfunction]
pub fn launch_app(path: &str) -> PyResult<()> {
    std::process::Command::new(path)
        .spawn()
        .map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(e.to_string()))?;
    Ok(())
}

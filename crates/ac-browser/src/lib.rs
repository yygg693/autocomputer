//! ac-browser: autocomputer 浏览器引擎
//!
//! 纯 Rust 实现的 Chrome DevTools Protocol 客户端
//! - 浏览器启动与生命周期管理
//! - CDP WebSocket 连接
//! - 页面导航、截图、DOM 操作
//! - 连接池管理

use pyo3::prelude::*;

#[pymodule]
fn _ac_browser(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add("__version__", env!("CARGO_PKG_VERSION"))?;
    Ok(())
}

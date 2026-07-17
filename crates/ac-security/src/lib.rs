//! ac-security: autocomputer 安全引擎
//!
//! - 边界检查、循环检测、频率限制
//! - 热键拦截
//! - 安全策略 TOML 加载
//! - SQLite 审计追踪

use pyo3::prelude::*;
use rusqlite::Connection;
use serde::{Deserialize, Serialize};
use std::sync::Mutex;
use std::time::Instant;

// ── Data structures ──

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SecurityConfig {
    #[serde(default = "default_true")]
    pub fail_safe_corner: bool,
    #[serde(default = "default_max_clicks")]
    pub max_clicks_same_position: u32,
    #[serde(default = "default_rate_limit")]
    pub rate_limit_ms: u64,
    #[serde(default)]
    pub blocked_hotkeys: Vec<HotkeyRule>,
    #[serde(default)]
    pub app_permissions: Vec<AppPermission>,
    #[serde(default = "default_true")]
    pub audit_enabled: bool,
    #[serde(default = "default_retention")]
    pub audit_retention_days: u32,
}

fn default_true() -> bool { true }
fn default_max_clicks() -> u32 { 5 }
fn default_rate_limit() -> u64 { 100 }
fn default_retention() -> u32 { 90 }

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct HotkeyRule {
    pub keys: Vec<String>,
    #[serde(default)]
    pub severity: Severity,
    #[serde(default)]
    pub message: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Default)]
pub enum Severity {
    #[default]
    Critical,
    Warning,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AppPermission {
    pub app: String,
    #[serde(default)]
    pub allow: Vec<String>,
    #[serde(default)]
    pub deny: Vec<String>,
    #[serde(default)]
    pub prompt: Vec<String>,
}

#[derive(Debug)]
pub enum SecurityAction {
    Click { x: i32, y: i32 },
    Hotkey { keys: Vec<String> },
    AppAction { app: String, action: String },
}

impl Default for SecurityConfig {
    fn default() -> Self {
        SecurityConfig {
            fail_safe_corner: true,
            max_clicks_same_position: 5,
            rate_limit_ms: 100,
            blocked_hotkeys: vec![
                HotkeyRule { keys: vec!["alt+f4".into(), "win+l".into(), "win+r".into(), "ctrl+alt+del".into()], severity: Severity::Critical, message: None },
            ],
            app_permissions: Vec::new(),
            audit_enabled: true,
            audit_retention_days: 90,
        }
    }
}

// ── Security Guard ──

pub struct SecurityGuard {
    pub config: SecurityConfig,
    click_history: Vec<(i32, i32, Instant)>,
    last_action: Instant,
    db: Option<Connection>,
}

impl SecurityGuard {
    pub fn new(config: SecurityConfig) -> Self {
        let db = if config.audit_enabled {
            let conn = Connection::open("autocomputer_audit.db").ok();
            if let Some(ref c) = conn {
                let _ = c.execute(
                    "CREATE TABLE IF NOT EXISTS audit_log (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp TEXT NOT NULL,
                        action TEXT NOT NULL,
                        detail TEXT,
                        result TEXT NOT NULL
                    )",
                    [],
                );
            }
            conn
        } else {
            None
        };

        SecurityGuard {
            config,
            click_history: Vec::new(),
            last_action: Instant::now(),
            db,
        }
    }

    pub fn from_toml(toml_str: &str) -> Result<Self, String> {
        let config: SecurityConfig = toml::from_str(toml_str).map_err(|e| e.to_string())?;
        Ok(Self::new(config))
    }

    pub fn with_defaults() -> Self {
        Self::new(SecurityConfig::default())
    }

    // ── Checks ──

    /// Check click: bounds + loop + rate
    pub fn guard_click(&mut self, x: i32, y: i32, screen_w: i32, screen_h: i32) -> Result<(i32, i32), String> {
        // Fail-safe: corner (0,0) cancels
        if self.config.fail_safe_corner && x == 0 && y == 0 {
            self.audit("fail_safe", "Mouse moved to corner (0,0) — abort");
            return Err("Fail-safe triggered: mouse moved to corner (0,0)".into());
        }

        // Bounds check + clamp
        let cx = x.clamp(0, screen_w - 1);
        let cy = y.clamp(0, screen_h - 1);
        if cx != x || cy != y {
            self.audit("bounds_clamp", &format!("({x},{y}) → ({cx},{cy})"));
        }

        // Loop detection
        let now = Instant::now();
        let same_pos_count = self.click_history.iter()
            .filter(|(px, py, _)| *px == cx && *py == cy)
            .count();
        if same_pos_count as u32 >= self.config.max_clicks_same_position {
            self.audit("loop_blocked", &format!("{same_pos_count} clicks at ({cx},{cy})"));
            return Err(format!("Loop detected: {same_pos_count} clicks at same position ({cx},{cy})"));
        }
        self.click_history.push((cx, cy, now));
        self.click_history.retain(|(_, _, t)| now.duration_since(*t).as_secs() < 5);

        // Rate limit
        let elapsed = now.duration_since(self.last_action).as_millis() as u64;
        if elapsed < self.config.rate_limit_ms {
            self.audit("rate_limited", &format!("{elapsed}ms < {}ms limit", self.config.rate_limit_ms));
            return Err(format!("Rate limited: {elapsed}ms since last action (min: {}ms)", self.config.rate_limit_ms));
        }
        self.last_action = now;

        self.audit("click", &format!("({cx},{cy})"));
        Ok((cx, cy))
    }

    /// Check hotkey combo
    pub fn guard_hotkey(&self, keys: &[String]) -> Result<(), String> {
        let combo = keys.join("+").to_lowercase();
        for rule in &self.config.blocked_hotkeys {
            let blocked = rule.keys.iter()
                .map(|k| k.to_lowercase())
                .collect::<Vec<_>>()
                .join("+");
            if combo == blocked {
                self.audit("hotkey_blocked", &combo);
                let msg = rule.message.as_deref().unwrap_or("Blocked hotkey");
                return Err(format!("{msg}: {combo}"));
            }
        }
        self.audit("hotkey", &combo);
        Ok(())
    }

    /// Check app permission
    pub fn guard_app_action(&self, app: &str, action: &str) -> Result<(), String> {
        for perm in &self.config.app_permissions {
            if perm.app.to_lowercase() == app.to_lowercase() {
                if perm.deny.iter().any(|a| a == action) {
                    self.audit("app_denied", &format!("{app}:{action}"));
                    return Err(format!("Action '{action}' denied for app '{app}'"));
                }
                if perm.prompt.iter().any(|a| a == action) {
                    self.audit("app_prompt", &format!("{app}:{action}"));
                    return Err(format!("Action '{action}' requires user prompt for app '{app}'"));
                }
                if perm.allow.iter().any(|a| a == action) || perm.allow.is_empty() {
                    self.audit("app_allowed", &format!("{app}:{action}"));
                    return Ok(());
                }
            }
        }
        // No matching permission rule → allow by default
        self.audit("app_allowed_default", &format!("{app}:{action}"));
        Ok(())
    }

    // ── Audit ──

    fn audit(&self, action: &str, detail: &str) {
        if let Some(ref conn) = self.db {
            let now = chrono_now();
            let _ = conn.execute(
                "INSERT INTO audit_log (timestamp, action, detail, result) VALUES (?1, ?2, ?3, 'ok')",
                rusqlite::params![now, action, detail],
            );
        }
    }
}

fn chrono_now() -> String {
    // Simple ISO timestamp without chrono dependency
    use std::time::SystemTime;
    let now = SystemTime::now()
        .duration_since(SystemTime::UNIX_EPOCH)
        .unwrap_or_default();
    let secs = now.as_secs();
    // Basic formatting: not perfect but avoids chrono dependency
    format!("{secs}")
}

// ── PyO3 wrapper ──

static GUARD: Mutex<Option<SecurityGuard>> = Mutex::new(None);

fn with_guard<F, R>(f: F) -> PyResult<R>
where
    F: FnOnce(&mut SecurityGuard) -> Result<R, String>,
{
    let mut guard = GUARD.lock().map_err(|e| {
        PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(e.to_string())
    })?;
    let g = guard.get_or_insert_with(SecurityGuard::with_defaults);
    f(g).map_err(PyErr::new::<pyo3::exceptions::PyRuntimeError, _>)
}

#[pyfunction]
pub fn security_init(config_toml: Option<String>) -> PyResult<()> {
    let config = if let Some(toml_str) = config_toml {
        toml::from_str(&toml_str).map_err(|e| {
            PyErr::new::<pyo3::exceptions::PyValueError, _>(e.to_string())
        })?
    } else {
        SecurityConfig::default()
    };

    let mut guard = GUARD.lock().map_err(|e| {
        PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(e.to_string())
    })?;
    *guard = Some(SecurityGuard::new(config));
    Ok(())
}

#[pyfunction]
pub fn guard_click(x: i32, y: i32, screen_w: i32, screen_h: i32) -> PyResult<(i32, i32)> {
    with_guard(|g| g.guard_click(x, y, screen_w, screen_h))
}

#[pyfunction]
pub fn guard_hotkey(keys: Vec<String>) -> PyResult<()> {
    with_guard(|g| g.guard_hotkey(&keys))
}

#[pyfunction]
pub fn guard_app_action(app: &str, action: &str) -> PyResult<()> {
    with_guard(|g| g.guard_app_action(app, action))
}

#[pyfunction]
pub fn security_reset() -> PyResult<()> {
    let mut guard = GUARD.lock().map_err(|e| {
        PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(e.to_string())
    })?;
    *guard = Some(SecurityGuard::with_defaults());
    Ok(())
}

//! Security guard — bounds, loop, rate, hotkeys, app permissions, SQLite audit.

use pyo3::prelude::*;
use rusqlite::Connection;
use serde::{Deserialize, Serialize};
use std::sync::Mutex;
use std::time::Instant;

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

fn default_true() -> bool {
    true
}
fn default_max_clicks() -> u32 {
    5
}
fn default_rate_limit() -> u64 {
    100
}
fn default_retention() -> u32 {
    90
}

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

impl Default for SecurityConfig {
    fn default() -> Self {
        SecurityConfig {
            fail_safe_corner: true,
            max_clicks_same_position: 5,
            rate_limit_ms: 100,
            blocked_hotkeys: vec![
                HotkeyRule {
                    keys: vec!["alt+f4".into()],
                    severity: Severity::Critical,
                    message: None,
                },
                HotkeyRule {
                    keys: vec!["win+l".into()],
                    severity: Severity::Critical,
                    message: None,
                },
                HotkeyRule {
                    keys: vec!["win+r".into()],
                    severity: Severity::Critical,
                    message: None,
                },
                HotkeyRule {
                    keys: vec!["ctrl+alt+del".into()],
                    severity: Severity::Critical,
                    message: None,
                },
            ],
            app_permissions: Vec::new(),
            audit_enabled: true,
            audit_retention_days: 90,
        }
    }
}

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
                        timestamp INTEGER NOT NULL,
                        iso_time TEXT NOT NULL DEFAULT '',
                        action TEXT NOT NULL,
                        detail TEXT,
                        result TEXT NOT NULL)",
                    [],
                );
                // Add iso_time if upgrading from older schema
                let _ = c.execute(
                    "ALTER TABLE audit_log ADD COLUMN iso_time TEXT NOT NULL DEFAULT ''",
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
            last_action: Instant::now() - std::time::Duration::from_secs(3600),
            db,
        }
    }

    pub fn with_defaults() -> Self {
        Self::new(SecurityConfig::default())
    }

    pub fn guard_click(
        &mut self,
        x: i32,
        y: i32,
        screen_w: i32,
        screen_h: i32,
    ) -> Result<(i32, i32), String> {
        if self.config.fail_safe_corner && x == 0 && y == 0 {
            self.audit("fail_safe", "(0,0) abort");
            return Err("Fail-safe: (0,0)".into());
        }
        let cx = x.clamp(0, screen_w - 1);
        let cy = y.clamp(0, screen_h - 1);
        if cx != x || cy != y {
            self.audit("bounds_clamp", &format!("({x},{y})->({cx},{cy})"));
        }

        let now = Instant::now();
        let same = self
            .click_history
            .iter()
            .filter(|(px, py, _)| *px == cx && *py == cy)
            .count();
        if same as u32 >= self.config.max_clicks_same_position {
            self.audit("loop_blocked", &format!("{same} clicks"));
            return Err(format!("Loop: {same} clicks"));
        }
        self.click_history.push((cx, cy, now));
        self.click_history
            .retain(|(_, _, t)| now.duration_since(*t).as_secs() < 5);

        let elapsed = now.duration_since(self.last_action).as_millis() as u64;
        if elapsed < self.config.rate_limit_ms {
            self.audit("rate_limited", &format!("{elapsed}ms"));
            return Err(format!("Rate limit: {elapsed}ms"));
        }
        self.last_action = now;
        self.audit("click", &format!("({cx},{cy})"));
        Ok((cx, cy))
    }

    pub fn guard_hotkey(&self, keys: &[String]) -> Result<(), String> {
        let combo = keys.join("+").to_lowercase();
        for rule in &self.config.blocked_hotkeys {
            let blocked = rule
                .keys
                .iter()
                .map(|k| k.to_lowercase())
                .collect::<Vec<_>>()
                .join("+");
            if combo == blocked {
                self.audit("hotkey_blocked", &combo);
                return Err(rule
                    .message
                    .clone()
                    .unwrap_or_else(|| format!("Blocked: {combo}")));
            }
        }
        Ok(())
    }

    pub fn guard_app_action(&self, app: &str, action: &str) -> Result<(), String> {
        for perm in &self.config.app_permissions {
            if perm.app.to_lowercase() == app.to_lowercase() {
                if perm.deny.iter().any(|a| a == action) {
                    return Err(format!("Denied {action} on {app}"));
                }
                if perm.prompt.iter().any(|a| a == action) {
                    return Err(format!("Prompt required: {action}"));
                }
                if perm.allow.iter().any(|a| a == action) || perm.allow.is_empty() {
                    return Ok(());
                }
            }
        }
        Ok(())
    }

    fn audit(&self, action: &str, detail: &str) {
        if let Some(ref conn) = self.db {
            // Log errors instead of silently swallowing
            if let Err(e) = conn.execute(
                "INSERT INTO audit_log (timestamp, iso_time, action, detail, result) VALUES (?1, ?2, ?3, ?4, 'ok')",
                rusqlite::params![unix_now(), iso_now(), action, detail],
            ) {
                eprintln!("[autocomputer] audit write failed: {e}");
            }
            // Cleanup old records lazily (~1% of writes)
            if unix_now().is_multiple_of(100) {
                maybe_cleanup_audit(conn, self.config.audit_retention_days);
            }
        }
    }
}

fn unix_now() -> u64 {
    std::time::SystemTime::now()
        .duration_since(std::time::SystemTime::UNIX_EPOCH)
        .map(|d| d.as_secs())
        .unwrap_or(0)
}

fn iso_now() -> String {
    chrono::Utc::now().format("%Y-%m-%dT%H:%M:%SZ").to_string()
}

/// Periodic cleanup of old audit entries (called lazily, ~1% probability per write).
fn maybe_cleanup_audit(conn: &rusqlite::Connection, retention_days: u32) {
    let cutoff = unix_now().saturating_sub(retention_days as u64 * 86400);
    let _ = conn.execute(
        "DELETE FROM audit_log WHERE timestamp < ?1",
        rusqlite::params![cutoff],
    );
}

// ── PyO3 wrapper ──

static GUARD: Mutex<Option<SecurityGuard>> = Mutex::new(None);

fn with_guard<F, R>(f: F) -> PyResult<R>
where
    F: FnOnce(&mut SecurityGuard) -> Result<R, String>,
{
    let mut guard = GUARD
        .lock()
        .map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(e.to_string()))?;
    let g = guard.get_or_insert_with(SecurityGuard::with_defaults);
    f(g).map_err(PyErr::new::<pyo3::exceptions::PyRuntimeError, _>)
}

#[pyfunction]
pub fn security_init(config_toml: Option<String>) -> PyResult<()> {
    let config = config_toml.map_or_else(
        || Ok(SecurityConfig::default()),
        |s| {
            toml::from_str(&s)
                .map_err(|e| PyErr::new::<pyo3::exceptions::PyValueError, _>(e.to_string()))
        },
    )?;
    let mut guard = GUARD
        .lock()
        .map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(e.to_string()))?;
    *guard = Some(SecurityGuard::new(config));
    Ok(())
}

#[pyfunction]
pub fn guard_click(x: i32, y: i32, sw: i32, sh: i32) -> PyResult<(i32, i32)> {
    with_guard(|g| g.guard_click(x, y, sw, sh))
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
    let mut guard = GUARD
        .lock()
        .map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(e.to_string()))?;
    *guard = Some(SecurityGuard::with_defaults());
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_check_click_ok() {
        let mut g = SecurityGuard::with_defaults();
        let (x, y) = g.guard_click(100, 200, 1920, 1080).expect("click ok");
        assert_eq!(x, 100);
        assert_eq!(y, 200);
    }

    #[test]
    fn test_check_click_fail_safe() {
        let mut g = SecurityGuard::with_defaults();
        assert!(g.guard_click(0, 0, 1920, 1080).is_err());
    }

    #[test]
    fn test_check_click_bounds_clamp() {
        let mut g = SecurityGuard::with_defaults();
        let (x, y) = g.guard_click(-10, 2000, 1920, 1080).expect("clamped");
        assert_eq!(x, 0);
        assert_eq!(y, 1079);
    }

    #[test]
    fn test_check_click_loop() {
        let mut g = SecurityGuard::new(SecurityConfig {
            rate_limit_ms: 0,
            ..SecurityConfig::default()
        });
        for _ in 0..5 {
            g.guard_click(500, 500, 1920, 1080).expect("ok");
        }
        assert!(g.guard_click(500, 500, 1920, 1080).is_err());
    }

    #[test]
    fn test_hotkey_block() {
        let g = SecurityGuard::with_defaults();
        assert!(g.guard_hotkey(&["alt".into(), "f4".into()]).is_err());
        assert!(g.guard_hotkey(&["enter".into()]).is_ok());
    }

    #[test]
    fn test_hotkey_custom() {
        let config = SecurityConfig {
            blocked_hotkeys: vec![HotkeyRule {
                keys: vec!["ctrl+q".into()],
                severity: Severity::Critical,
                message: None,
            }],
            ..SecurityConfig::default()
        };
        let g = SecurityGuard::new(config);
        assert!(g.guard_hotkey(&["ctrl".into(), "q".into()]).is_err());
    }

    #[test]
    fn test_config_from_toml() {
        let toml = r#"
fail_safe_corner = true
max_clicks_same_position = 3
rate_limit_ms = 50
[[blocked_hotkeys]]
keys = ["ctrl+x"]
severity = "Warning"
"#;
        let g = SecurityGuard::new(toml::from_str(toml).expect("parse"));
        assert_eq!(g.config.max_clicks_same_position, 3);
        assert!(g.guard_hotkey(&["ctrl".into(), "x".into()]).is_err());
    }
}

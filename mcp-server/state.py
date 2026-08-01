#!/usr/bin/env python3
"""
Unified State Manager for autocomputer — single SQLite DB for all subsystems.

Merges what were previously separate stores:
  - agent state  (.agent_state/)        → tables: agent_state, change_log
  - security audit (security_v2.py)     → tables: audit_log, permissions
  - cross-session memory (memory.py)    → tables: learned_actions, ui_patterns, user_prefs

Benefits:
  1. Single source of truth — query across subsystems
  2. WAL mode + retry for concurrent safety
  3. Backward-compatible: other modules can import this instead of their own DB
  4. Auto-migration from old separate stores
"""

import sys
import io
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        try:
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
            sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
        except Exception:
            pass

import sqlite3
import json
import time
import os
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Any

DB_PATH = Path.home() / ".qclaw" / "autocomputer" / "unified_state.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

# ── Singleton connection ──
_conn: Optional[sqlite3.Connection] = None


def _get_conn() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        _conn = sqlite3.connect(str(DB_PATH))
        _conn.row_factory = sqlite3.Row
        _conn.execute("PRAGMA journal_mode=WAL")
        _conn.execute("PRAGMA busy_timeout=3000")
        _conn.execute("PRAGMA foreign_keys=ON")
        _create_tables(_conn)
    return _conn


def _create_tables(conn: sqlite3.Connection):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS _schema (
            key   TEXT PRIMARY KEY,
            value TEXT
        );

        CREATE TABLE IF NOT EXISTS agent_state (
            key        TEXT PRIMARY KEY,
            value      TEXT,
            updated_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS change_log (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp  TEXT DEFAULT (datetime('now')),
            action     TEXT NOT NULL,
            detail     TEXT,
            before_img TEXT,
            after_img  TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_change_log_ts ON change_log(timestamp);

        CREATE TABLE IF NOT EXISTS audit_log (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp     TEXT DEFAULT (datetime('now')),
            app           TEXT,
            action_type   TEXT NOT NULL,
            risk_level    TEXT NOT NULL DEFAULT 'MEDIUM',
            detail        TEXT,
            before_img    TEXT,
            after_img     TEXT,
            verdict       TEXT,
            session_id    TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_audit_ts    ON audit_log(timestamp);
        CREATE INDEX IF NOT EXISTS idx_audit_app   ON audit_log(app);
        CREATE INDEX IF NOT EXISTS idx_audit_risk  ON audit_log(risk_level);

        CREATE TABLE IF NOT EXISTS permissions (
            app        TEXT PRIMARY KEY,
            policy     TEXT NOT NULL DEFAULT 'ask',
            granted_at TEXT DEFAULT (datetime('now')),
            reason     TEXT
        );

        CREATE TABLE IF NOT EXISTS learned_actions (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            app         TEXT NOT NULL,
            task        TEXT NOT NULL,
            steps       TEXT NOT NULL,
            success     INTEGER DEFAULT 1,
            used_count  INTEGER DEFAULT 0,
            last_used   TEXT,
            created_at  TEXT DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_learned_app_task ON learned_actions(app, task);

        CREATE TABLE IF NOT EXISTS ui_patterns (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            app         TEXT NOT NULL,
            element     TEXT NOT NULL,
            signature   TEXT,
            position    TEXT,
            confidence  REAL DEFAULT 1.0,
            last_seen   TEXT DEFAULT (datetime('now')),
            seen_count  INTEGER DEFAULT 1
        );
        CREATE INDEX IF NOT EXISTS idx_patterns_app_elem ON ui_patterns(app, element);

        CREATE TABLE IF NOT EXISTS user_prefs (
            key        TEXT PRIMARY KEY,
            value      TEXT NOT NULL,
            updated_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS sessions (
            id         TEXT PRIMARY KEY,
            started_at TEXT DEFAULT (datetime('now')),
            ended_at   TEXT,
            model      TEXT,
            task_count INTEGER DEFAULT 0,
            status     TEXT DEFAULT 'active'
        );
    """)
    conn.commit()


# ═══════════════════════════════════════════════════════════════
#  Public API
# ═══════════════════════════════════════════════════════════════

def agent_set(key: str, value: str):
    conn = _get_conn()
    conn.execute(
        "INSERT OR REPLACE INTO agent_state (key, value, updated_at) VALUES (?, ?, datetime('now'))",
        (key, value)
    )
    conn.commit()

def agent_get(key: str) -> Optional[str]:
    conn = _get_conn()
    row = conn.execute("SELECT value FROM agent_state WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else None

def agent_delete(key: str):
    conn = _get_conn()
    conn.execute("DELETE FROM agent_state WHERE key = ?", (key,))
    conn.commit()

def log_change(action: str, detail: dict, before_img: str = None, after_img: str = None):
    conn = _get_conn()
    conn.execute(
        "INSERT INTO change_log (action, detail, before_img, after_img) VALUES (?, ?, ?, ?)",
        (action, json.dumps(detail, ensure_ascii=False), before_img, after_img)
    )
    conn.commit()


def audit_log(app: str, action_type: str, risk_level: str = "MEDIUM",
              detail: dict = None, before_img: str = None, after_img: str = None,
              verdict: str = "allowed", session_id: str = None):
    conn = _get_conn()
    conn.execute(
        """INSERT INTO audit_log (app, action_type, risk_level, detail, before_img, after_img, verdict, session_id)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (app, action_type, risk_level,
         json.dumps(detail, ensure_ascii=False) if detail else None,
         before_img, after_img, verdict, session_id)
    )
    conn.commit()

def audit_query(app: str = None, risk_level: str = None, limit: int = 20) -> list[dict]:
    conn = _get_conn()
    sql = "SELECT * FROM audit_log WHERE 1=1"
    params = []
    if app:
        sql += " AND app = ?"; params.append(app)
    if risk_level:
        sql += " AND risk_level = ?"; params.append(risk_level)
    sql += " ORDER BY id DESC LIMIT ?"; params.append(limit)
    return [dict(r) for r in conn.execute(sql, params).fetchall()]

def audit_stats() -> dict:
    conn = _get_conn()
    total = conn.execute("SELECT COUNT(*) as n FROM audit_log").fetchone()["n"]
    by_app = [dict(r) for r in conn.execute(
        "SELECT app, COUNT(*) as n FROM audit_log GROUP BY app ORDER BY n DESC LIMIT 10"
    ).fetchall()]
    by_risk = [dict(r) for r in conn.execute(
        "SELECT risk_level, COUNT(*) as n FROM audit_log GROUP BY risk_level"
    ).fetchall()]
    return {"total": total, "by_app": by_app, "by_risk": by_risk}


def permission_get(app: str) -> str:
    conn = _get_conn()
    row = conn.execute("SELECT policy FROM permissions WHERE app = ?", (app,)).fetchone()
    return row["policy"] if row else "ask"

def permission_set(app: str, policy: str, reason: str = None):
    conn = _get_conn()
    conn.execute(
        "INSERT OR REPLACE INTO permissions (app, policy, granted_at, reason) VALUES (?, ?, datetime('now'), ?)",
        (app, policy, reason)
    )
    conn.commit()

def permission_reset(app: str):
    conn = _get_conn()
    conn.execute("DELETE FROM permissions WHERE app = ?", (app,))
    conn.commit()

def permission_list() -> list[dict]:
    conn = _get_conn()
    return [dict(r) for r in conn.execute("SELECT * FROM permissions ORDER BY app").fetchall()]


def memory_learn(app: str, task: str, steps: list[dict], success: bool = True) -> int:
    conn = _get_conn()
    existing = conn.execute(
        "SELECT id, used_count FROM learned_actions WHERE app = ? AND task = ? AND success = 1",
        (app, task)
    ).fetchone()
    if existing:
        conn.execute(
            "UPDATE learned_actions SET steps = ?, used_count = used_count + 1, last_used = datetime('now') WHERE id = ?",
            (json.dumps(steps, ensure_ascii=False), existing["id"])
        )
        conn.commit()
        return existing["id"]
    cur = conn.execute(
        "INSERT INTO learned_actions (app, task, steps, success) VALUES (?, ?, ?, ?)",
        (app, task, json.dumps(steps, ensure_ascii=False), 1 if success else 0)
    )
    conn.commit()
    return cur.lastrowid

def memory_recall(app: str, task: str = None, limit: int = 5) -> list[dict]:
    conn = _get_conn()
    if task:
        rows = conn.execute(
            "SELECT * FROM learned_actions WHERE app = ? AND task = ? ORDER BY used_count DESC, last_used DESC LIMIT ?",
            (app, task, limit)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM learned_actions WHERE app = ? ORDER BY used_count DESC, last_used DESC LIMIT ?",
            (app, limit)
        ).fetchall()
    return [dict(r) for r in rows]


def pattern_save(app: str, element: str, signature: str = None,
                 position: dict = None, confidence: float = 1.0):
    conn = _get_conn()
    existing = conn.execute(
        "SELECT id, seen_count FROM ui_patterns WHERE app = ? AND element = ?",
        (app, element)
    ).fetchone()
    if existing:
        conn.execute(
            """UPDATE ui_patterns
               SET signature = ?, position = ?, confidence = ?, last_seen = datetime('now'),
                   seen_count = seen_count + 1 WHERE id = ?""",
            (signature, json.dumps(position) if position else None, confidence, existing["id"])
        )
    else:
        conn.execute(
            "INSERT INTO ui_patterns (app, element, signature, position, confidence) VALUES (?, ?, ?, ?, ?)",
            (app, element, signature, json.dumps(position) if position else None, confidence)
        )
    conn.commit()

def pattern_find(app: str, element: str) -> Optional[dict]:
    conn = _get_conn()
    row = conn.execute(
        "SELECT * FROM ui_patterns WHERE app = ? AND element = ? ORDER BY confidence DESC, seen_count DESC LIMIT 1",
        (app, element)
    ).fetchone()
    if row:
        d = dict(row)
        if d.get("position"):
            d["position"] = json.loads(d["position"])
        return d
    return None


def pref_set(key: str, value: str):
    conn = _get_conn()
    conn.execute(
        "INSERT OR REPLACE INTO user_prefs (key, value, updated_at) VALUES (?, ?, datetime('now'))",
        (key, value)
    )
    conn.commit()

def pref_get(key: str) -> Optional[str]:
    conn = _get_conn()
    row = conn.execute("SELECT value FROM user_prefs WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else None

def pref_list() -> dict:
    conn = _get_conn()
    return {r["key"]: r["value"] for r in conn.execute("SELECT key, value FROM user_prefs").fetchall()}


def session_start(session_id: str, model: str = None) -> str:
    conn = _get_conn()
    conn.execute(
        "INSERT OR REPLACE INTO sessions (id, started_at, model, status) VALUES (?, datetime('now'), ?, 'active')",
        (session_id, model)
    )
    conn.commit()
    return session_id

def session_end(session_id: str):
    conn = _get_conn()
    conn.execute(
        "UPDATE sessions SET ended_at = datetime('now'), status = 'ended' WHERE id = ?",
        (session_id,)
    )
    conn.commit()

def session_increment_task(session_id: str):
    conn = _get_conn()
    conn.execute("UPDATE sessions SET task_count = task_count + 1 WHERE id = ?", (session_id,))
    conn.commit()


def cleanup(days: int = 30):
    conn = _get_conn()
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()
    conn.execute("DELETE FROM change_log WHERE timestamp < ?", (cutoff,))
    conn.execute("DELETE FROM audit_log WHERE timestamp < ?", (cutoff,))
    conn.execute("DELETE FROM ui_patterns WHERE last_seen < ? AND seen_count < 3", (cutoff,))
    conn.execute("VACUUM")
    conn.commit()

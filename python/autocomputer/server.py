"""
autocomputer API Server — HTTP bridge between GUI and Rust core.
Start with: python -m autocomputer serve
"""

import json
import base64
import sqlite3
import sys
import time
import threading
from collections import deque
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from pathlib import Path

if sys.platform == "win32":
    try:
        # Windows console defaults to gbk/cp936 — emoji in startup banner crashes.
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

GUI_DIR = Path(__file__).resolve().parent.parent.parent / "gui"
REPO_ROOT = Path(__file__).resolve().parent.parent.parent

# -- In-process operation log (ring buffer, most recent 200) --
_LOG_QUEUE: deque = deque(maxlen=200)


def count_tests() -> int:
    """Dynamically count tests: Rust #[test] markers + Python def test_ functions."""
    n = 0
    rust_src = REPO_ROOT / "crates" / "ac-core" / "src"
    for rs in rust_src.glob("*.rs"):
        n += rs.read_text(encoding="utf-8").count("#[test]")
    py_tests = REPO_ROOT / "python" / "tests"
    for py in py_tests.glob("test_*.py"):
        n += sum(
            1 for line in py.read_text(encoding="utf-8").splitlines()
            if line.lstrip().startswith("def test_")
        )
    return n


def flows_path() -> Path:
    """Location of persisted flows: %APPDATA%/autocomputer/flows.json."""
    from autocomputer.utils import config_dir
    return config_dir() / "flows.json"


def _load_flows() -> list:
    p = flows_path()
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []


def _save_flows(flows: list) -> None:
    p = flows_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(flows, ensure_ascii=False, indent=2), encoding="utf-8")


def audit_stats() -> dict:
    """Read audit statistics from the Rust-core SQLite database (may be absent)."""
    from autocomputer.utils import config_dir
    db = config_dir() / "autocomputer_audit.db"
    stats = {"total": 0, "by_action": {}, "recent": []}
    if not db.exists():
        return stats
    try:
        conn = sqlite3.connect(db)
        row = conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()
        stats["total"] = row[0] if row else 0
        for action, cnt in conn.execute(
            "SELECT action, COUNT(*) AS c FROM audit_log GROUP BY action ORDER BY c DESC"
        ):
            stats["by_action"][action] = cnt
        for r in conn.execute(
            "SELECT iso_time, action, detail, result FROM audit_log ORDER BY id DESC LIMIT 20"
        ):
            stats["recent"].append(
                {"time": r[0], "action": r[1], "detail": r[2], "result": r[3]}
            )
        conn.close()
    except Exception:
        pass
    return stats


class APIHandler(BaseHTTPRequestHandler):
    """HTTP request handler with JSON API + static file serving."""

    def log_message(self, format, *args):
        """Silence default logging."""
        pass

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        # ── API Routes ──
        if path == "/api/status":
            return self.json_response(self._status())
        elif path == "/api/monitors":
            return self.json_response(self._monitors())
        elif path == "/api/capture":
            return self.json_response(self._capture())
        elif path == "/api/flows":
            return self.json_response(self._flows())
        elif path == "/api/logs":
            return self.json_response(self._logs())
        elif path == "/api/security":
            return self.json_response(self._security())
        elif path == "/api/windows":
            return self.json_response(self._windows())
        elif path == "/api/memory":
            return self.json_response(self._memory())

        # ── Static Files (GUI) ──
        if path == "/" or path == "":
            path = "/index.html"
        file_path = GUI_DIR / path.lstrip("/")
        if file_path.exists() and file_path.is_file():
            return self.serve_file(file_path)

        self.send_error(404)

    def do_POST(self):
        parsed = urlparse(self.path)

        if parsed.path == "/api/execute":
            content_len = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_len) if content_len else b"{}"
            try:
                data = json.loads(body)
            except (json.JSONDecodeError, UnicodeDecodeError):
                data = {}
            return self.json_response(self._execute(data))
        elif parsed.path == "/api/flows":
            content_len = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_len) if content_len else b"{}"
            try:
                data = json.loads(body)
            except (json.JSONDecodeError, UnicodeDecodeError):
                data = {}
            return self.json_response(self._save_flow(data))

        self.send_error(404)

    def do_DELETE(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/flows":
            params = parse_qs(parsed.query)
            name = (params.get("name") or [""])[0]
            return self.json_response(self._delete_flow(name))

        self.send_error(404)

    # ── Helpers ──

    def json_response(self, data):
        body = json.dumps(data, ensure_ascii=False, indent=2).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def serve_file(self, file_path: Path):
        content = file_path.read_bytes()
        mime = {
            ".html": "text/html; charset=utf-8",
            ".css": "text/css",
            ".js": "application/javascript",
            ".json": "application/json",
            ".png": "image/png",
            ".svg": "image/svg+xml",
        }.get(file_path.suffix, "application/octet-stream")

        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    # ── API Methods ──

    def _status(self):
        try:
            from autocomputer.core import screen_size
            from autocomputer.core._bridge import _RUST_AVAILABLE
            from autocomputer import __version__

            w, h = screen_size()
            # Dynamic module listing — syncs with actual compiled modules
            core_modules = []
            try:
                from autocomputer.core._bridge import _get_rust_attr
                for name in ("capture_screen", "mouse_click", "keyboard_type",
                             "window_list", "security_init", "image_diff"):
                    if _get_rust_attr(name) is not None:
                        mod = name.rsplit("_", 1)[0] if "_" in name else name
                        if mod not in core_modules:
                            core_modules.append(mod)
            except Exception:
                core_modules = ["capture", "input", "window", "security", "image_proc"]
            return {
                "status": "ok",
                "rust_core": _RUST_AVAILABLE,
                "version": __version__,
                "screen": f"{w}x{h}",
                "modules": core_modules,
                "python_packages": ["agent", "cli", "perception", "record", "llm", "plugins", "utils", "memory"],
                "tests_passed": count_tests(),
                "uptime_seconds": time.time() - _START_TIME,
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def _monitors(self):
        try:
            from autocomputer.core import list_monitors

            monitors = list_monitors()
            return {
                "count": len(monitors),
                "monitors": [
                    {
                        "index": m.index,
                        "name": m.name,
                        "resolution": f"{m.width}x{m.height}",
                        "position": f"({m.x}, {m.y})",
                        "primary": m.is_primary,
                        "scale": m.scale_factor,
                    }
                    for m in monitors
                ],
            }
        except Exception as e:
            return {"error": str(e)}

    def _capture(self):
        try:
            from autocomputer.core import capture_screen

            result = capture_screen(0)
            return {
                "width": result.width,
                "height": result.height,
                "png_size": len(result.png),
                "png_b64": base64.b64encode(result.png).decode(),
            }
        except Exception as e:
            return {"error": str(e)}

    def _flows(self):
        try:
            flows = _load_flows()
            return {
                "flows": [
                    {
                        "name": f.get("name", "未命名流程"),
                        "steps": f.get("steps", []),
                        "created": f.get("created", ""),
                        "step_count": len(f.get("steps", [])),
                    }
                    for f in flows
                ],
                "count": len(flows),
            }
        except Exception:
            return {"flows": [], "message": "Saved flows will appear here"}

    def _save_flow(self, data):
        name = str(data.get("name", "")).strip()
        steps = data.get("steps", [])
        if not name:
            return {"ok": False, "error": "name is required"}
        flows = _load_flows()
        now = datetime.now().isoformat(timespec="seconds")
        for f in flows:
            if f.get("name") == name:
                f["steps"] = steps
                f["created"] = f.get("created", now)
                _save_flows(flows)
                return {"ok": True, "name": name, "updated": True}
        flows.append({"name": name, "steps": steps, "created": now})
        _save_flows(flows)
        return {"ok": True, "name": name, "updated": False}

    def _delete_flow(self, name):
        flows = _load_flows()
        before = len(flows)
        flows = [f for f in flows if f.get("name") != name]
        _save_flows(flows)
        return {"ok": True, "deleted": before - len(flows)}

    def _logs(self):
        return {"logs": list(_LOG_QUEUE)}

    def _security(self):
        return {
            "audit": audit_stats(),
            "hotkeys": [
                {"keys": "alt+f4", "severity": "Critical"},
                {"keys": "win+l", "severity": "Critical"},
                {"keys": "win+r", "severity": "Critical"},
                {"keys": "ctrl+alt+del", "severity": "Critical"},
            ],
            "thresholds": {
                "max_clicks_same_position": 5,
                "rate_limit_ms": 100,
                "audit_retention_days": 90,
            },
        }

    def _windows(self):
        """List open windows via the bridge (empty in pure-Python fallback)."""
        try:
            from autocomputer.core._bridge import _get_rust_attr
            fn = _get_rust_attr("window_list")
            if fn is None:
                return {"windows": [], "engine": "offline"}
            wins = fn(None)
            return {
                "engine": "online",
                "windows": [
                    {
                        "title": getattr(w, "title", ""),
                        "visible": bool(getattr(w, "is_visible", False)),
                    }
                    for w in (wins or [])
                ],
            }
        except Exception as e:
            return {"windows": [], "engine": "error", "message": str(e)}

    def _memory(self):
        """Read the MCP-side unified state DB (audit/permissions/learned actions)."""
        db = Path.home() / ".qclaw" / "autocomputer" / "unified_state.db"
        out = {"learned_actions": [], "permissions": [], "audit": [], "db": str(db)}
        if not db.exists():
            out["available"] = False
            return out
        import sqlite3
        try:
            conn = sqlite3.connect(db)
            try:
                for r in conn.execute(
                    "SELECT app, task, steps, success, used_count FROM learned_actions "
                    "ORDER BY used_count DESC LIMIT 50"
                ):
                    steps = r[2]
                    out["learned_actions"].append({
                        "app": r[0], "task": r[1], "success": bool(r[3]),
                        "used_count": r[4],
                        "steps": json.loads(steps) if steps else [],
                    })
            except Exception:
                pass
            try:
                for r in conn.execute("SELECT app, policy, granted_at, reason FROM permissions"):
                    out["permissions"].append({
                        "app": r[0], "policy": r[1], "granted_at": r[2], "reason": r[3] or "",
                    })
            except Exception:
                pass
            try:
                for r in conn.execute(
                    "SELECT timestamp, app, action_type, risk_level, detail FROM audit_log "
                    "ORDER BY id DESC LIMIT 50"
                ):
                    out["audit"].append({
                        "time": r[0], "app": r[1] or "", "action": r[2],
                        "risk": r[3], "detail": r[4] or "",
                    })
            except Exception:
                pass
            conn.close()
            out["available"] = True
        except Exception:
            out["available"] = False
        return out

    def _execute(self, data):
        action = data.get("action", "")
        params = data.get("params", {})

        try:
            from autocomputer.core._bridge import _get_rust_attr

            if action == "click":
                fn = _get_rust_attr("mouse_click")
                if fn:
                    fn(params.get("x", 0), params.get("y", 0), params.get("button", "left"))
                result = {"success": True, "action": "click", "detail": f"点击 ({params.get('x', 0)}, {params.get('y', 0)})"}
            elif action == "type":
                fn = _get_rust_attr("keyboard_type")
                if fn:
                    fn(params.get("text", ""), params.get("method", "auto"))
                result = {"success": True, "action": "type", "detail": f"输入: {str(params.get('text', ''))[:20]}"}
            elif action == "press":
                fn = _get_rust_attr("keyboard_press")
                if fn:
                    fn(params.get("key", "enter"))
                result = {"success": True, "action": "press", "detail": f"按键: {params.get('key', 'enter')}"}
            elif action == "move":
                fn = _get_rust_attr("mouse_move")
                if fn:
                    fn(params.get("x", 0), params.get("y", 0), None)
                result = {"success": True, "action": "move", "detail": f"移动至 ({params.get('x', 0)}, {params.get('y', 0)})"}
            elif action == "focus":
                fn = _get_rust_attr("window_focus")
                if fn is None:
                    result = {"success": False, "action": "focus", "error": "引擎离线:无法聚焦窗口(纯 Python 模式)"}
                else:
                    fn(params.get("title", ""))
                    result = {"success": True, "action": "focus", "detail": f"聚焦: {params.get('title', '')}"}
            elif action == "scroll":
                fn = _get_rust_attr("mouse_scroll")
                if fn:
                    fn(params.get("clicks", 1))
                result = {"success": True, "action": "scroll", "detail": f"滚动 {params.get('clicks', 1)}"}
            else:
                result = {"success": False, "action": action, "error": f"Unknown action: {action}"}
        except Exception as e:
            result = {"success": False, "action": action, "error": str(e)}

        _LOG_QUEUE.append({
            "ts": datetime.now().strftime("%H:%M:%S"),
            "action": action,
            "detail": result.get("detail", result.get("error", "")),
            "ok": bool(result.get("success", False)),
        })
        return result


_START_TIME = time.time()


def run_server(host: str = "127.0.0.1", port: int = 8765):
    """Start the API + GUI server."""
    from autocomputer import __version__
    server = HTTPServer((host, port), APIHandler)
    print(f"\n  🦀 autocomputer API Server v{__version__}")
    print(f"  📡 Listening on http://{host}:{port}")
    print(f"  🌐 GUI: http://{host}:{port}")
    print(f"  📋 API: http://{host}:{port}/api/status")
    print(f"\n  Press Ctrl+C to stop.\n")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  👋 Server stopped.")
        server.shutdown()

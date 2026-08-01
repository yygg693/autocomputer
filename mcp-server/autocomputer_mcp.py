#!/usr/bin/env python3
"""autocomputer MCP server — desktop GUI automation as Reasonix tools.

Maps the autocomputer core (cua.py actions + state.py audit/permissions/memory +
Windows built-in OCR) to the Model Context Protocol (stdio, newline-delimited
JSON-RPC 2.0). This is the "computer use" surface for Reasonix: the model drives
a see -> decide -> act -> verify loop through mcp__autocomputer__* tools.

Tools
  see             screenshot + OCR text(with coords) + active window + change detect
  find            locate text on screen -> ranked coordinate candidates (no click)
  act             click / type / press / scroll / move -> before/after diff + expect check
  verify_target   verify focused window title before any send (hard gate)
  apps            list windows / focus one
  audit           query the SQLite audit log
  permissions     view / set per-app policy (ask|allow|deny)
  memory          learn / recall cross-session action recipes

Safety
  * send-class acts (enter / ctrl+enter / send / submit) require a passing
    verify_target within the session or they are refused.
  * every act is audited (state.audit_log) with before/after screenshots.
  * per-app policy from state.py: "deny" hard-blocks that app.
  * pyautogui FAILSAFE stays on: mouse to screen corner (0,0) aborts.
"""
import sys, os, io, json, time, argparse
from datetime import datetime
from pathlib import Path

if sys.platform == "win32":
    try:
        # MCP stdio transport is UTF-8. Under a pipe (non-console) Windows
        # Python defaults stdin to the locale codec (e.g. gbk/cp936), which
        # corrupts any non-ASCII tool argument (type text, expect, find text,
        # verify_target expected, memory steps ...). Reconfigure all three
        # streams so JSON params round-trip losslessly.
        sys.stdin.reconfigure(encoding="utf-8", errors="replace")
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import cua
import state
import ocr as ocr_mod

try:
    import pyautogui
    pyautogui.FAILSAFE = True
except Exception:
    pyautogui = None

WORKSPACE = Path.home() / ".qclaw" / "workspace"
ACP_DIR = WORKSPACE / ".acp"
SHOT_DIR = WORKSPACE / "screenshots"
for d in (ACP_DIR, SHOT_DIR):
    d.mkdir(parents=True, exist_ok=True)

VERIFY_FILE = ACP_DIR / "verified_target.json"
LAST_FRAME_FILE = ACP_DIR / "last_frame.md5"
SEND_CLASSES = {"enter", "ctrl+enter", "send", "submit", "return"}
VERIFY_TTL_SECONDS = 90

PROTOCOL_VERSION = "2024-11-05"
SERVER_INFO = {"name": "autocomputer", "version": "1.0.0"}

# --------------------------- helpers ---------------------------


def _load_json(p: Path, default):
    try:
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default


def _save_json(p: Path, obj):
    try:
        p.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def _active_window_title() -> str:
    try:
        import ctypes
        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        length = user32.GetWindowTextLengthW(hwnd)
        if length > 0:
            buf = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buf, length + 1)
            return buf.value
    except Exception:
        pass
    return ""


def _fuzzy_match(expected: str, title: str) -> bool:
    if not expected:
        return False

    def norm(s):
        return "".join(ch for ch in s.lower() if ch.isalnum())

    e, t = norm(expected), norm(title)
    if not e:
        return False
    return e in t or t in e or e == t


def _target_verified(app: str = None) -> dict:
    st = _load_json(VERIFY_FILE, {})
    if not st.get("match"):
        return {"ok": False, "reason": "never_verified"}
    if _now() - st.get("verified_at", 0) > VERIFY_TTL_SECONDS:
        return {"ok": False, "reason": "stale"}
    if app and st.get("app") and app.lower() not in (st.get("app") or "").lower() and st.get("app") != "*":
        return {"ok": False, "reason": "app_mismatch"}
    return {"ok": True, **st}


def _now():
    return time.time()


def _md5(data) -> str:
    import hashlib
    return hashlib.md5(data).hexdigest()


def _frame_hash(img_path: str) -> str:
    try:
        import numpy as np
        from PIL import Image
        im = Image.open(img_path).convert("L").resize((64, 64))
        arr = np.asarray(im, dtype=np.uint8)
        return _md5(arr.tobytes())
    except Exception:
        try:
            return _md5(open(img_path, "rb").read())
        except Exception:
            return ""


def _capture_now(prefix="shot") -> str:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
    out = str(SHOT_DIR / f"{prefix}_{ts}.png")
    try:
        cua._capture(out)
        return out
    except Exception:
        return ""


def _ocr_on(path: str, region: str = None, max_lines: int = 40):
    if not path or not os.path.exists(path):
        return []
    try:
        lines = ocr_mod.ocr_lines(path, region)
        return lines[:max_lines]
    except Exception:
        return []


# --------------------------- tools ---------------------------


def tool_see(region=None, with_ocr=True, max_lines=40):
    img = _capture_now("see")
    dims = None
    try:
        from PIL import Image
        w, h = Image.open(img).size
        dims = {"width": w, "height": h}
    except Exception:
        pass
    title = _active_window_title()
    changed = True
    hsh = _frame_hash(img) if img else ""
    if hsh and LAST_FRAME_FILE.exists():
        changed = (LAST_FRAME_FILE.read_text().strip() != hsh)
    if hsh:
        LAST_FRAME_FILE.write_text(hsh)
    out = {
        "screenshot": img or None,
        "dimensions": dims,
        "active_window": title,
        "changed": changed,
    }
    if with_ocr:
        out["ocr"] = _ocr_on(img, region, max_lines)
    return out


def tool_find(text, app=None):
    img = _capture_now("find")
    lines = _ocr_on(img, None, 200)
    if app:
        title = _active_window_title()
        if app.lower() not in title.lower():
            return {"ok": False, "error": "app_not_focused", "active_window": title}
    cands = [ln for ln in lines if text.lower() in ln["text"].lower()]
    cands = sorted(cands, key=lambda ln: (ln["text"].lower().index(text.lower()),
                                          -ln["box"]["width"] * ln["box"]["height"]))
    return {"ok": True, "query": text, "matches": cands[:5], "screen": img}


def tool_act(action, x=None, y=None, text=None, key=None, scroll_y=None,
             expect=None, expect_gone=None, app=None, duration=0.5):
    action = (action or "").lower()
    send_class = action in SEND_CLASSES or key in SEND_CLASSES
    if send_class:
        v = _target_verified(app)
        if not v["ok"]:
            return {"ok": False, "error": "target_not_verified",
                    "reason": v.get("reason"), "hint": "call verify_target first"}

    if app:
        policy = state.permission_get(app)
        if policy == "deny":
            return {"ok": False, "error": "app_denied", "app": app}

    before = _capture_now("before")
    try:
        if action in ("click", "left_click", "double_click", "right_click", "mouse_move"):
            if x is None or y is None:
                return {"ok": False, "error": "need x,y"}
            kwargs = {"x": int(x), "y": int(y)}
            if action == "double_click":
                kwargs["clicks"] = 2
            res = cua.cua_act(action, **kwargs)
        elif action == "type":
            res = cua.cua_act("type", text=text or "")
        elif action in ("press", "key"):
            k = key or text or "enter"
            res = cua.cua_act("press", key=k)
        elif action == "scroll":
            res = cua.cua_act("scroll", x=x, y=y, scroll_y=scroll_y or 1)
        elif action == "wait":
            res = cua.cua_act("wait", duration=duration or 0.5)
        else:
            return {"ok": False, "error": "unsupported action: " + action}
    except Exception as e:
        return {"ok": False, "error": str(e)}

    after = res.get("screenshot_after", "")
    out = {"ok": res.get("status") == "success", "action": action,
           "screen_changed": res.get("screen_changed", False)}
    if expect or expect_gone:
        lines = _ocr_on(after, None, 60)
        blob = " ".join(ln["text"] for ln in lines)
        if expect:
            out["expect_met"] = expect.lower() in blob.lower()
        if expect_gone:
            out["expect_gone_met"] = expect_gone.lower() not in blob.lower()
    out["screenshot_after"] = after or None
    out["screenshot_before"] = before or None

    try:
        state.audit_log(app or _active_window_title() or "unknown",
                        action, "HIGH" if send_class else "MEDIUM",
                        {"x": x, "y": y, "text": (text or "")[:80], "key": key,
                         "ok": out["ok"]},
                        before, after)
    except Exception:
        pass
    return out


def tool_verify_target(expected, app=None):
    title = _active_window_title()
    match = _fuzzy_match(expected, title)
    rec = {"match": match, "expected": expected, "title": title,
           "app": app or title, "verified_at": _now()}
    _save_json(VERIFY_FILE, rec)
    return {"ok": True, "match": match, "expected": expected,
            "active_window": title,
            "hint": None if match else "title mismatch - do NOT send; focus the right window and retry"}


def tool_apps(action="list", name=None):
    try:
        import pygetwindow as gw
    except Exception as e:
        return {"ok": False, "error": str(e)}
    if action == "list":
        titles = sorted({w.title for w in gw.getAllWindows() if w.title.strip()})
        return {"ok": True, "windows": titles[:50]}
    if action == "focus" and name:
        wins = gw.getWindowsWithTitle(name)
        if not wins:
            return {"ok": False, "error": "window not found", "query": name}
        try:
            wins[0].activate()
            return {"ok": True, "focused": name}
        except Exception as e:
            return {"ok": False, "error": str(e), "query": name}
    return {"ok": False, "error": "apps: action=list|focus, focus needs name"}


def tool_audit(app=None, risk=None, limit=20):
    try:
        rows = state.audit_query(app, risk, min(int(limit), 100))
        return {"ok": True, "rows": rows}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def tool_permissions(action="list", app=None, policy=None):
    if action == "list":
        return {"ok": True, "permissions": state.permission_list()}
    if action == "get" and app:
        return {"ok": True, "app": app, "policy": state.permission_get(app)}
    if action == "set" and app and policy in ("ask", "allow", "deny"):
        state.permission_set(app, policy)
        return {"ok": True, "app": app, "policy": policy}
    return {"ok": False, "error": "permissions: action=list|get|set, set needs app+policy(ask|allow|deny)"}


def tool_memory(action="recall", app=None, task=None, steps=None, limit=5):
    if action == "recall":
        if not app:
            return {"ok": False, "error": "recall needs app"}
        rows = state.memory_recall(app, task, min(int(limit), 20))
        return {"ok": True, "app": app, "recipes": rows}
    if action == "learn" and app and task and steps:
        sid = state.memory_learn(app, task, steps)
        return {"ok": True, "app": app, "task": task, "id": sid}
    return {"ok": False, "error": "memory: action=recall|learn, learn needs app+task+steps"}


TOOLS = [
    {"name": "see", "description":
     "Screenshot the screen and return OCR text with coordinates (token-efficient, "
     "model is text-only). Returns active window title, dimensions, change flag, and "
     "up to 40 OCR lines [{text,box,center}]. Use before and after actions.",
     "inputSchema": {"type": "object", "properties": {
         "region": {"type": "string", "description": "optional x,y,w,h crop"},
         "max_lines": {"type": "integer", "description": "cap OCR lines (default 40)"}},
         "required": []}},
    {"name": "find", "description":
     "Locate text on screen via OCR and return ranked coordinate candidates (no click). "
     "Returns matches [{text,center,box}]. Then call act with those coordinates.",
     "inputSchema": {"type": "object", "properties": {
         "text": {"type": "string", "description": "text to find (substring)"},
         "app": {"type": "string", "description": "optional: require this app focused"}},
         "required": ["text"]}},
    {"name": "act", "description":
     "Execute a desktop action with automatic before/after screenshot diff and audit. "
     "Actions: click|double_click|right_click|mouse_move (need x,y), type (need text), "
     "press (need key like 'enter'/'ctrl+enter'), scroll (need scroll_y), wait. "
     "SEND-class keys (enter/ctrl+enter/send/submit) REQUIRE a passing verify_target first.",
     "inputSchema": {"type": "object", "properties": {
         "action": {"type": "string", "enum": ["click", "double_click", "right_click",
                     "mouse_move", "type", "press", "scroll", "wait"]},
         "x": {"type": "integer"}, "y": {"type": "integer"},
         "text": {"type": "string"}, "key": {"type": "string"},
         "scroll_y": {"type": "integer"},
         "expect": {"type": "string", "description": "text that must appear after the action"},
         "expect_gone": {"type": "string", "description": "text that must disappear"},
         "app": {"type": "string"}, "duration": {"type": "number"}},
         "required": ["action"]}},
    {"name": "verify_target", "description":
     "VERIFY the focused window matches the intended target BEFORE any send (the #1 GUI "
     "failure mode is sending to the wrong recipient). Compares active window title "
     "against expected. Must pass within 90s for send-class act calls.",
     "inputSchema": {"type": "object", "properties": {
         "expected": {"type": "string", "description": "expected window title (fuzzy match)"},
         "app": {"type": "string"}}, "required": ["expected"]}},
    {"name": "apps", "description":
     "List open windows or focus one by title. Useful before launching/clicks to avoid "
     "duplicate instances.",
     "inputSchema": {"type": "object", "properties": {
         "action": {"type": "string", "enum": ["list", "focus"]},
         "name": {"type": "string"}}, "required": ["action"]}},
    {"name": "audit", "description": "Query the desktop-automation audit log (SQLite).",
     "inputSchema": {"type": "object", "properties": {
         "app": {"type": "string"}, "risk": {"type": "string"}, "limit": {"type": "integer"}},
         "required": []}},
    {"name": "permissions", "description":
     "View or set per-app desktop-automation policy: ask|allow|deny. deny hard-blocks act() on that app.",
     "inputSchema": {"type": "object", "properties": {
         "action": {"type": "string", "enum": ["list", "get", "set"]},
         "app": {"type": "string"}, "policy": {"type": "string", "enum": ["ask", "allow", "deny"]}},
         "required": ["action"]}},
    {"name": "memory", "description":
     "Cross-session action recipes: recall(app[,task]) or learn(app,task,steps).",
     "inputSchema": {"type": "object", "properties": {
         "action": {"type": "string", "enum": ["recall", "learn"]},
         "app": {"type": "string"}, "task": {"type": "string"},
         "steps": {"type": "array", "items": {"type": "object"}}, "limit": {"type": "integer"}},
         "required": ["action"]}},
]

HANDLERS = {
    "see": tool_see, "find": tool_find, "act": tool_act,
    "verify_target": tool_verify_target, "apps": tool_apps,
    "audit": tool_audit, "permissions": tool_permissions, "memory": tool_memory,
}


def call_tool(name: str, args: dict) -> dict:
    fn = HANDLERS.get(name)
    if not fn:
        return {"ok": False, "error": "unknown tool: " + name}
    try:
        result = fn(**args)
    except TypeError as e:
        result = {"ok": False, "error": "bad arguments: " + str(e)}
    except Exception as e:
        result = {"ok": False, "error": type(e).__name__ + ": " + str(e)}
    return result


def rpc_handle(msg: dict):
    method = msg.get("method")
    mid = msg.get("id")
    if method == "initialize":
        return {"jsonrpc": "2.0", "id": mid, "result": {
            "protocolVersion": (msg.get("params", {}).get("protocolVersion") or PROTOCOL_VERSION),
            "capabilities": {"tools": {}},
            "serverInfo": SERVER_INFO}}
    if method == "notifications/initialized":
        return None
    if method == "ping":
        return {"jsonrpc": "2.0", "id": mid, "result": {}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": mid, "result": {"tools": TOOLS}}
    if method == "tools/call":
        params = msg.get("params", {})
        name = params.get("name", "")
        args = params.get("arguments", {}) or {}
        result = call_tool(name, args)
        text = json.dumps(result, ensure_ascii=False)
        return {"jsonrpc": "2.0", "id": mid, "result": {
            "content": [{"type": "text", "text": text}],
            "isError": result.get("ok") is False and "error" in result}}
    return {"jsonrpc": "2.0", "id": mid, "result": {
        "content": [{"type": "text", "text": json.dumps(
            {"ok": False, "error": "unhandled method " + method})}],
        "isError": True}}


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--selftest":
        print(json.dumps(call_tool("see", {}), ensure_ascii=False))
        return
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except Exception:
            continue
        resp = rpc_handle(msg)
        if resp is not None:
            sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()

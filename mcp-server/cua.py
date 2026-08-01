#!/usr/bin/env python3
"""
CUA Compatibility Layer — makes autocomputer speak OpenAI CUA / Claude Computer Use schema.

This module translates autocomputer operations into CUA-compatible action schemas
so that autocomputer can be used as a drop-in "computer" tool for agents expecting
the CUA/Claude Computer Use API contract.

Two modes:
  1. cua-see   — take screenshot, return {type: "computer_screenshot", ...}
  2. cua-act   — accept CUA action + execute it, return screenshot after

Usage:
  python cua.py see [--region x,y,w,h]
      Capture screenshot in CUA-compatible format.

  python cua.py act click --x 500 --y 300
  python cua.py act type --text "hello"
  python cua.py act key --keys "enter"
  python cua.py act scroll --x 500 --y 300 --scroll_y 100

CUA Action Schema (subset we support):
  {
    "action": "left_click" | "type" | "key" | "scroll" | "mouse_move" | "right_click",
    "coordinate": [x, y],   // for click, move
    "text": "...",          // for type
    "keys": [...],          // for key
    "scroll_y": int,        // for scroll
  }
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

import json
import argparse
import time
import os
from pathlib import Path
from datetime import datetime

SKILL_DIR = Path(__file__).parent
def _data_dir() -> Path:
    """Runtime data root: %APPDATA%/autocomputer (Windows) or ~/.config/autocomputer."""
    base = os.environ.get("APPDATA") or str(Path.home() / ".config")
    d = Path(base) / "autocomputer"
    d.mkdir(parents=True, exist_ok=True)
    return d

WORKSPACE = _data_dir() / "workspace"
SCREENSHOT_DIR = WORKSPACE / "screenshots"
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)

# ── Helpers ──

def _get_screen_info() -> dict:
    """Get screen/monitor info for CUA context."""
    try:
        from screen import get_monitors
        monitors = get_monitors()
        if monitors:
            primary = [m for m in monitors if m.get("primary")][0] if any(m.get("primary") for m in monitors) else monitors[0]
            return {
                "display_width_px": primary["width"],
                "display_height_px": primary["height"],
                "monitor_count": len(monitors),
                "monitors": monitors
            }
    except Exception:
        pass

    # Fallback
    try:
        from PIL import ImageGrab
        img = ImageGrab.grab()
        return {"display_width_px": img.width, "display_height_px": img.height}
    except Exception:
        return {}


def _get_active_window() -> dict:
    """Get active window info for CUA context."""
    try:
        import ctypes
        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        length = user32.GetWindowTextLengthW(hwnd)
        if length > 0:
            buf = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buf, length + 1)
            return {"active_window": buf.value}
    except Exception:
        pass
    return {}


def _capture(output_path: str, region: str = None):
    """Capture screenshot using MSS or PIL."""
    try:
        import mss
        import numpy as np
        from PIL import Image

        with mss.MSS() as sct:
            if region:
                x, y, w, h = map(int, region.split(","))
                monitor = {"top": y, "left": x, "width": w, "height": h}
            else:
                monitor = sct.monitors[0]
            arr = np.array(sct.grab(monitor))
            img = Image.fromarray(arr)
            img.save(output_path)
            return img.width, img.height
    except ImportError:
        pass

    from PIL import ImageGrab
    img = ImageGrab.grab()
    if region:
        x, y, w, h = map(int, region.split(","))
        img = img.crop((x, y, x + w, y + h))
    img.save(output_path)
    return img.width, img.height


# ── CUA See ──

def cua_see(region: str = None) -> dict:
    """
    CUA-compatible screenshot capture.

    Returns: {
      "type": "computer_screenshot",
      "image_url": "file:///path/to/screenshot.png",
      "dimensions": {"width": 1920, "height": 1080},
      "active_window": "...",
      "monitors": [...]
    }
    """
    ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    output = str(SCREENSHOT_DIR / f"cua_{ts}.png")

    width, height = _capture(output, region)

    result = {
        "type": "computer_screenshot",
        "image_path": output,
        "image_url": f"file:///{output.replace(chr(92), '/')}",
        "dimensions": {"width": width, "height": height},
    }

    # Enrich with screen + window context
    screen_info = _get_screen_info()
    if screen_info:
        result.update(screen_info)

    win_info = _get_active_window()
    if win_info:
        result.update(win_info)

    # Try to get OCR text for context
    try:
        import subprocess
        ocr_script = SKILL_DIR / "ocr.py"
        ocr_result = subprocess.run(
            [sys.executable, str(ocr_script), "read", output],
            capture_output=True, text=True,
            encoding='utf-8', errors='replace',
            timeout=30
        )
        if ocr_result.stdout:
            ocr_data = json.loads(ocr_result.stdout)
            if ocr_data.get("status") == "ok":
                texts = [t["text"] for t in ocr_data.get("texts", [])[:20]]
                result["ocr_texts"] = texts
    except Exception:
        pass

    return result


# ── CUA Act ──

def cua_act(action_type: str, **kwargs) -> dict:
    """
    Execute a CUA-compatible action.

    Supported actions:
      - left_click / click: coordinate=[x, y]
      - right_click: coordinate=[x, y]
      - double_click: coordinate=[x, y]
      - mouse_move: coordinate=[x, y]
      - type: text="..."
      - key: keys=["enter"] or keys=["ctrl", "c"]
      - scroll: coordinate=[x, y], scroll_y=100
      - screenshot: (no args)
      - wait: text="..."

    Returns: {
      "status": "success" | "error",
      "action": "...",
      "screenshot_after": "path/to/after.png",
      ...
    }
    """
    import pyautogui

    before_screenshot = _quick_capture("before")

    try:
        if action_type in ("left_click", "click"):
            x, y = kwargs["x"], kwargs["y"]
            if "clicks" in kwargs and kwargs["clicks"] == 2:
                pyautogui.doubleClick(x, y)
                action_detail = {"action": "double_click", "coordinate": [x, y]}
            else:
                pyautogui.click(x, y)
                action_detail = {"action": "left_click", "coordinate": [x, y]}

        elif action_type == "right_click":
            x, y = kwargs["x"], kwargs["y"]
            pyautogui.rightClick(x, y)
            action_detail = {"action": "right_click", "coordinate": [x, y]}

        elif action_type == "double_click":
            x, y = kwargs["x"], kwargs["y"]
            pyautogui.doubleClick(x, y)
            action_detail = {"action": "double_click", "coordinate": [x, y]}

        elif action_type == "mouse_move":
            x, y = kwargs["x"], kwargs["y"]
            pyautogui.moveTo(x, y, duration=0.3)
            action_detail = {"action": "mouse_move", "coordinate": [x, y]}

        elif action_type == "type":
            text = kwargs["text"]
            # Use clipboard for non-ASCII
            if any(ord(c) > 127 for c in text):
                import pyperclip
                pyperclip.copy(text)
                pyautogui.hotkey('ctrl', 'v')
            else:
                pyautogui.typewrite(text, interval=0.05)
            action_detail = {"action": "type", "text": text}

        elif action_type == "key":
            keys = kwargs.get("keys", [kwargs.get("key", "enter")])
            if isinstance(keys, str):
                keys = [keys]
            if len(keys) == 1:
                pyautogui.press(keys[0])
            else:
                pyautogui.hotkey(*keys)
            action_detail = {"action": "key", "keys": keys}

        elif action_type == "scroll":
            x = kwargs.get("x")
            y = kwargs.get("y")
            scroll_y = kwargs.get("scroll_y", kwargs.get("clicks", 1))
            if x is not None and y is not None:
                pyautogui.scroll(scroll_y, x, y)
            else:
                pyautogui.scroll(scroll_y)
            action_detail = {"action": "scroll", "scroll_y": scroll_y}

        elif action_type == "screenshot":
            action_detail = {"action": "screenshot"}
            time.sleep(0.1)

        elif action_type == "wait":
            # Wait for UI to settle
            time.sleep(kwargs.get("duration", 0.5))
            action_detail = {"action": "wait"}

        elif action_type == "press":
            key = kwargs.get("key", "enter")
            if "+" in key:
                parts = [k.strip() for k in key.split("+")]
                pyautogui.hotkey(*parts)
            else:
                pyautogui.press(key)
            action_detail = {"action": "press", "key": key}

        else:
            return {"status": "error", "message": f"Unsupported CUA action: {action_type}"}

        # Wait for UI to settle
        time.sleep(0.3)

        # Capture after screenshot
        after_screenshot = _quick_capture("after")

        result = {
            "status": "success",
            **action_detail,
            "screenshot_before": before_screenshot,
            "screenshot_after": after_screenshot,
        }

        # Check if screen changed
        if before_screenshot and after_screenshot:
            try:
                from PIL import Image
                import numpy as np
                before_img = Image.open(before_screenshot).resize((192, 108))
                after_img = Image.open(after_screenshot).resize((192, 108))
                diff = np.abs(np.array(before_img, dtype=np.float32) -
                              np.array(after_img, dtype=np.float32))
                changed = float(np.mean(diff > 25)) > 0.003
                result["screen_changed"] = changed
            except Exception:
                pass

        return result

    except Exception as e:
        return {"status": "error", "action": action_type, "message": str(e)}


def _quick_capture(prefix: str) -> str:
    """Capture a quick screenshot for before/after comparison."""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    output = str(SCREENSHOT_DIR / f"cua_{prefix}_{ts}.png")
    try:
        _capture(output)
        return output
    except Exception:
        return ""


# ── CUA Pulse (see + change detect) ──

def cua_pulse(region: str = None) -> dict:
    """
    Fast combo: screenshot + change detection. Returns screenshot only if changed.

    This is the Codex-grade fast loop: capture → check → return only meaningful frames.
    """
    try:
        from agent import capture_memory, has_changed, save_last_state, compute_simple_hash

        img = capture_memory()
        change_info = has_changed(img)

        if change_info["changed"]:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            output = str(SCREENSHOT_DIR / f"cua_pulse_{ts}.png")
            img.save(output)

            return {
                "type": "computer_screenshot",
                "image_path": output,
                "changed": True,
                "change_ratio": change_info["ratio"],
                "dimensions": {"width": img.width, "height": img.height}
            }
        else:
            return {
                "type": "computer_screenshot",
                "image_path": None,
                "changed": False,
            }
    except ImportError:
        # Fallback: always capture
        return cua_see(region)


# ── CLI ──

def main():
    parser = argparse.ArgumentParser(description="CUA Compatibility Layer")
    sub = parser.add_subparsers(dest="cmd")

    # cua-see
    see = sub.add_parser("see", help="CUA-compatible screenshot")
    see.add_argument("--region", help="Capture region x,y,w,h")
    see.add_argument("--ocr", action="store_true", help="Include OCR texts")

    # cua-pulse
    pulse = sub.add_parser("pulse", help="Fast screenshot + change detect")
    pulse.add_argument("--region")

    # cua-act
    act = sub.add_parser("act", help="Execute CUA action")
    act.add_argument("action_type", choices=[
        "left_click", "click", "right_click", "double_click",
        "mouse_move", "type", "key", "scroll", "screenshot", "wait", "press"
    ])
    act.add_argument("--x", type=int)
    act.add_argument("--y", type=int)
    act.add_argument("--text")
    act.add_argument("--key")
    act.add_argument("--keys", nargs="+")
    act.add_argument("--clicks", type=int)
    act.add_argument("--scroll_y", type=int)
    act.add_argument("--duration", type=float)
    act.add_argument("--retry", type=int, default=1)

    args = parser.parse_args()

    if args.cmd == "see":
        result = cua_see(getattr(args, 'region', None))
        print(json.dumps(result, ensure_ascii=False, indent=2))

    elif args.cmd == "pulse":
        result = cua_pulse(getattr(args, 'region', None))
        print(json.dumps(result, ensure_ascii=False, indent=2))

    elif args.cmd == "act":
        kwargs = {}
        for attr in ["x", "y", "text", "key", "keys", "clicks", "scroll_y", "duration", "retry"]:
            v = getattr(args, attr, None)
            if v is not None:
                kwargs[attr] = v

        # Handle retry
        max_tries = kwargs.pop("retry", 1)
        for attempt in range(max_tries):
            result = cua_act(args.action_type, **kwargs)
            if result.get("status") == "success":
                print(json.dumps(result, ensure_ascii=False, indent=2))
                return
            if attempt < max_tries - 1:
                time.sleep(0.5 * (attempt + 1))

        print(json.dumps(result, ensure_ascii=False, indent=2))

    else:
        parser.print_help()


if __name__ == "__main__":
    main()

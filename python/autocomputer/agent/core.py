"""
CoT (Chain-of-Thought) Agent — context collection, planning, execution, tracking.
"""

import base64
import io
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from autocomputer.core import (
    capture_screen,
    list_monitors,
    screen_size,
)
from autocomputer.core._bridge import _get_rust_attr


@dataclass
class ScreenContext:
    """Snapshot of current screen state for AI decision-making."""
    monitor_count: int = 1
    resolution: tuple[int, int] = (1920, 1080)
    screenshot_png_b64: str = ""
    ocr_text: list[str] = field(default_factory=list)
    active_window: str = ""
    timestamp: float = 0.0

    @classmethod
    def capture(cls, with_ocr: bool = False) -> "ScreenContext":
        """Capture current screen context."""
        monitors = list_monitors()
        size = screen_size()
        result = capture_screen(0)

        ctx = ScreenContext(
            monitor_count=len(monitors),
            resolution=size,
            screenshot_png_b64=base64.b64encode(result.png).decode(),
            timestamp=time.time(),
        )

        # TODO: OCR integration (Phase 7)
        # if with_ocr: ctx.ocr_text = ocr_recognize(result.png)

        # Try to detect active window
        try:
            window_list_fn = _get_rust_attr("window_list")
            if window_list_fn:
                windows = window_list_fn(None)
                for w in windows:
                    if getattr(w, "is_visible", False):
                        ctx.active_window = getattr(w, "title", "")
                        break
        except Exception:
            pass

        return ctx

    def to_prompt(self) -> str:
        """Format context for LLM prompt."""
        return (
            f"Screen: {self.resolution[0]}x{self.resolution[1]}, "
            f"Monitors: {self.monitor_count}, "
            f"Window: {self.active_window or 'unknown'}\n"
            f"OCR text: {', '.join(self.ocr_text) if self.ocr_text else '(none)'}"
        )


@dataclass
class ActionStep:
    """A single step in an action plan."""
    action: str  # "click", "type", "press", "wait", "see", "scroll"
    params: dict[str, Any] = field(default_factory=dict)
    reasoning: str = ""


@dataclass
class ActionPlan:
    """Sequence of steps to execute."""
    goal: str
    steps: list[ActionStep] = field(default_factory=list)
    context: Optional[ScreenContext] = None

    def add(self, action: str, params: dict[str, Any] | None = None, reasoning: str = "") -> "ActionPlan":
        self.steps.append(ActionStep(action=action, params=params or {}, reasoning=reasoning))
        return self


class AgentExecutor:
    """Execute action plans using the Rust core engine."""

    _last_action_time: float = 0.0

    @staticmethod
    def execute_step(step: ActionStep) -> dict[str, Any]:
        """Execute a single action step. Returns result dict."""
        result: dict[str, Any] = {"action": step.action, "success": True}

        try:
            if step.action == "click":
                x = step.params.get("x", 0)
                y = step.params.get("y", 0)
                bt = step.params.get("button", "left")
                mouse_click_fn = _get_rust_attr("mouse_click")
                if mouse_click_fn:
                    mouse_click_fn(x, y, bt)
                result["detail"] = f"Clicked ({x},{y})"

            elif step.action == "type":
                text = step.params.get("text", "")
                method = step.params.get("method", "auto")
                keyboard_type_fn = _get_rust_attr("keyboard_type")
                if keyboard_type_fn:
                    keyboard_type_fn(text, method)
                result["detail"] = f"Typed '{text[:30]}...'" if len(text) > 30 else f"Typed '{text}'"

            elif step.action == "press":
                key = step.params.get("key", "enter")
                keyboard_press_fn = _get_rust_attr("keyboard_press")
                if keyboard_press_fn:
                    keyboard_press_fn(key)
                result["detail"] = f"Pressed '{key}'"

            elif step.action == "wait":
                ms = step.params.get("ms", 1000)
                time.sleep(ms / 1000.0)
                result["detail"] = f"Waited {ms}ms"

            elif step.action == "scroll":
                clicks = step.params.get("clicks", 1)
                mouse_scroll_fn = _get_rust_attr("mouse_scroll")
                if mouse_scroll_fn:
                    mouse_scroll_fn(clicks)
                result["detail"] = f"Scrolled {clicks} clicks"

            elif step.action == "see":
                ctx = ScreenContext.capture()
                result["context"] = ctx
                result["detail"] = f"Screenshot {ctx.resolution}"

            elif step.action == "move":
                x = step.params.get("x", 0)
                y = step.params.get("y", 0)
                mouse_move_fn = _get_rust_attr("mouse_move")
                if mouse_move_fn:
                    mouse_move_fn(x, y, None)
                result["detail"] = f"Moved to ({x},{y})"

            else:
                result["success"] = False
                result["error"] = f"Unknown action: {step.action}"

        except Exception as e:
            result["success"] = False
            result["error"] = str(e)

        return result

    @staticmethod
    def execute_plan(plan: ActionPlan, verify: bool = True) -> dict[str, Any]:
        """Execute all steps in a plan."""
        results: list[dict[str, Any]] = []
        start = time.time()

        for step in plan.steps:
            r = AgentExecutor.execute_step(step)
            results.append(r)
            if not r["success"]:
                break

        if verify and results:
            # Final screenshot for verification
            try:
                ctx = ScreenContext.capture()
                return {
                    "success": all(r["success"] for r in results),
                    "steps": results,
                    "elapsed_ms": (time.time() - start) * 1000,
                    "final_context": ctx,
                }
            except Exception:
                pass

        return {
            "success": all(r["success"] for r in results),
            "steps": results,
            "elapsed_ms": (time.time() - start) * 1000,
        }


# ── State tracker ──

@dataclass
class TrackerState:
    """Tracks screen changes between action steps."""
    before: Optional[ScreenContext] = None
    after: Optional[ScreenContext] = None
    changed: bool = False
    change_percent: float = 0.0


class StateTracker:
    """Tracks screen state changes to verify actions had intended effect."""

    @staticmethod
    def before_action() -> TrackerState:
        return TrackerState(before=ScreenContext.capture())

    @staticmethod
    def after_action(state: TrackerState) -> TrackerState:
        state.after = ScreenContext.capture()
        if state.before and state.after:
            has_changed_fn = _get_rust_attr("has_changed")
            if has_changed_fn and state.before.screenshot_png_b64:
                # Decode screenshots to raw RGBA
                import base64 as b64
                before_raw = b64.b64decode(state.before.screenshot_png_b64)
                after_raw = b64.b64decode(state.after.screenshot_png_b64)
                # Use PNG bytes directly — Rust side handles it
                try:
                    state.changed = has_changed_fn(
                        before_raw, after_raw,
                        state.before.resolution[0], state.before.resolution[1], 10
                    )
                except Exception:
                    state.changed = True  # Assume changed on error
            else:
                state.changed = True
        return state

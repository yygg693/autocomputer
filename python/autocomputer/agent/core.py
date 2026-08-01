"""
CoT (Chain-of-Thought) Agent — context collection, planning, execution, tracking.
Phase 1: Wired PerceptionManager → ScreenContext, LLM planning loop, self-correction.
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


# ── Screen context (wired to PerceptionManager) ──

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
        """Capture current screen context, optionally with OCR text extraction."""
        monitors = list_monitors()
        size = screen_size()
        result = capture_screen(0)

        ctx = ScreenContext(
            monitor_count=len(monitors),
            resolution=size,
            screenshot_png_b64=base64.b64encode(result.png).decode(),
            timestamp=time.time(),
        )

        # ── OCR integration (Phase 1) ──
        if with_ocr:
            try:
                from autocomputer.perception.engine import PerceptionManager
                pm = PerceptionManager()
                available = pm.list_available()
                if available:
                    pr = pm.recognize(result.png)
                    ctx.ocr_text = [r.text for r in pr.regions] if pr.regions else [pr.full_text]
            except ImportError:
                pass  # perception extras not installed
            except Exception:
                pass  # OCR backend installed but unusable (e.g. tesseract missing) — degrade

        # Detect active window
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
        lines = [
            f"Screen: {self.resolution[0]}x{self.resolution[1]}",
            f"Monitors: {self.monitor_count}",
            f"Window: {self.active_window or 'unknown'}",
        ]
        if self.ocr_text:
            lines.append(f"OCR text on screen: {', '.join(self.ocr_text[:20])}")
        return "\n".join(lines)


# ── Plan types ──

@dataclass
class ActionStep:
    """A single step in an action plan."""

    action: str  # "click", "type", "press", "wait", "see", "scroll", "move"
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


# ── Executor ──

class AgentExecutor:
    """Execute action plans using the Rust core engine.

    Call enable_security() once at startup to enable safety checks globally.
    All execute_* methods will then pass through the security guard automatically.
    """

    _security_enabled: bool = False
    _guard_click: Any = None
    _guard_hotkey: Any = None

    @classmethod
    def enable_security(cls, config_toml: Optional[str] = None) -> None:
        """Enable security guard. Call once at application startup."""
        try:
            init_fn = _get_rust_attr("security_init")
            if init_fn:
                init_fn(config_toml)
            cls._guard_click = _get_rust_attr("guard_click")
            cls._guard_hotkey = _get_rust_attr("guard_hotkey")
            cls._security_enabled = cls._guard_click is not None
        except Exception:
            cls._security_enabled = False

    @staticmethod
    def execute_step(step: ActionStep) -> dict[str, Any]:
        """Execute a single action step. Returns result dict."""
        result: dict[str, Any] = {"action": step.action, "success": True}

        try:
            if step.action == "click":
                x = step.params.get("x", 0)
                y = step.params.get("y", 0)
                bt = step.params.get("button", "left")
                # Security check — use actual screen size, not hardcoded
                if AgentExecutor._security_enabled and AgentExecutor._guard_click:
                    sw, sh = screen_size()
                    x, y = AgentExecutor._guard_click(x, y, sw, sh)
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
                preview = text[:30] + "..." if len(text) > 30 else text
                result["detail"] = f"Typed '{preview}'"

            elif step.action == "press":
                key = step.params.get("key", "enter")
                # Security: block dangerous hotkeys
                if AgentExecutor._security_enabled and AgentExecutor._guard_hotkey:
                    AgentExecutor._guard_hotkey([key])
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
                result["detail"] = f"Screenshot {ctx.resolution}"
                result["context"] = ctx

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
    def execute_plan(
        plan: ActionPlan,
        verify: bool = True,
        max_retries: int = 3,
    ) -> dict[str, Any]:
        """Execute all steps in a plan, with self-correction on failure.

        On step failure: re-capture screen context, attempt recovery (max_retries).
        """
        results: list[dict[str, Any]] = []
        start = time.time()
        retries = 0

        i = 0
        while i < len(plan.steps):
            step = plan.steps[i]
            r = AgentExecutor.execute_step(step)
            results.append(r)

            if not r["success"] and retries < max_retries:
                retries += 1
                # Re-capture context to see what changed
                r["retry"] = retries
                r["context_after_error"] = ScreenContext.capture()
                # Insert a small wait before retry
                time.sleep(0.5)
                continue  # retry same step
            elif not r["success"]:
                break

            retries = 0  # reset on success
            i += 1

        # Final verification
        final_ctx = None
        if verify and results:
            try:
                final_ctx = ScreenContext.capture()
                tracker = StateTracker()
                state = tracker.before_action()
                state = tracker.after_action(state)
                if not state.changed:
                    # Something might be off, but still return results
                    pass
            except Exception:
                pass

        return {
            "success": all(r["success"] for r in results),
            "steps": results,
            "elapsed_ms": (time.time() - start) * 1000,
            "retries_used": retries,
            "final_context": final_ctx,
        }


# ── LLM-driven Agent ──

SYSTEM_PROMPT = """You are a desktop automation agent. Given a goal and current screen context, output a sequence of actions.

Available actions:
- click: {x, y, button?} — click at position (use OCR coordinates if available)
- type: {text, method?} — type text (method: "auto" for clipboard-based Chinese)
- press: {key} — press single key (enter, escape, tab, ctrl+c, etc.)
- wait: {ms} — wait milliseconds
- scroll: {clicks} — positive=up, negative=down
- move: {x, y} — move mouse
- see: {} — take screenshot (for vision-based verification)

Respond ONLY with a JSON array of action objects. Each object: {"action": "...", "params": {...}, "reasoning": "why this step"}"""


class Agent:
    """LLM-driven desktop automation agent.

    Uses screen context + optional LLM to create and execute action plans.
    """

    def __init__(self, model: str = "openai/gpt-4o", max_retries: int = 3):
        self.model = model
        self.max_retries = max_retries

    def plan(self, goal: str, context: Optional[ScreenContext] = None) -> ActionPlan:
        """Generate an action plan from a natural-language goal.

        Without an LLM configured, falls back to single-step capture-and-report.
        """
        if context is None:
            context = ScreenContext.capture(with_ocr=True)

        plan = ActionPlan(goal=goal, context=context)

        # Try LLM-based planning first
        try:
            steps = self._llm_plan(context, goal)
            for s in steps:
                plan.add(s["action"], s.get("params", {}), s.get("reasoning", ""))
            return plan
        except Exception:
            # Fallback: at minimum, capture context
            plan.add("see", {}, "LLM unavailable — captured screen context only")
            return plan

    def _llm_plan(self, context: ScreenContext, goal: str) -> list[dict[str, Any]]:
        """Use litellm to generate action steps from goal + context."""
        import json

        user_prompt = f"Goal: {goal}\n\n{context.to_prompt()}"
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]

        try:
            import litellm  # type: ignore
            response = litellm.completion(
                model=self.model,
                messages=messages,
                max_tokens=2000,
                temperature=0.3,
            )
            raw = response.choices[0].message.content or "[]"
            # Strip markdown fences if present
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[1]
                if raw.endswith("```"):
                    raw = raw[:-3]
            return json.loads(raw)
        except ImportError:
            raise RuntimeError("litellm not installed — pip install autocomputer[llm]")
        except json.JSONDecodeError as e:
            raise RuntimeError(f"LLM returned invalid JSON: {e}")

    def run(self, goal: str) -> dict[str, Any]:
        """Plan + execute for a natural-language goal. All-in-one."""
        plan = self.plan(goal)
        return AgentExecutor.execute_plan(plan, verify=True, max_retries=self.max_retries)


# ── State tracker (enhanced) ──

@dataclass
class TrackerState:
    """Tracks screen changes between action steps."""

    before: Optional[ScreenContext] = None
    after: Optional[ScreenContext] = None
    changed: bool = False
    change_percent: float = 0.0  # Phase 1: actually computed


class StateTracker:
    """Tracks screen state changes to verify actions had intended effect."""

    @staticmethod
    def before_action() -> TrackerState:
        return TrackerState(before=ScreenContext.capture(with_ocr=True))

    @staticmethod
    def after_action(state: TrackerState) -> TrackerState:
        state.after = ScreenContext.capture()
        if state.before and state.after:
            has_changed_fn = _get_rust_attr("has_changed")
            if has_changed_fn and state.before.screenshot_png_b64 and state.after.screenshot_png_b64:
                before_raw = base64.b64decode(state.before.screenshot_png_b64)
                after_raw = base64.b64decode(state.after.screenshot_png_b64)
                try:
                    state.changed = has_changed_fn(
                        before_raw, after_raw,
                        state.before.resolution[0],
                        state.before.resolution[1],
                        10,  # threshold
                    )
                    # Also get diff percentage
                    diff_fn = _get_rust_attr("image_diff")
                    if diff_fn:
                        diff_result = diff_fn(
                            before_raw, after_raw,
                            state.before.resolution[0],
                            state.before.resolution[1],
                            10,
                        )
                        state.change_percent = getattr(diff_result, "percent", 0.0)
                except Exception:
                    state.changed = True
                    state.change_percent = 100.0
            else:
                state.changed = True
                state.change_percent = 100.0
        return state

    @staticmethod
    def describe(state: TrackerState) -> str:
        """Human-readable change description."""
        if not state.changed:
            return "No screen change detected"
        return (
            f"Screen changed: {state.change_percent:.1f}% pixels affected | "
            f"Before: {state.before.resolution if state.before else '?'} | "
            f"After: {state.after.resolution if state.after else '?'}"
        )

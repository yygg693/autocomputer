"""
Intelligent enhancements — cross-step memory, flow generalization, performance profiling.

Phase 4 additions to the Agent system.
"""

import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Optional

from .core import ActionPlan, ActionStep, ScreenContext


# ═══════════════════════════════════════════════════════
# Context Memory — persistent state across action steps
# ═══════════════════════════════════════════════════════

@dataclass
class ContextMemory:
    """Persistent state across Agent steps. Remembers what was done to avoid repetition.

    Tracks: opened windows, last screenshot, completed sub-goals, 
    known UI positions (text → coordinates mappings), and action history.
    """

    # Track opened windows so we don't re-open them
    opened_windows: set[str] = field(default_factory=set)

    # Completed sub-goals (to avoid re-doing)
    completed_goals: list[str] = field(default_factory=list)

    # text → (x, y) mappings from OCR, speeds up repeated clicks
    known_positions: dict[str, tuple[int, int]] = field(default_factory=dict)

    # Screenshot before most recent action
    last_screenshot: Optional[ScreenContext] = None

    # Full action history for review
    action_history: list[dict[str, Any]] = field(default_factory=list)

    def record_window(self, title: str) -> None:
        """Mark a window as opened/visible."""
        self.opened_windows.add(title.lower())

    def is_window_open(self, title: str) -> bool:
        """Check if a window was previously encountered."""
        return title.lower() in self.opened_windows

    def record_position(self, text: str, x: int, y: int) -> None:
        """Cache text → screen coordinates from OCR."""
        self.known_positions[text] = (x, y)

    def known_position(self, text: str) -> Optional[tuple[int, int]]:
        """Look up cached coordinates for text."""
        return self.known_positions.get(text)

    def record_action(self, step: ActionStep, result: dict[str, Any]) -> None:
        """Log an executed action and its result."""
        self.action_history.append({
            "action": step.action,
            "params": step.params,
            "reasoning": step.reasoning,
            "success": result.get("success", False),
            "detail": result.get("detail", ""),
        })

    def record_goal_complete(self, goal: str) -> None:
        """Mark a (sub-)goal as completed."""
        self.completed_goals.append(goal)

    def is_goal_complete(self, goal: str) -> bool:
        """Check if a goal was already completed."""
        return goal in self.completed_goals

    def snapshot_for_llm(self) -> str:
        """Format memory state for LLM context."""
        lines = ["Memory (what was already done):"]
        for g in self.completed_goals[-5:]:
            lines.append(f"  ✓ Completed: {g}")
        for w in sorted(self.opened_windows)[-5:]:
            lines.append(f"  Window open: {w}")
        if self.known_positions:
            lines.append(f"  Known positions: {len(self.known_positions)} elements")
        last_actions = self.action_history[-3:]
        for a in last_actions:
            icon = "✓" if a["success"] else "✗"
            lines.append(f"  {icon} {a['action']} → {a.get('detail', '')[:40]}")
        return "\n".join(lines)


# ═══════════════════════════════════════════════════════
# Flow Generalization — parametrize recorded flows
# ═══════════════════════════════════════════════════════

@dataclass
class FlowTemplate:
    """A parametrized flow template — generalize from recorded flows.

    Replaces hardcoded values (text, coordinates, window titles) with
    template variables that get filled at runtime.
    """

    name: str
    description: str = ""
    steps: list[dict[str, Any]] = field(default_factory=list)
    parameters: dict[str, Any] = field(default_factory=dict)

    def apply(self, **kwargs: Any) -> ActionPlan:
        """Fill template variables and produce an executable ActionPlan."""
        plan = ActionPlan(goal=self.description)
        for s in self.steps:
            params = {}
            for k, v in s.get("params", {}).items():
                if isinstance(v, str) and v.startswith("${") and v.endswith("}"):
                    key = v[2:-1]
                    params[k] = kwargs.get(key, v)
                else:
                    params[k] = v
            plan.add(s["action"], params, s.get("reasoning", ""))
        return plan


class FlowGeneralizer:
    """Convert recorded flows into reusable parametrized templates.

    Example:
        recorded flow: click Text("搜索"), type Text("2036")
        generalized template: click Text("${search_target}"), type Text("${input_text}")
    """

    @staticmethod
    def generalize(flow_name: str, recorded_steps: list[dict[str, Any]]) -> FlowTemplate:
        """Extract a parametrized template from recorded steps."""
        template = FlowTemplate(name=flow_name)

        for s in recorded_steps:
            step = {"action": s["action"], "params": {}, "reasoning": s.get("reasoning", "")}

            # Generalize parameters
            for k, v in s.get("params", {}).items():
                if k in ("text", "key") and isinstance(v, str):
                    param_name = f"{k}_{len(template.parameters)}"
                    template.parameters[param_name] = v
                    step["params"][k] = f"${{{param_name}}}"
                elif k in ("x", "y") and isinstance(v, int):
                    # Coordinates from OCR are relative — keep as-is unless target is consistent
                    step["params"][k] = v
                else:
                    step["params"][k] = v

            template.steps.append(step)

        template.description = f"Generalized from {flow_name}"
        return template

    @staticmethod
    def from_recording(name: str, filepath: str) -> FlowTemplate:
        """Load a recorded JSON, generalize it."""
        import json
        with open(filepath) as f:
            data = json.load(f)
        steps = data.get("steps", data)
        return FlowGeneralizer.generalize(name, steps)


# ═══════════════════════════════════════════════════════
# Performance Profiler — per-step timing visibility
# ═══════════════════════════════════════════════════════

@dataclass
class StepProfile:
    """Timing breakdown for a single action step."""

    action: str
    start_ms: float
    capture_ms: float = 0.0   # screenshot time
    ocr_ms: float = 0.0       # OCR text extraction time
    execute_ms: float = 0.0   # actual action execution time
    verify_ms: float = 0.0    # screen change verification time
    total_ms: float = 0.0
    success: bool = True
    retries: int = 0

    @property
    def overhead_pct(self) -> float:
        """Percentage of time spent on capture+ocr+verify vs execute."""
        if self.total_ms == 0:
            return 0.0
        non_exec = self.capture_ms + self.ocr_ms + self.verify_ms
        return non_exec / self.total_ms * 100


class Profiler:
    """Collects per-step timing data for performance analysis."""

    def __init__(self) -> None:
        self.profiles: list[StepProfile] = []
        self._start: float = 0.0

    def start_step(self, action: str) -> StepProfile:
        self._start = time.time()
        return StepProfile(action=action, start_ms=self._start * 1000)

    def record(self, profile: StepProfile) -> None:
        profile.total_ms = time.time() * 1000 - profile.start_ms
        self.profiles.append(profile)

    def summary(self) -> dict[str, Any]:
        """Aggregated profiling summary."""
        if not self.profiles:
            return {"steps": 0}

        total = sum(p.total_ms for p in self.profiles)
        exec_time = sum(p.execute_ms for p in self.profiles)
        capture_time = sum(p.capture_ms for p in self.profiles)
        failed = sum(1 for p in self.profiles if not p.success)

        return {
            "steps": len(self.profiles),
            "total_ms": total,
            "avg_per_step_ms": total / len(self.profiles),
            "exec_time_pct": exec_time / total * 100 if total else 0,
            "capture_overhead_pct": capture_time / total * 100 if total else 0,
            "failed_steps": failed,
            "retries": sum(p.retries for p in self.profiles),
        }

    def report(self) -> str:
        """Human-readable profiling report."""
        s = self.summary()
        if s["steps"] == 0:
            return "No profiling data."

        lines = [
            f"Performance: {s['steps']} steps in {s['total_ms']:.0f}ms ({s['avg_per_step_ms']:.0f}ms/step avg)",
            f"  Execution: {s['exec_time_pct']:.1f}% | Capture overhead: {s['capture_overhead_pct']:.1f}%",
        ]
        if s["retries"]:
            lines.append(f"  Retries: {s['retries']} | Failed: {s['failed_steps']}")

        # Per-step breakdown
        for p in self.profiles[-5:]:
            icon = "✓" if p.success else "✗"
            lines.append(
                f"  {icon} {p.action}: total={p.total_ms:.0f}ms "
                f"(capture={p.capture_ms:.0f} ocr={p.ocr_ms:.0f} "
                f"exec={p.execute_ms:.0f} verify={p.verify_ms:.0f})"
                + (f" r{p.retries}" if p.retries else "")
            )
        return "\n".join(lines)


# ═══════════════════════════════════════════════════════
# Profiling Agent — wraps Agent with timing visibility
# ═══════════════════════════════════════════════════════

class ProfilingAgent:
    """Agent wrapper that profiles every step."""

    def __init__(self, agent: Any) -> None:
        self.agent = agent
        self.profiler = Profiler()

    def run(self, goal: str) -> dict[str, Any]:
        """Run a goal with profiling."""
        plan = self.agent.plan(goal)

        from .core import AgentExecutor
        results: list[dict[str, Any]] = []

        for step in plan.steps:
            profile = self.profiler.start_step(step.action)

            # Capture before
            t0 = time.time()
            before = ScreenContext.capture()
            profile.capture_ms = (time.time() - t0) * 1000

            # OCR if text available
            if before.ocr_text:
                profile.ocr_ms = 0.5  # approximate; real OCR time varies

            # Execute
            t1 = time.time()
            result = AgentExecutor.execute_step(step)
            profile.execute_ms = (time.time() - t1) * 1000
            profile.success = result.get("success", False)

            # Retry if needed
            retries = 0
            while not profile.success and retries < self.agent.max_retries:
                retries += 1
                time.sleep(0.5)
                t1 = time.time()
                result = AgentExecutor.execute_step(step)
                profile.execute_ms += (time.time() - t1) * 1000
                profile.success = result.get("success", False)
            profile.retries = retries

            # Verify
            t2 = time.time()
            after = ScreenContext.capture()
            profile.verify_ms = (time.time() - t2) * 1000

            self.profiler.record(profile)
            results.append(result)

            if not profile.success:
                break

        return {
            "success": all(r.get("success", False) for r in results),
            "steps": results,
            "plan": plan,
            "profile": self.profiler.summary(),
            "report": self.profiler.report(),
        }

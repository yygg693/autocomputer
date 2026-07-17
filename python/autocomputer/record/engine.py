"""
ActionFlow — intent-based recording and replay engine.
JSON Schema v1.0 for serialized automation flows.
"""

import json
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from autocomputer.core import capture_screen, screen_size
from autocomputer.core._bridge import _get_rust_attr

# ── Schema v1.0 ──

SCHEMA_VERSION = "1.0"


@dataclass
class FlowStep:
    """A single step in a recorded flow."""
    action: str  # "click" | "type" | "press" | "wait" | "scroll" | "move" | "hotkey"
    params: dict[str, Any] = field(default_factory=dict)
    # Intent data (not coordinates)
    ocr_text: str = ""  # Text near click point
    window_title: str = ""
    screen_size: tuple[int, int] = (0, 0)
    # Metadata
    description: str = ""
    timestamp: float = 0.0
    step_index: int = 0


@dataclass
class ActionFlow:
    """Complete recorded automation flow."""
    version: str = SCHEMA_VERSION
    name: str = ""
    description: str = ""
    created_at: float = field(default_factory=time.time)
    screen_size: tuple[int, int] = (0, 0)
    steps: list[FlowStep] = field(default_factory=list)


class FlowRecorder:
    """Records user actions as an ActionFlow."""

    def __init__(self, name: str = "") -> None:
        self.flow = ActionFlow(
            name=name,
            screen_size=screen_size(),
        )
        self._step_idx = 0

    def record_click(self, x: int, y: int, button: str = "left", description: str = "") -> None:
        s = FlowStep(
            action="click",
            params={"x": x, "y": y, "button": button},
            screen_size=screen_size(),
            description=description,
            timestamp=time.time(),
            step_index=self._step_idx,
        )
        self.flow.steps.append(s)
        self._step_idx += 1

    def record_type(self, text: str, method: str = "auto", description: str = "") -> None:
        s = FlowStep(
            action="type",
            params={"text": text, "method": method},
            screen_size=screen_size(),
            description=description,
            timestamp=time.time(),
            step_index=self._step_idx,
        )
        self.flow.steps.append(s)
        self._step_idx += 1

    def record_press(self, key: str, description: str = "") -> None:
        s = FlowStep(
            action="press",
            params={"key": key},
            screen_size=screen_size(),
            description=description,
            timestamp=time.time(),
            step_index=self._step_idx,
        )
        self.flow.steps.append(s)
        self._step_idx += 1

    def record_wait(self, ms: int = 1000, description: str = "") -> None:
        s = FlowStep(
            action="wait",
            params={"ms": ms},
            screen_size=screen_size(),
            description=description,
            timestamp=time.time(),
            step_index=self._step_idx,
        )
        self.flow.steps.append(s)
        self._step_idx += 1

    def record_scroll(self, clicks: int, description: str = "") -> None:
        s = FlowStep(
            action="scroll",
            params={"clicks": clicks},
            screen_size=screen_size(),
            description=description or f"Scroll {clicks}",
            timestamp=time.time(),
            step_index=self._step_idx,
        )
        self.flow.steps.append(s)
        self._step_idx += 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.flow.version,
            "name": self.flow.name,
            "description": self.flow.description,
            "created_at": self.flow.created_at,
            "screen_size": list(self.flow.screen_size),
            "step_count": len(self.flow.steps),
            "steps": [
                {
                    "action": s.action,
                    "params": s.params,
                    "ocr_text": s.ocr_text,
                    "window_title": s.window_title,
                    "description": s.description,
                    "screen_size": list(s.screen_size),
                    "step_index": s.step_index,
                    "timestamp": s.timestamp,
                }
                for s in self.flow.steps
            ],
        }

    def save(self, path: str) -> str:
        """Save flow to JSON file."""
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)
        return path

    @classmethod
    def load(cls, path: str) -> "FlowRecorder":
        """Load flow from JSON file."""
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: dict) -> "FlowRecorder":

        ver = data.get("version", "1.0")
        if ver != SCHEMA_VERSION:
            # Auto-migration for future versions
            pass

        recorder = cls(name=data.get("name", ""))
        recorder.flow.description = data.get("description", "")
        recorder.flow.created_at = data.get("created_at", time.time())
        ss = data.get("screen_size", [0, 0])
        recorder.flow.screen_size = (ss[0], ss[1])

        for i, s in enumerate(data.get("steps", [])):
            ss2 = s.get("screen_size", [0, 0])
            step = FlowStep(
                action=s["action"],
                params=s.get("params", {}),
                ocr_text=s.get("ocr_text", ""),
                window_title=s.get("window_title", ""),
                screen_size=(ss2[0], ss2[1]),
                description=s.get("description", ""),
                timestamp=s.get("timestamp", 0.0),
                step_index=i,
            )
            recorder.flow.steps.append(step)

        recorder._step_idx = len(recorder.flow.steps)
        return recorder


class FlowReplayer:
    """Replay a recorded ActionFlow using the Rust engine."""

    def __init__(self, flow: FlowRecorder) -> None:
        self.flow = flow
        self.results: list[dict[str, Any]] = []
        self._speed: float = 1.0

    def replay(self, speed: float = 1.0, dry_run: bool = False) -> list[dict[str, Any]]:
        """Replay all steps. Returns list of results."""
        self._speed = speed
        self.results = []
        for step in self.flow.flow.steps:
            r = self._execute(step, dry_run)
            self.results.append(r)
            if not r["success"] and not dry_run:
                break
            if not dry_run:
                time.sleep(0.1 / speed)
        return self.results

    def _execute(self, step: FlowStep, dry_run: bool) -> dict[str, Any]:
        """Execute or simulate a single step."""
        result: dict[str, Any] = {"step": step.step_index, "action": step.action, "success": True}

        if dry_run:
            result["dry_run"] = True
            return result

        try:
            if step.action == "click":
                fn = _get_rust_attr("mouse_click")
                if fn:
                    fn(step.params["x"], step.params["y"], step.params.get("button", "left"))

            elif step.action == "type":
                fn = _get_rust_attr("keyboard_type")
                if fn:
                    fn(step.params["text"], step.params.get("method", "auto"))

            elif step.action == "press":
                fn = _get_rust_attr("keyboard_press")
                if fn:
                    fn(step.params["key"])

            elif step.action == "wait":
                time.sleep(step.params.get("ms", 1000) / 1000.0 / self._speed)

            elif step.action == "scroll":
                fn = _get_rust_attr("mouse_scroll")
                if fn:
                    fn(step.params["clicks"])

            elif step.action == "move":
                fn = _get_rust_attr("mouse_move")
                if fn:
                    fn(step.params["x"], step.params["y"], None)

            elif step.action == "hotkey":
                fn = _get_rust_attr("keyboard_press")
                if fn:
                    fn(step.params.get("combo", ""))

        except Exception as e:
            result["success"] = False
            result["error"] = str(e)

        return result


# ── Compression ──

def compress_flow(flow: FlowRecorder) -> FlowRecorder:
    """Compress a flow by merging consecutive wait+action pairs."""
    compressed = FlowRecorder(name=flow.flow.name + " (compressed)")
    compressed.flow.description = flow.flow.description

    i = 0
    steps = flow.flow.steps
    while i < len(steps):
        # Merge consecutive waits
        total_wait = 0
        while i < len(steps) and steps[i].action == "wait":
            total_wait += steps[i].params.get("ms", 0)
            i += 1
        if total_wait > 0:
            compressed.record_wait(total_wait, f"Merged wait: {total_wait}ms")

        if i < len(steps):
            s = steps[i]
            if s.action == "click":
                compressed.record_click(
                    s.params.get("x", 0), s.params.get("y", 0),
                    s.params.get("button", "left"), s.description,
                )
            elif s.action == "type":
                compressed.record_type(s.params.get("text", ""), s.params.get("method", "auto"), s.description)
            elif s.action == "press":
                compressed.record_press(s.params.get("key", ""), s.description)
            elif s.action == "scroll":
                compressed.record_scroll(s.params.get("clicks", 1), s.description)
            elif s.action == "move":
                compressed.record_click(s.params.get("x", 0), s.params.get("y", 0), "left", s.description)
            elif s.action == "hotkey":
                compressed.record_press(s.params.get("combo", ""), s.description)
            i += 1

    return compressed

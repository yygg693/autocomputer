"""Tests for Python SDK modules."""

import json
import tempfile
from pathlib import Path

import pytest

from autocomputer.core._bridge import _RUST_AVAILABLE

# Tests that need real screenshots/input only make sense with the Rust core
# (_core.pyd) built; skip them in pure-Python fallback mode.
needs_rust = pytest.mark.skipif(
    not _RUST_AVAILABLE, reason="requires Rust core (autocomputer.core._core)"
)


class TestCommandRegistry:
    def test_register_and_dispatch(self) -> None:
        from autocomputer.cli.commands import Command, CommandRegistry

        reg = CommandRegistry()
        reg.register(Command(name="test", handler=lambda x: x * 2, category="test"))
        assert "test" in reg
        assert reg.dispatch("test", 5) == 10

    def test_aliases(self) -> None:
        from autocomputer.cli.commands import Command, CommandRegistry

        reg = CommandRegistry()
        reg.register(Command(name="capture", handler=lambda: "ok", aliases=["cap", "screenshot", "截图"]))
        assert reg.dispatch("cap") == "ok"
        assert reg.dispatch("截图") == "ok"
        assert reg.dispatch("capture") == "ok"

    def test_unknown_command(self) -> None:
        from autocomputer.cli.commands import CommandRegistry

        reg = CommandRegistry()
        try:
            reg.dispatch("nonexistent")
            assert False, "Should have raised"
        except ValueError:
            pass

    def test_list_by_category(self) -> None:
        from autocomputer.cli.commands import Command, CommandRegistry

        reg = CommandRegistry()
        reg.register(Command(name="a", handler=lambda: 1, category="cat1"))
        reg.register(Command(name="b", handler=lambda: 2, category="cat2"))
        reg.register(Command(name="c", handler=lambda: 3, category="cat1"))

        cats = reg.list_by_category()
        assert len(cats["cat1"]) == 2
        assert len(cats["cat2"]) == 1


class TestScreenContext:
    @needs_rust
    def test_capture(self) -> None:
        from autocomputer.agent.core import ScreenContext

        ctx = ScreenContext.capture()
        assert ctx.resolution[0] > 0
        assert ctx.resolution[1] > 0
        assert ctx.monitor_count >= 1
        assert ctx.screenshot_png_b64 != ""

    def test_to_prompt(self) -> None:
        from autocomputer.agent.core import ScreenContext

        ctx = ScreenContext(resolution=(1920, 1080), monitor_count=2)
        prompt = ctx.to_prompt()
        assert "1920x1080" in prompt
        assert "2" in prompt


class TestFlowRecorder:
    def test_record_and_save(self) -> None:
        from autocomputer.record.engine import FlowRecorder

        rec = FlowRecorder(name="test_flow")
        rec.record_click(100, 200, "left", "click login")
        rec.record_type("hello", "auto", "type message")
        rec.record_press("enter")
        rec.record_wait(500)

        data = rec.to_dict()
        assert data["version"] == "1.0"
        assert data["name"] == "test_flow"
        assert data["step_count"] == 4
        assert data["steps"][0]["action"] == "click"
        assert data["steps"][1]["action"] == "type"

    def test_save_and_load(self) -> None:
        from autocomputer.record.engine import FlowRecorder

        rec = FlowRecorder(name="save_test")
        rec.record_click(50, 50)
        rec.record_type("test")

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
            rec.save(f.name)
            loaded = FlowRecorder.load(f.name)

        assert loaded.flow.name == "save_test"
        assert len(loaded.flow.steps) == 2
        Path(f.name).unlink()

    def test_compress_flow(self) -> None:
        from autocomputer.record.engine import FlowRecorder, compress_flow

        rec = FlowRecorder(name="to_compress")
        rec.record_wait(100)
        rec.record_wait(200)
        rec.record_click(10, 10)
        rec.record_wait(50)
        rec.record_type("abc")

        compressed = compress_flow(rec)
        # Two consecutive waits merged, total 300ms
        steps = compressed.flow.steps
        assert steps[0].action == "wait"
        assert steps[0].params["ms"] == 300


class TestAgent:
    def test_action_plan(self) -> None:
        from autocomputer.agent.core import ActionPlan

        plan = ActionPlan(goal="test")
        plan.add("click", {"x": 100, "y": 200})
        plan.add("type", {"text": "hello"})
        assert len(plan.steps) == 2
        assert plan.steps[0].action == "click"

    @needs_rust
    def test_state_tracker(self) -> None:
        from autocomputer.agent.core import StateTracker

        state = StateTracker.before_action()
        assert state.before is not None
        assert state.changed is False

        state = StateTracker.after_action(state)
        assert state.after is not None
        # changed could be True or False depending on screen

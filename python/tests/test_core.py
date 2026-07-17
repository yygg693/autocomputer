"""Tests for autocomputer core module."""

import pytest


def test_version() -> None:
    from autocomputer import __version__

    assert __version__.endswith("-dev")
    parts = __version__.split(".")
    assert len(parts) >= 3


def test_import_core() -> None:
    from autocomputer.core._bridge import _RUST_AVAILABLE

    assert _RUST_AVAILABLE in (True, False)


def test_import_cli() -> None:
    from autocomputer.cli import app

    assert app is not None


def test_capture_result_stub() -> None:
    """Ensure CaptureResult is importable."""
    from autocomputer.core import CaptureResult

    r = CaptureResult()
    assert r.width == 0
    assert r.height == 0


def test_monitor_info_stub() -> None:
    """Ensure MonitorInfo is importable."""
    from autocomputer.core import MonitorInfo

    m = MonitorInfo()
    assert m.name == ""


def test_screen_size() -> None:
    """screen_size() should return a tuple of two ints."""
    from autocomputer.core import screen_size

    w, h = screen_size()
    assert isinstance(w, int)
    assert isinstance(h, int)


def test_list_monitors() -> None:
    """list_monitors() should return a list."""
    from autocomputer.core import list_monitors

    monitors = list_monitors()
    assert isinstance(monitors, list)


def test_capture_screen() -> None:
    """capture_screen() should return a CaptureResult."""
    from autocomputer.core import capture_screen, CaptureResult

    result = capture_screen(0)
    assert isinstance(result, CaptureResult)
    if result.width > 0:
        assert len(result.raw) == result.width * result.height * 4
        assert len(result.png) > 0


def test_all_subpackages_importable() -> None:
    """Verify all subpackages can be imported."""
    import autocomputer.agent
    import autocomputer.perception
    import autocomputer.record
    import autocomputer.llm
    import autocomputer.plugins
    import autocomputer.utils

"""Tests for the API server (fallback mode — no Rust core required)."""

import json
import pytest

from autocomputer import server


def _handler():
    """Instance methods on APIHandler don't touch network state — call with a dummy self."""
    return server.APIHandler


def test_status_reports_real_test_counts():
    """tests_passed must be a dynamic count of actual Rust + Python tests, not a hardcoded number."""
    status = _handler()._status(object())
    expected = server.count_tests()
    assert isinstance(status.get("tests_passed"), int)
    assert status["tests_passed"] == expected
    assert expected >= 29  # Rust #[test] floor


def test_flows_roundtrip_save_load_delete(monkeypatch, tmp_path):
    monkeypatch.setattr(server, "flows_path", lambda: tmp_path / "flows.json")
    h = _handler()

    # Empty initially
    assert h._flows(object()) == {"flows": [], "count": 0}

    # Save
    saved = server.APIHandler._save_flow(object(), {"name": "登录流程", "steps": [{"action": "click", "params": {"x": 1, "y": 2}}]})
    assert saved["ok"] is True
    got = h._flows(object())
    assert got["count"] == 1
    assert got["flows"][0]["name"] == "登录流程"
    assert got["flows"][0]["step_count"] == 1
    assert "created" in got["flows"][0]

    # Overwrite same name keeps single entry
    server.APIHandler._save_flow(object(), {"name": "登录流程", "steps": []})
    assert h._flows(object())["count"] == 1

    # Delete
    server.APIHandler._delete_flow(object(), "登录流程")
    assert h._flows(object()) == {"flows": [], "count": 0}


def test_execute_appends_to_log_queue():
    server._LOG_QUEUE.clear()
    h = _handler()
    server.APIHandler._execute(object(), {"action": "click", "params": {"x": 0, "y": 0}})
    assert len(server._LOG_QUEUE) == 1
    entry = server._LOG_QUEUE[0]
    assert entry["action"] == "click"
    assert entry["ok"] is True

    server.APIHandler._execute(object(), {"action": "nonexistent"})
    assert server._LOG_QUEUE[-1]["ok"] is False


def test_logs_endpoint_shape():
    logs = _handler()._logs(object())
    assert set(logs.keys()) == {"logs"}


def test_security_endpoint_shape():
    sec = _handler()._security(object())
    assert "audit" in sec and "hotkeys" in sec and "thresholds" in sec
    assert sec["audit"]["total"] >= 0
    assert isinstance(sec["audit"]["by_action"], dict)
    assert len(sec["hotkeys"]) == 4
    assert sec["thresholds"]["max_clicks_same_position"] == 5

"""
Plugin system — extensible actions and perception backends.

Plugins are discovered via Python entry_points (group="autocomputer.plugins")
or by registering classes directly.

Each plugin can provide:
- Actions: additional executor actions (e.g., "screenshot", "ocr_click")
- Perception backends: custom OCR/vision implementations
- Hooks: lifecycle callbacks (on_start, on_step_complete, on_finish)
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable

import importlib.metadata
import sys


# ── Plugin interface ──

@dataclass
class PluginAction:
    """An action that a plugin can execute."""
    name: str
    execute: Callable[..., Any]
    description: str = ""


class AutoComputerPlugin(ABC):
    """Base class for autocomputer plugins."""

    name: str = ""
    version: str = "0.1"

    def on_load(self) -> None:
        """Called when the plugin is first loaded."""
        pass

    def get_actions(self) -> list[PluginAction]:
        """Return actions this plugin provides."""
        return []

    def get_hooks(self) -> dict[str, Callable[..., Any]]:
        """Return lifecycle hooks {hook_name: callback}."""
        return {}


# ── Registry ──

class PluginRegistry:
    """Central plugin registry. Plugins register actions and hooks here."""

    _plugins: dict[str, AutoComputerPlugin] = {}
    _actions: dict[str, PluginAction] = {}
    _hooks: dict[str, list[Callable[..., Any]]] = {}

    _discovered: bool = False

    @classmethod
    def _ensure_discovered(cls) -> None:
        if not cls._discovered:
            cls.discover()
            cls._discovered = True

    @classmethod
    def discover(cls) -> list[str]:
        """Discover plugins via entry_points and built-in registry."""
        names: list[str] = []

        # Discover via Python entry_points
        try:
            eps = importlib.metadata.entry_points(group="autocomputer.plugins")
            for ep in eps:
                try:
                    plugin_cls = ep.load()
                    plugin = plugin_cls()
                    cls.register(plugin)
                    names.append(plugin.name or ep.name)
                except Exception as e:
                    print(f"[autocomputer] Failed to load plugin {ep.name}: {e}", file=sys.stderr)
        except Exception:
            pass  # entry_points not available or empty

        return names

    @classmethod
    def register(cls, plugin: AutoComputerPlugin) -> None:
        """Register a plugin and its actions/hooks."""
        name = plugin.name or plugin.__class__.__name__
        cls._plugins[name] = plugin
        plugin.on_load()

        for action in plugin.get_actions():
            cls._actions[action.name] = action

        for hook_name, callback in plugin.get_hooks().items():
            cls._hooks.setdefault(hook_name, []).append(callback)

    @classmethod
    def get_action(cls, name: str) -> PluginAction | None:
        """Look up a registered action."""
        cls._ensure_discovered()
        return cls._actions.get(name)

    @classmethod
    def list_actions(cls) -> list[str]:
        """List all registered action names."""
        cls._ensure_discovered()
        return list(cls._actions.keys())

    @classmethod
    def fire_hook(cls, hook_name: str, **kwargs: Any) -> None:
        """Fire a lifecycle hook."""
        for cb in cls._hooks.get(hook_name, []):
            try:
                cb(**kwargs)
            except Exception as e:
                print(f"[autocomputer] Hook {hook_name} error: {e}", file=sys.stderr)

"""
Plugin-based command registry — replaces if-elif dispatch chains.

Usage:
    registry = CommandRegistry()
    registry.register(Command(name="see", handler=lambda: ..., category="capture"))
    registry.dispatch("see", {})
"""

from dataclasses import dataclass, field
from typing import Any, Callable, Optional


@dataclass
class Command:
    """A registered command with metadata."""
    name: str
    handler: Callable[..., Any]
    category: str = "general"
    aliases: list[str] = field(default_factory=list)
    description: str = ""
    help_text: str = ""


class CommandRegistry:
    """Plugin-based command registration and dispatch."""

    def __init__(self) -> None:
        self._commands: dict[str, Command] = {}
        self._aliases: dict[str, str] = {}

    def register(self, cmd: Command) -> None:
        """Register a command."""
        self._commands[cmd.name] = cmd
        for alias in cmd.aliases:
            self._aliases[alias] = cmd.name

    def unregister(self, name: str) -> None:
        """Remove a command."""
        cmd = self._commands.pop(name, None)
        if cmd:
            for alias in cmd.aliases:
                self._aliases.pop(alias, None)

    def get(self, name: str) -> Optional[Command]:
        """Look up a command by name or alias."""
        real_name = self._aliases.get(name, name)
        return self._commands.get(real_name)

    def dispatch(self, name: str, *args: Any, **kwargs: Any) -> Any:
        """Find and execute a command."""
        cmd = self.get(name)
        if cmd is None:
            available = ", ".join(sorted(self._commands.keys()))
            raise ValueError(f"Unknown command: '{name}'. Available: {available}")
        return cmd.handler(*args, **kwargs)

    def list_by_category(self) -> dict[str, list[Command]]:
        """Group commands by category."""
        cats: dict[str, list[Command]] = {}
        for cmd in sorted(self._commands.values(), key=lambda c: c.name):
            cats.setdefault(cmd.category, []).append(cmd)
        return cats

    def list_all(self) -> list[Command]:
        """All registered commands, sorted by name."""
        return sorted(self._commands.values(), key=lambda c: c.name)

    def __len__(self) -> int:
        return len(self._commands)

    def __contains__(self, name: str) -> bool:
        return self.get(name) is not None


# ── Global instance ──
_registry: Optional[CommandRegistry] = None


def get_registry() -> CommandRegistry:
    """Get or create the global command registry."""
    global _registry
    if _registry is None:
        _registry = CommandRegistry()
    return _registry


def reset_registry() -> None:
    """Reset the global registry (for testing)."""
    global _registry
    _registry = None

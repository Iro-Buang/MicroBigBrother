# World/results.py
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, Tuple

from World.events import Event

@dataclass(frozen=True)
class ToolResult:
    ok: bool
    message: str
    events: Tuple[Event, ...] = field(default_factory=tuple)
    data: Dict[str, Any] = field(default_factory=dict)
    # Whether invoking this tool should automatically advance the global turn.
    # Default True to preserve the "one action per turn" feel.
    consume_turn: bool = True

    @staticmethod
    def success(message: str, *, events: Tuple[Event, ...] = (), data: Dict[str, Any] | None = None) -> "ToolResult":
        return ToolResult(True, message, tuple(events), dict(data or {}), True)

    @staticmethod
    def fail(message: str, *, events: Tuple[Event, ...] = (), data: Dict[str, Any] | None = None) -> "ToolResult":
        return ToolResult(False, message, tuple(events), dict(data or {}), True)

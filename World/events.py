# World/events.py
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, Tuple
import uuid

@dataclass(frozen=True)
class Event:
    id: str
    turn: int
    actor: str
    type: str
    args: Dict[str, Any] = field(default_factory=dict)
    ok: bool = True
    message: str = ""

def new_event(*, turn: int, actor: str, type: str, args: Dict[str, Any] | None = None, ok: bool = True, message: str = "") -> Event:
    return Event(
        id=str(uuid.uuid4()),
        turn=turn,
        actor=actor,
        type=type,
        args=dict(args or {}),
        ok=ok,
        message=message,
    )

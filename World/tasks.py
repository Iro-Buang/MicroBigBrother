# World/tasks.py
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, Literal, Tuple

TaskStatus = Literal["queued", "active", "done", "cancelled", "failed"]

@dataclass(frozen=True)
class TaskDef:
    name: str
    args_schema: Dict[str, str] = field(default_factory=dict)
    description: str = ""
    # later: duration rules, preconditions, etc.

@dataclass(frozen=True)
class TaskInstance:
    id: str
    name: str
    actor: str
    args: Dict[str, Any] = field(default_factory=dict)
    status: TaskStatus = "queued"
    created_turn: int = 0
    started_turn: int | None = None
    completed_turn: int | None = None
    progress: Dict[str, Any] = field(default_factory=dict)

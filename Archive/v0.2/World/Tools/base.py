from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, Protocol, Tuple

from World.house import House
from World.state import WorldState
from World.engine import Result  # reuse your Result dataclass
from World.Tools.spec import ToolSpec

@dataclass(frozen=True)
class ActionContext:
    house: House
    state: WorldState
    actor: str

class Tool(Protocol):
    name: str
    spec: ToolSpec

    def can_run(self, ctx: ActionContext, args: Dict[str, Any]) -> Tuple[bool, str]:
        ...

    def run(self, ctx: ActionContext, args: Dict[str, Any]) -> Tuple[WorldState, Result]:
        ...

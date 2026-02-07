from __future__ import annotations
from typing import Any, Dict, Tuple

from World.engine import Result, end_turn
from World.tools.base import ActionContext

class EndTurnTool:
    name = "end_turn"

    def can_run(self, ctx: ActionContext, args: Dict[str, Any]) -> Tuple[bool, str]:
        return True, "OK"

    def run(self, ctx: ActionContext, args: Dict[str, Any]):
        return end_turn(ctx.state)

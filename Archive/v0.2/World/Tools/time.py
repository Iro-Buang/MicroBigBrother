from __future__ import annotations
from typing import Any, Dict, Tuple

from World.engine import end_turn
from World.Tools.base import ActionContext
from World.Tools.spec import ToolSpec

class EndTurnTool:
    name = "end_turn"

    spec = ToolSpec(
        name="end_turn",
        description="End your action for this round (advance to the next actor).",
        args_schema={},
        visible=lambda ctx: True,
    )

    def can_run(self, ctx: ActionContext, args: Dict[str, Any]) -> Tuple[bool, str]:
        return True, "OK"

    def run(self, ctx: ActionContext, args: Dict[str, Any]):
        return end_turn(ctx.state)

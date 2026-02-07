from __future__ import annotations
from typing import Any, Dict, Tuple

from World.engine import Result, apply_move
from World.tools.base import ActionContext

class MoveToTool:
    name = "move_to"

    def can_run(self, ctx: ActionContext, args: Dict[str, Any]) -> Tuple[bool, str]:
        if "dst" not in args:
            return False, "move_to requires args: {dst}"
        if not isinstance(args["dst"], str):
            return False, "move_to.dst must be a string"
        return True, "OK"

    def run(self, ctx: ActionContext, args: Dict[str, Any]):
        dst = args["dst"]
        return apply_move(ctx.house, ctx.state, ctx.actor, dst)

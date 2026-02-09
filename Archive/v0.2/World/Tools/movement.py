from __future__ import annotations
from typing import Any, Dict, Tuple

from World.engine import apply_move, can_enter_room
from World.Tools.base import ActionContext
from World.Tools.spec import ToolSpec

class MoveToTool:
    name = "move_to"

    @staticmethod
    def _choices(ctx: ActionContext) -> Dict[str, list[str]]:
        src = ctx.state.locations.get(ctx.actor)
        if not src:
            return {"dst": []}

        # adjacent rooms from current location
        neighbors = sorted(ctx.house.edges.get(src, set()))

        # filter out locked destinations (since your lock semantics block entry)
        allowed = [r for r in neighbors if can_enter_room(ctx.state, ctx.actor, r)]
        return {"dst": allowed}

    spec = ToolSpec(
        name="move_to",
        description="Move to an adjacent room if it is accessible.",
        args_schema={
            "dst": "Destination room id (must be adjacent and unlocked)."
        },
        visible=lambda ctx: True,
        choices=_choices.__func__,  # staticmethod -> function
    )

    def can_run(self, ctx: ActionContext, args: Dict[str, Any]) -> Tuple[bool, str]:
        if "dst" not in args:
            return False, "move_to requires args: {dst}"
        if not isinstance(args["dst"], str):
            return False, "move_to.dst must be a string"
        return True, "OK"

    def run(self, ctx: ActionContext, args: Dict[str, Any]):
        return apply_move(ctx.house, ctx.state, ctx.actor, args["dst"])

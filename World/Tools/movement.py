from __future__ import annotations
from typing import Any, Dict, Tuple

from World.engine import apply_move, can_enter_room
from World.Tools.base import ActionContext
from World.Tools.spec import ToolSpec
from World.interactions import active_talk_id

class MoveToTool:
    name = "move_to"

    @staticmethod
    def _choices(ctx: ActionContext) -> Dict[str, list[str]]:
        src = ctx.state.locations.get(ctx.actor)
        if not src:
            return {"dst": []}

        # adjacent rooms from current location
        neighbors = sorted(ctx.house.edges.get(src, set()))

        # living room hub rule: if you're not in the living room, you can only move to the living room
        if src != "living_room":
            neighbors = ["living_room"] if "living_room" in ctx.house.edges.get(src, set()) else []

        # filter out locked destinations (since your lock semantics block entry)
        allowed = [r for r in neighbors if can_enter_room(ctx.state, ctx.actor, r)]
        return {"dst": allowed}

    spec = ToolSpec(
        name="move_to",
        description="Move to an adjacent room if it is accessible.",
        args_schema={
            "dst": "Destination room id (must be adjacent and unlocked)."
        },
        visible=lambda ctx: active_talk_id(ctx.state, ctx.actor) is None,
        choices=_choices.__func__,  # staticmethod -> function
    )

    def can_run(self, ctx: ActionContext, args: Dict[str, Any]) -> Tuple[bool, str]:
        if "dst" not in args:
            return False, "move_to requires args: {dst}"
        if not isinstance(args["dst"], str):
            return False, "move_to.dst must be a string"
        return True, "OK"

    def run(self, ctx: ActionContext, args: Dict[str, Any]):
        src = ctx.state.locations.get(ctx.actor)
        dst = args["dst"]
        if src and src != "living_room" and dst != "living_room":
            from World.results import ToolResult
            return ctx.state, ToolResult(False, "Denied: from non-living rooms you must move to living_room first.")
        return apply_move(ctx.house, ctx.state, ctx.actor, args["dst"])

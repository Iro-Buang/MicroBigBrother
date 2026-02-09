from __future__ import annotations
from typing import Any, Dict, Tuple

from World.engine import lock_room, unlock_room, Result
from World.Tools.base import ActionContext
from World.Tools.spec import ToolSpec
from World.engine import room_owner
from World.Tools.tool_validators import room_exists, actor_exists, owns_room, in_or_adjacent

def _toggleable_rooms(ctx: ActionContext, *, want_locked: bool) -> list[str]:
    """
    Returns rooms the actor can lock/unlock right now.
    want_locked=True  -> rooms that are currently locked (for unlock)
    want_locked=False -> rooms that are currently unlocked (for lock)
    """
    actor = ctx.actor
    state = ctx.state
    house = ctx.house

    actor_loc = state.locations.get(actor)
    if not actor_loc:
        return []

    result = []

    for room_id in state.room_locked.keys():
        # must own the room
        if room_owner(room_id) != actor:
            continue

        # must be inside or adjacent
        if actor_loc != room_id and room_id not in house.edges.get(actor_loc, set()):
            continue

        # must match desired state
        if state.room_locked.get(room_id) != want_locked:
            continue

        result.append(room_id)

    return sorted(result)


class LockRoomTool:
    name = "lock"

    @staticmethod
    def _choices(ctx: ActionContext) -> Dict[str, list[str]]:
        rooms = _toggleable_rooms(ctx, want_locked=False)
        return {"room_id": rooms}

    spec = ToolSpec(
        name="lock",
        description="Lock a room you own, preventing others from entering.",
        args_schema={
            "room_id": "Room you own that is currently unlocked."
        },
        visible=lambda ctx: len(_toggleable_rooms(ctx, want_locked=False)) > 0,
        choices=_choices.__func__,
    )

    def can_run(self, ctx: ActionContext, args: Dict[str, Any]) -> Tuple[bool, str]:
        if "room_id" not in args:
            return False, "lock requires args: {room_id}"
        if not isinstance(args["room_id"], str):
            return False, "lock.room_id must be a string"
        return True, "OK"

    def run(self, ctx: ActionContext, args: Dict[str, Any]):
        room_id = args["room_id"]

        for gate in (
            (room_exists, (ctx.house, room_id)),
            (actor_exists, (ctx.state, ctx.actor)),
            (owns_room, (ctx.state, ctx.actor, room_id)),
            (in_or_adjacent, (ctx.house, ctx.state, ctx.actor, room_id)),
        ):
            fn, params = gate
            ok, msg = fn(*params)
            if not ok:
                return ctx.state, Result(False, msg)

        return lock_room(ctx.house, ctx.state, ctx.actor, room_id)

class UnlockRoomTool:
    name = "unlock"

    @staticmethod
    def _choices(ctx: ActionContext) -> Dict[str, list[str]]:
        rooms = _toggleable_rooms(ctx, want_locked=True)
        return {"room_id": rooms}

    spec = ToolSpec(
        name="unlock",
        description="Unlock a room you own, allowing others to enter.",
        args_schema={
            "room_id": "Room you own that is currently locked."
        },
        visible=lambda ctx: len(_toggleable_rooms(ctx, want_locked=True)) > 0,
        choices=_choices.__func__,
    )

    def can_run(self, ctx: ActionContext, args: Dict[str, Any]) -> Tuple[bool, str]:
        if "room_id" not in args:
            return False, "unlock requires args: {room_id}"
        if not isinstance(args["room_id"], str):
            return False, "unlock.room_id must be a string"
        return True, "OK"

    def run(self, ctx: ActionContext, args: Dict[str, Any]):
        room_id = args["room_id"]

        for gate in (
            (room_exists, (ctx.house, room_id)),
            (actor_exists, (ctx.state, ctx.actor)),
            (owns_room, (ctx.state, ctx.actor, room_id)),
            (in_or_adjacent, (ctx.house, ctx.state, ctx.actor, room_id)),
        ):
            fn, params = gate
            ok, msg = fn(*params)
            if not ok:
                return ctx.state, Result(False, msg)

        return unlock_room(ctx.house, ctx.state, ctx.actor, room_id)
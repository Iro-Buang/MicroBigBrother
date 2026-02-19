from __future__ import annotations
from typing import Any, Dict, Tuple

from World.engine import lock_room, unlock_room
from World.results import ToolResult
from World.Tools.base import ActionContext
from World.Tools.spec import ToolSpec
from World.interactions import active_talk_id
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
        if room_owner(state, room_id) != actor:
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
        visible=lambda ctx: (active_talk_id(ctx.state, ctx.actor) is None) and (len(_toggleable_rooms(ctx, want_locked=False)) > 0),
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
                return ctx.state, ToolResult(False, msg)

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
        visible=lambda ctx: (active_talk_id(ctx.state, ctx.actor) is None) and (len(_toggleable_rooms(ctx, want_locked=True)) > 0),
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
                return ctx.state, ToolResult(False, msg)

        return unlock_room(ctx.house, ctx.state, ctx.actor, room_id)


class AnnaUnlockRoomTool:
    """Anna-only unlock that can unlock any locked room, but only from the living room."""
    name = "unlock_room"

    @staticmethod
    def _choices(ctx: ActionContext) -> Dict[str, list[str]]:
        if ctx.actor != "anna":
            return {"room_id": []}
        if ctx.state.locations.get(ctx.actor) != "living_room":
            return {"room_id": []}
        locked = [rid for rid, is_locked in (ctx.state.room_locked or {}).items() if is_locked]
        # Don't include living room even if it's ever added later
        locked = [r for r in locked if r != "living_room"]
        return {"room_id": sorted(locked)}

    spec = ToolSpec(
        name="unlock_room",
        description="(Anna) Unlock a locked room from the living room.",
        args_schema={"room_id": "Locked room to unlock."},
        visible=lambda ctx: (ctx.actor == "anna") and (ctx.state.locations.get(ctx.actor) == "living_room") and any((ctx.state.room_locked or {}).values()),
        choices=_choices.__func__,
    )

    def can_run(self, ctx: ActionContext, args: Dict[str, Any]) -> Tuple[bool, str]:
        if ctx.actor != "anna":
            return False, "Denied: only Anna can use unlock_room."
        if ctx.state.locations.get(ctx.actor) != "living_room":
            return False, "Denied: Anna can only unlock rooms from the living_room."
        if "room_id" not in args or not isinstance(args["room_id"], str):
            return False, "unlock_room requires args: {room_id}"
        return True, "OK"

    def run(self, ctx: ActionContext, args: Dict[str, Any]):
        room_id = args["room_id"]
        locked = dict(getattr(ctx.state, "room_locked", {}) or {})
        if room_id not in locked:
            return ctx.state, ToolResult(False, f"Unknown room: {room_id}")
        if not locked.get(room_id, False):
            return ctx.state, ToolResult(False, f"Already unlocked: {room_id}")

        locked[room_id] = False
        from dataclasses import replace
        new_state = replace(ctx.state, room_locked=locked)
        from World.engine import emit
        new_state, ev = emit(new_state, actor=ctx.actor, type="unlock_room", args={"room_id": room_id}, ok=True, message="unlocked")
        return new_state, ToolResult(True, f"Unlocked {room_id}.", events=(ev,))

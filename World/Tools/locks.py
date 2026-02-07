from __future__ import annotations
from typing import Any, Dict, Tuple

from World.engine import Result, lock_room, unlock_room
from World.tools.base import ActionContext

class LockRoomTool:
    name = "lock"

    def can_run(self, ctx: ActionContext, args: Dict[str, Any]) -> Tuple[bool, str]:
        if "room_id" not in args:
            return False, "lock requires args: {room_id}"
        if not isinstance(args["room_id"], str):
            return False, "lock.room_id must be a string"
        return True, "OK"

    def run(self, ctx: ActionContext, args: Dict[str, Any]):
        return lock_room(ctx.house, ctx.state, ctx.actor, args["room_id"])

class UnlockRoomTool:
    name = "unlock"

    def can_run(self, ctx: ActionContext, args: Dict[str, Any]) -> Tuple[bool, str]:
        if "room_id" not in args:
            return False, "unlock requires args: {room_id}"
        if not isinstance(args["room_id"], str):
            return False, "unlock.room_id must be a string"
        return True, "OK"

    def run(self, ctx: ActionContext, args: Dict[str, Any]):
        return unlock_room(ctx.house, ctx.state, ctx.actor, args["room_id"])

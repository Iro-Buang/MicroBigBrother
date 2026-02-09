from __future__ import annotations
from typing import Any, Dict, Tuple

from World.Tools.base import ActionContext
from World.Tools.spec import ToolSpec
from World.results import ToolResult
from World.engine import entities_in_room, whereami
from World.interaction_engine import talk_request, talk_accept, talk_decline, talk_say, talk_end

def _co_located_others(ctx: ActionContext) -> list[str]:
    room_id = ctx.state.locations.get(ctx.actor)
    if not room_id:
        return []
    occ = entities_in_room(ctx.state, room_id)
    return sorted([e for e in occ if e != ctx.actor])

def _pending_for_target(ctx: ActionContext) -> list[str]:
    out = []
    for iid, inter in (getattr(ctx.state, "interactions", {}) or {}).items():
        if inter.kind == "talk" and inter.status == "pending" and inter.target == ctx.actor:
            out.append(iid)
    return sorted(out)

def _active_for_actor(ctx: ActionContext) -> list[str]:
    out = []
    for iid, inter in (getattr(ctx.state, "interactions", {}) or {}).items():
        if inter.kind == "talk" and inter.status == "active" and ctx.actor in (inter.initiator, inter.target):
            out.append(iid)
    return sorted(out)



def _in_active_talk(ctx: ActionContext) -> bool:
    return len(_active_for_actor(ctx)) > 0

class TalkRequestTool:
    name = "talk_request"

    @staticmethod
    def _choices(ctx: ActionContext) -> Dict[str, list[str]]:
        return {"target": _co_located_others(ctx)}

    spec = ToolSpec(
        name="talk_request",
        description="Request to start a conversation with someone in the same room.",
        args_schema={"target": "Actor id in the same room."},
        visible=lambda ctx: (len(_co_located_others(ctx)) > 0) and (not _in_active_talk(ctx)),
        choices=_choices.__func__,
    )

    def can_run(self, ctx: ActionContext, args: Dict[str, Any]) -> Tuple[bool, str]:
        if "target" not in args or not isinstance(args["target"], str):
            return False, "talk_request requires args: {target}"
        if args["target"] == ctx.actor:
            return False, "Denied: you cannot request to talk with yourself."
        return True, "OK"

    def run(self, ctx: ActionContext, args: Dict[str, Any]):
        room_id = ctx.state.locations.get(ctx.actor)
        if not room_id:
            return ctx.state, ToolResult(False, "Unknown location.")
        return talk_request(ctx.state, initiator=ctx.actor, target=args["target"], room_id=room_id)

class TalkAcceptTool:
    name = "talk_accept"

    @staticmethod
    def _choices(ctx: ActionContext) -> Dict[str, list[str]]:
        return {"interaction_id": _pending_for_target(ctx)}

    spec = ToolSpec(
        name="talk_accept",
        description="Accept a pending talk request directed at you.",
        args_schema={"interaction_id": "Pending talk interaction id."},
        visible=lambda ctx: len(_pending_for_target(ctx)) > 0,
        choices=_choices.__func__,
    )

    def can_run(self, ctx: ActionContext, args: Dict[str, Any]) -> Tuple[bool, str]:
        if "interaction_id" not in args or not isinstance(args["interaction_id"], str):
            return False, "talk_accept requires args: {interaction_id}"
        return True, "OK"

    def run(self, ctx: ActionContext, args: Dict[str, Any]):
        return talk_accept(ctx.state, who=ctx.actor, interaction_id=args["interaction_id"])

class TalkDeclineTool:
    name = "talk_decline"

    @staticmethod
    def _choices(ctx: ActionContext) -> Dict[str, list[str]]:
        return {"interaction_id": _pending_for_target(ctx)}

    spec = ToolSpec(
        name="talk_decline",
        description="Decline a pending talk request directed at you.",
        args_schema={"interaction_id": "Pending talk interaction id."},
        visible=lambda ctx: len(_pending_for_target(ctx)) > 0,
        choices=_choices.__func__,
    )

    def can_run(self, ctx: ActionContext, args: Dict[str, Any]) -> Tuple[bool, str]:
        if "interaction_id" not in args or not isinstance(args["interaction_id"], str):
            return False, "talk_decline requires args: {interaction_id}"
        return True, "OK"

    def run(self, ctx: ActionContext, args: Dict[str, Any]):
        return talk_decline(ctx.state, who=ctx.actor, interaction_id=args["interaction_id"])

class TalkSayTool:
    name = "talk_say"

    @staticmethod
    def _choices(ctx: ActionContext) -> Dict[str, list[str]]:
        return {"interaction_id": _active_for_actor(ctx)}

    spec = ToolSpec(
        name="talk_say",
        description="Say something in an active talk interaction you are part of.",
        args_schema={"interaction_id": "Active talk interaction id.", "text": "What you say."},
        visible=lambda ctx: len(_active_for_actor(ctx)) > 0,
        choices=_choices.__func__,
    )

    def can_run(self, ctx: ActionContext, args: Dict[str, Any]) -> Tuple[bool, str]:
        if "interaction_id" not in args or not isinstance(args["interaction_id"], str):
            return False, "talk_say requires args: {interaction_id, text}"
        if "text" not in args or not isinstance(args["text"], str):
            return False, "talk_say.text must be a string"
        if not args["text"].strip():
            return False, "talk_say.text cannot be empty"
        return True, "OK"

    def run(self, ctx: ActionContext, args: Dict[str, Any]):
        return talk_say(ctx.state, who=ctx.actor, interaction_id=args["interaction_id"], text=args["text"])


class TalkEndTool:
    name = "talk_end"

    @staticmethod
    def _choices(ctx: ActionContext) -> Dict[str, list[str]]:
        return {"interaction_id": _active_for_actor(ctx)}

    spec = ToolSpec(
        name="talk_end",
        description="End an active talk interaction you are part of.",
        args_schema={"interaction_id": "Active talk interaction id."},
        visible=lambda ctx: len(_active_for_actor(ctx)) > 0,
        choices=_choices.__func__,
    )

    def can_run(self, ctx: ActionContext, args: Dict[str, Any]) -> Tuple[bool, str]:
        if "interaction_id" not in args or not isinstance(args["interaction_id"], str):
            return False, "talk_end requires args: {interaction_id}"
        return True, "OK"

    def run(self, ctx: ActionContext, args: Dict[str, Any]):
        return talk_end(ctx.state, who=ctx.actor, interaction_id=args["interaction_id"])

# World/Tools/factory.py
from __future__ import annotations

from World.Tools.registry import ToolRegistry
from World.Tools.movement import MoveToTool
from World.Tools.locks import LockRoomTool, UnlockRoomTool, AnnaUnlockRoomTool
from World.Tools.time import EndTurnTool
from World.Tools.social import TalkRequestTool, TalkAcceptTool, TalkDeclineTool, TalkSayTool, TalkEndTool
from World.Tools.tasks_requests import CleanLivingRoomTool, WashDishesTool, CookTool, GuessTool, SkipTool, RequestAnnaTool, TaskAcceptTool, TaskRejectTool


def build_toolbox() -> ToolRegistry:
    tb = ToolRegistry(tools={})

    tb.register(MoveToTool())
    tb.register(LockRoomTool())
    tb.register(UnlockRoomTool())
    tb.register(EndTurnTool())

    # v0.3 social interaction tools
    tb.register(TalkRequestTool())
    tb.register(TalkAcceptTool())
    tb.register(TalkDeclineTool())
    tb.register(TalkSayTool())

    # household task tools
    tb.register(CleanLivingRoomTool())
    tb.register(WashDishesTool())
    tb.register(CookTool())
    tb.register(GuessTool())
    tb.register(SkipTool())

    # task request system (Kevin -> Anna)
    tb.register(RequestAnnaTool())
    tb.register(TaskAcceptTool())
    tb.register(TaskRejectTool())

    # Anna's special unlock (from living room)
    tb.register(AnnaUnlockRoomTool())


    tb.register(TalkEndTool())

    return tb

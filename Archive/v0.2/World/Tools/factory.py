# World/Tools/factory.py
from __future__ import annotations

from World.Tools.registry import ToolRegistry
from World.Tools.movement import MoveToTool
from World.Tools.locks import LockRoomTool, UnlockRoomTool
from World.Tools.time import EndTurnTool


def build_toolbox() -> ToolRegistry:
    tb = ToolRegistry(tools={})

    tb.register(MoveToTool())
    tb.register(LockRoomTool())
    tb.register(UnlockRoomTool())
    tb.register(EndTurnTool())

    return tb

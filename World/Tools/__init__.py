from World.tools.registry import ToolRegistry
from World.tools.movement import MoveToTool
from World.tools.locks import LockRoomTool, UnlockRoomTool
from World.tools.time import EndTurnTool

def build_toolbox() -> ToolRegistry:
    tb = ToolRegistry(tools={})
    tb.register(MoveToTool())
    tb.register(LockRoomTool())
    tb.register(UnlockRoomTool())
    tb.register(EndTurnTool())
    return tb

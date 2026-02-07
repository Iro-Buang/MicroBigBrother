from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, Tuple

from World.engine import Result
from World.tools.base import ActionContext, Tool

@dataclass
class ToolRegistry:
    tools: Dict[str, Tool]

    def register(self, tool: Tool) -> None:
        if tool.name in self.tools:
            raise ValueError(f"Duplicate tool: {tool.name}")
        self.tools[tool.name] = tool

    def invoke(self, tool_name: str, ctx: ActionContext, args: Dict[str, Any]) -> Tuple[ActionContext, Result]:
        tool = self.tools.get(tool_name)
        if not tool:
            return ctx, Result(False, f"Unknown tool: {tool_name}")

        ok, msg = tool.can_run(ctx, args)
        if not ok:
            return ctx, Result(False, msg)

        new_state, res = tool.run(ctx, args)
        return ActionContext(house=ctx.house, state=new_state, actor=ctx.actor), res

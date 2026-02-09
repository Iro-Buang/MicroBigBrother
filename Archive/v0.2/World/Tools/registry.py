from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, Tuple

from World.engine import Result
from World.Tools.base import ActionContext, Tool
from World.Tools.spec import ToolSpec

@dataclass
class ToolRegistry:
    tools: Dict[str, Tool]

    def register(self, tool: Tool) -> None:
        if tool.name in self.tools:
            raise ValueError(f"Duplicate tool: {tool.name}")
        self.tools[tool.name] = tool

    def list_specs(self, ctx) -> list[ToolSpec]:
        specs: list[ToolSpec] = []
        for tool in self.tools.values():
            spec = getattr(tool, "spec", None)
            if spec is None:
                # Skip tools without metadata (or raise if you prefer strict)
                raise AttributeError(f"Tool '{tool.name}' is missing .spec")
            if spec.visible(ctx):
                specs.append(spec)
        return specs


    def invoke(self, tool_name: str, ctx: ActionContext, args: Dict[str, Any]) -> Tuple[ActionContext, Result]:
        tool = self.tools.get(tool_name)
        if not tool:
            return ctx, Result(False, f"Unknown tool: {tool_name}")

        ok, msg = tool.can_run(ctx, args)
        if not ok:
            return ctx, Result(False, msg)

        new_state, res = tool.run(ctx, args)
        return ActionContext(house=ctx.house, state=new_state, actor=ctx.actor), res

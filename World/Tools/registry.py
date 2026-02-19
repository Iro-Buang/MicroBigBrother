from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, Tuple

from World.results import ToolResult
from World.engine import advance_turn
from World.interaction_engine import auto_decline_pending_talks, auto_reject_pending_task_requests
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


    def invoke(self, tool_name: str, ctx: ActionContext, args: Dict[str, Any]) -> Tuple[ActionContext, ToolResult]:
        tool = self.tools.get(tool_name)
        if not tool:
            return ctx, ToolResult(False, f"Unknown tool: {tool_name}")

        ok, msg = tool.can_run(ctx, args)
        if not ok:
            return ctx, ToolResult(False, msg)

        # "Decay" mechanic: if you have pending talk requests directed at you,
        # and you do anything OTHER than accept/decline, they auto-decline.
        if tool_name not in ("talk_accept", "talk_decline", "task_accept", "task_reject"):
            new_state, _evs = auto_decline_pending_talks(ctx.state, target=ctx.actor, reason="decay")
            new_state2, _evs2 = auto_reject_pending_task_requests(new_state, target=ctx.actor, reason="decay")
            ctx = ActionContext(house=ctx.house, state=new_state2, actor=ctx.actor)

        new_state, res = tool.run(ctx, args)

        # Centralized turn consumption. Most tools consume a turn; some (talk accept/decline, talk say/end)
        # do not. Tools that already advance (end_turn) should return consume_turn=False.
        if res.ok and getattr(res, "consume_turn", True):
            new_state = advance_turn(new_state)

        return ActionContext(house=ctx.house, state=new_state, actor=ctx.actor), res

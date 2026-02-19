from __future__ import annotations
from dataclasses import replace
from typing import Any, Dict, Tuple

from World.Tools.base import ActionContext
from World.Tools.spec import ToolSpec
from World.results import ToolResult
from World.engine import emit, can_enter_room

# ----------------------------
# Helpers
# ----------------------------

ONE_TIME_TASKS = {
    "clean_living_room",
    "wash_dishes",
    "cook:egg",
    "cook:bacon",
    "cook:hotdog",
}

def _completed(state) -> set[str]:
    return set(getattr(state, "completed_tasks", frozenset()) or frozenset())

def _mark_completed(state, task_id: str):
    done = _completed(state)
    done.add(task_id)
    return replace(state, completed_tasks=frozenset(done))

def _get_counter(state, actor: str, key: str, default: int = 0) -> int:
    counters = dict(getattr(state, "actor_counters", {}) or {})
    return int((counters.get(actor, {}) or {}).get(key, default) or 0)

def _set_counter(state, actor: str, key: str, value: int):
    counters = dict(getattr(state, "actor_counters", {}) or {})
    actor_c = dict(counters.get(actor, {}) or {})
    actor_c[key] = int(value)
    counters[actor] = actor_c
    return replace(state, actor_counters=counters)

def _inc_counter(state, actor: str, key: str, delta: int, default: int = 0, *, floor: int | None = None, ceil: int | None = None):
    cur = _get_counter(state, actor, key, default)
    nxt = cur + int(delta)
    if floor is not None:
        nxt = max(int(floor), nxt)
    if ceil is not None:
        nxt = min(int(ceil), nxt)
    return _set_counter(state, actor, key, nxt)

def _get_flag(state, actor: str, key: str, default: Any = None) -> Any:
    flags = dict(getattr(state, "actor_flags", {}) or {})
    return (flags.get(actor, {}) or {}).get(key, default)

def _set_flag(state, actor: str, key: str, value: Any):
    flags = dict(getattr(state, "actor_flags", {}) or {})
    actor_f = dict(flags.get(actor, {}) or {})
    actor_f[key] = value
    flags[actor] = actor_f
    return replace(state, actor_flags=flags)

def _award_guess_for_task(state):
    # Every successful task completion grants Anna +1 guess.
    return _inc_counter(state, "anna", "guesses_left", 1, default=0)

# ----------------------------
# Task tools (clean/wash/cook/guess/skip)
# ----------------------------

class CleanLivingRoomTool:
    name = "clean_living_room"

    spec = ToolSpec(
        name="clean_living_room",
        description="Clean the living room (one-time).",
        args_schema={},
        # Realism mode: only Anna can do house chores.
        visible=lambda ctx: (ctx.actor == "anna") and (ctx.state.locations.get(ctx.actor) == "living_room") and ("clean_living_room" not in _completed(ctx.state)),
    )

    def can_run(self, ctx: ActionContext, args: Dict[str, Any]) -> Tuple[bool, str]:
        if ctx.actor != "anna":
            return False, "Denied: only Anna can clean the living room."
        if ctx.state.locations.get(ctx.actor) != "living_room":
            return False, "Denied: must be in living_room."
        if "clean_living_room" in _completed(ctx.state):
            return False, "Denied: living room already cleaned."
        return True, "OK"

    def run(self, ctx: ActionContext, args: Dict[str, Any]):
        state = _mark_completed(ctx.state, "clean_living_room")
        state = _award_guess_for_task(state)
        state, ev = emit(state, actor=ctx.actor, type="task_completed", args={"task_id": "clean_living_room"}, ok=True, message="cleaned living room")
        return state, ToolResult(True, "Living room cleaned.", events=(ev,))


class WashDishesTool:
    name = "wash_dishes"

    spec = ToolSpec(
        name="wash_dishes",
        description="Wash the dishes (one-time).",
        args_schema={},
        # Realism mode: only Anna can do house chores.
        visible=lambda ctx: (ctx.actor == "anna") and (ctx.state.locations.get(ctx.actor) == "kitchen") and ("wash_dishes" not in _completed(ctx.state)),
    )

    def can_run(self, ctx: ActionContext, args: Dict[str, Any]) -> Tuple[bool, str]:
        if ctx.actor != "anna":
            return False, "Denied: only Anna can wash dishes."
        if ctx.state.locations.get(ctx.actor) != "kitchen":
            return False, "Denied: must be in kitchen."
        if "wash_dishes" in _completed(ctx.state):
            return False, "Denied: dishes already washed."
        return True, "OK"

    def run(self, ctx: ActionContext, args: Dict[str, Any]):
        state = _mark_completed(ctx.state, "wash_dishes")
        state = _award_guess_for_task(state)
        state, ev = emit(state, actor=ctx.actor, type="task_completed", args={"task_id": "wash_dishes"}, ok=True, message="washed dishes")
        return state, ToolResult(True, "Dishes washed.", events=(ev,))


class CookTool:
    name = "cook"
    FOODS = ("egg", "bacon", "hotdog")

    @staticmethod
    def _choices(ctx: ActionContext) -> Dict[str, list[str]]:
        done = _completed(ctx.state)
        avail = [f for f in CookTool.FOODS if f"cook:{f}" not in done]
        return {"food": avail}

    spec = ToolSpec(
        name="cook",
        description="Cook one item (egg/bacon/hotdog). Each item is one-time.",
        args_schema={"food": "One of: egg, bacon, hotdog"},
        # Realism mode: only Anna can do house chores.
        visible=lambda ctx: (ctx.actor == "anna") and (ctx.state.locations.get(ctx.actor) == "kitchen") and any(f"cook:{f}" not in _completed(ctx.state) for f in CookTool.FOODS),
        choices=_choices.__func__,
    )

    def can_run(self, ctx: ActionContext, args: Dict[str, Any]) -> Tuple[bool, str]:
        if ctx.actor != "anna":
            return False, "Denied: only Anna can cook."
        if ctx.state.locations.get(ctx.actor) != "kitchen":
            return False, "Denied: must be in kitchen."
        food = args.get("food")
        if food not in self.FOODS:
            return False, "cook requires args: {food: egg|bacon|hotdog}"
        if f"cook:{food}" in _completed(ctx.state):
            return False, f"Denied: already cooked {food}."
        return True, "OK"

    def run(self, ctx: ActionContext, args: Dict[str, Any]):
        food = args["food"]
        state = _mark_completed(ctx.state, f"cook:{food}")
        state = _award_guess_for_task(state)
        state, ev = emit(state, actor=ctx.actor, type="task_completed", args={"task_id": f"cook:{food}"}, ok=True, message=f"cooked {food}")
        return state, ToolResult(True, f"Cooked {food}.", events=(ev,))


class GuessTool:
    name = "guess"

    spec = ToolSpec(
        name="guess",
        description="(Anna) Guess a completed task id (e.g. clean_living_room, wash_dishes, cook:egg). Costs 1 guess.",
        args_schema={"task_id": "Task id to guess."},
        visible=lambda ctx: ctx.actor == "anna",
    )

    def can_run(self, ctx: ActionContext, args: Dict[str, Any]) -> Tuple[bool, str]:
        if ctx.actor != "anna":
            return False, "Denied: only Anna can guess."
        if _get_counter(ctx.state, "anna", "guesses_left", 0) <= 0:
            return False, "Denied: no guesses left."
        task_id = args.get("task_id")
        if not isinstance(task_id, str) or not task_id.strip():
            return False, "guess requires args: {task_id}"
        task_id = task_id.strip().lower()

        # Exact-match only (no fuzzy guessing). If it's not a known one-time task id, reject.
        if task_id not in ONE_TIME_TASKS:
            return False, f"Denied: unknown task id '{task_id}'."

        # Prevent duplicate guesses.
        guessed = _get_flag(ctx.state, "anna", "guessed_task_ids", default=None)
        if guessed is None:
            guessed_set = set()
        else:
            guessed_set = set(guessed) if not isinstance(guessed, set) else guessed
        if task_id in guessed_set:
            return False, "Denied: you already guessed that task id."
        return True, "OK"

    def run(self, ctx: ActionContext, args: Dict[str, Any]):
        task_id = args["task_id"].strip().lower()

        # Record this guess to prevent duplicates.
        guessed = _get_flag(ctx.state, "anna", "guessed_task_ids", default=None)
        guessed_set = set(guessed) if guessed is not None else set()
        guessed_set.add(task_id)

        state = _inc_counter(ctx.state, "anna", "guesses_left", -1, default=0, floor=0)
        state = _set_flag(state, "anna", "guessed_task_ids", sorted(list(guessed_set)))
        correct = task_id in _completed(state)
        state, ev = emit(state, actor="anna", type="guess", args={"task_id": task_id, "correct": bool(correct)}, ok=True, message="guess made")
        msg = "Correct!" if correct else "Wrong."
        return state, ToolResult(True, f"{msg} (guesses left: {_get_counter(state,'anna','guesses_left',0)})", events=(ev,), data={"correct": bool(correct)})


class SkipTool:
    name = "skip"

    spec = ToolSpec(
        name="skip",
        description="Skip your turn.",
        args_schema={},
        visible=lambda ctx: True,
    )

    def can_run(self, ctx: ActionContext, args: Dict[str, Any]) -> Tuple[bool, str]:
        return True, "OK"

    def run(self, ctx: ActionContext, args: Dict[str, Any]):
        # Advance to next actor, but log as an explicit skip
        from World.engine import skip_turn
        return skip_turn(ctx.state, ctx.actor)

# ----------------------------
# Task request tools (Kevin -> Anna)
# ----------------------------

from World.interaction_engine import task_request, task_accept, task_reject

_ALLOWED_REQUEST_TOOLS = {"clean_living_room", "wash_dishes", "cook", "move_to"}

def _pending_task_requests_for_target(ctx: ActionContext) -> list[str]:
    out = []
    for iid, inter in (getattr(ctx.state, "interactions", {}) or {}).items():
        if inter.kind == "task_request" and inter.status == "pending" and inter.target == ctx.actor:
            out.append(iid)
    return sorted(out)

def _available_request_choices(ctx: ActionContext) -> list[str]:
    # Hide once-only tasks that are already completed
    done = _completed(ctx.state)
    out = []
    for name in sorted(_ALLOWED_REQUEST_TOOLS):
        if name == "clean_living_room" and "clean_living_room" in done:
            continue
        if name == "wash_dishes" and "wash_dishes" in done:
            continue
        if name == "cook" and all(f"cook:{f}" in done for f in CookTool.FOODS):
            continue
        out.append(name)
    return out

class RequestAnnaTool:
    name = "request_anna"

    @staticmethod
    def _choices(ctx: ActionContext) -> Dict[str, list[str]]:
        return {"tool": _available_request_choices(ctx)}

    spec = ToolSpec(
        name="request_anna",
        description="(Kevin) Request Anna to perform a task.",
        args_schema={"tool": "Task tool name", "args": "Tool args dict (optional)"},
        visible=lambda ctx: (ctx.actor == "kevin") and (_get_counter(ctx.state, "kevin", "requests_left", 0) > 0) and (len(_available_request_choices(ctx)) > 0),
        choices=_choices.__func__,
    )

    def can_run(self, ctx: ActionContext, args: Dict[str, Any]) -> Tuple[bool, str]:
        if ctx.actor != "kevin":
            return False, "Denied: only Kevin can request tasks."
        if _get_counter(ctx.state, "kevin", "requests_left", 0) <= 0:
            return False, "Denied: Kevin has no requests left."
        tool = args.get("tool")
        if tool not in _ALLOWED_REQUEST_TOOLS:
            return False, f"Denied: tool not requestable. Allowed: {sorted(_ALLOWED_REQUEST_TOOLS)}"
        tool_args = args.get("args", {})
        if tool_args is None:
            tool_args = {}
        if not isinstance(tool_args, dict):
            return False, "request_anna.args must be a dict if provided."

        # once-only availability checks
        done = _completed(ctx.state)
        if tool == "clean_living_room" and "clean_living_room" in done:
            return False, "Denied: task already completed."
        if tool == "wash_dishes" and "wash_dishes" in done:
            return False, "Denied: task already completed."
        if tool == "cook":
            food = tool_args.get("food")
            if food not in CookTool.FOODS:
                return False, "request_anna cook requires args: {food: egg|bacon|hotdog}"
            if f"cook:{food}" in done:
                return False, f"Denied: already cooked {food}."
        if tool == "move_to":
            dst = tool_args.get("dst")
            if not isinstance(dst, str) or not dst:
                return False, "request_anna move_to requires args: {dst}"
        return True, "OK"

    def run(self, ctx: ActionContext, args: Dict[str, Any]):
        tool = args["tool"]
        tool_args = dict(args.get("args", {}) or {})
        state = _inc_counter(ctx.state, "kevin", "requests_left", -1, default=0, floor=0)
        # record request in interactions
        room_id = ctx.state.locations.get("kevin") or "living_room"
        state, res = task_request(state, initiator="kevin", target="anna", room_id=room_id, tool_name=tool, tool_args=tool_args)
        # task_request already consumes turn; but we must return updated counters state
        state = replace(state, actor_counters=getattr(state, "actor_counters"))  # noop clarity
        return state, ToolResult(res.ok, res.message + f" (requests left: {_get_counter(state,'kevin','requests_left',0)})", events=res.events, consume_turn=True)


class TaskAcceptTool:
    name = "task_accept"

    @staticmethod
    def _choices(ctx: ActionContext) -> Dict[str, list[str]]:
        return {"interaction_id": _pending_task_requests_for_target(ctx)}

    spec = ToolSpec(
        name="task_accept",
        description="(Anna) Accept a pending task request from Kevin. Accepting moves you to the relevant room and executes the task immediately.",
        args_schema={"interaction_id": "Pending task request id"},
        visible=lambda ctx: (ctx.actor == "anna") and (len(_pending_task_requests_for_target(ctx)) > 0),
        choices=_choices.__func__,
    )

    def can_run(self, ctx: ActionContext, args: Dict[str, Any]) -> Tuple[bool, str]:
        if ctx.actor != "anna":
            return False, "Denied: only Anna can accept task requests."
        iid = args.get("interaction_id")
        if not isinstance(iid, str) or not iid:
            return False, "task_accept requires args: {interaction_id}"
        if iid not in _pending_task_requests_for_target(ctx):
            return False, "Denied: no such pending task request."
        return True, "OK"

    def run(self, ctx: ActionContext, args: Dict[str, Any]):
        iid = args["interaction_id"]
        state, res = task_accept(ctx.state, target="anna", interaction_id=iid)
        if not res.ok:
            return state, res

        inter = (state.interactions or {}).get(iid)
        tool = (inter.data or {}).get("tool")
        tool_args = dict((inter.data or {}).get("args", {}) or {})

        # Resolve destination for the requested action
        dest_room = None
        if tool == "clean_living_room":
            dest_room = "living_room"
        elif tool in ("wash_dishes", "cook"):
            dest_room = "kitchen"
        elif tool == "move_to":
            dest_room = tool_args.get("dst")

        # Forced move (bypass living-room hub rule), but still respect locked rooms.
        if isinstance(dest_room, str) and dest_room:
            if not can_enter_room(state, "anna", dest_room):
                # can't fulfill; convert to rejected with reason
                state2, r2 = task_reject(state, target="anna", interaction_id=iid, reason="destination locked")
                return state2, ToolResult(False, f"Cannot accept: destination locked ({dest_room}).", events=r2.events)
            state = replace(state, locations={**state.locations, "anna": dest_room})
            state, evm = emit(state, actor="anna", type="forced_move", args={"dst": dest_room, "reason": "task_accept"}, ok=True, message="moved for task")

        # Execute the requested tool immediately (except move_to which was already done)
        if tool == "clean_living_room":
            state, r_task = CleanLivingRoomTool().run(ActionContext(ctx.house, state, "anna"), {})
        elif tool == "wash_dishes":
            state, r_task = WashDishesTool().run(ActionContext(ctx.house, state, "anna"), {})
        elif tool == "cook":
            state, r_task = CookTool().run(ActionContext(ctx.house, state, "anna"), {"food": tool_args.get("food")})
        elif tool == "move_to":
            r_task = ToolResult(True, f"Moved to {dest_room}.", events=())

        # Close the request interaction
        interactions = dict(getattr(state, "interactions", {}) or {})
        if iid in interactions:
            interactions[iid] = replace(interactions[iid], status="closed", ended_by="anna", ended_reason="accepted+done", ended_turn=state.turn)
            state = replace(state, interactions=interactions)

        state, ev = emit(state, actor="anna", type="task_fulfilled", args={"interaction_id": iid, "tool": tool, "tool_args": tool_args}, ok=True, message="task fulfilled")
        all_events = tuple(res.events) + tuple(getattr(r_task, "events", ()) or ()) + (ev,)
        return state, ToolResult(True, f"Accepted and completed: {tool}.", events=all_events, consume_turn=True)


class TaskRejectTool:
    name = "task_reject"

    @staticmethod
    def _choices(ctx: ActionContext) -> Dict[str, list[str]]:
        return {"interaction_id": _pending_task_requests_for_target(ctx)}

    spec = ToolSpec(
        name="task_reject",
        description="(Anna) Reject a pending task request from Kevin. Costs 1 reject.",
        args_schema={"interaction_id": "Pending task request id", "reason": "Optional reason"},
        visible=lambda ctx: (ctx.actor == "anna") and (len(_pending_task_requests_for_target(ctx)) > 0),
        choices=_choices.__func__,
    )

    def can_run(self, ctx: ActionContext, args: Dict[str, Any]) -> Tuple[bool, str]:
        if ctx.actor != "anna":
            return False, "Denied: only Anna can reject task requests."
        if _get_counter(ctx.state, "anna", "rejects_left", 0) <= 0:
            return False, "Denied: no rejects left."
        iid = args.get("interaction_id")
        if not isinstance(iid, str) or not iid:
            return False, "task_reject requires args: {interaction_id}"
        if iid not in _pending_task_requests_for_target(ctx):
            return False, "Denied: no such pending task request."
        return True, "OK"

    def run(self, ctx: ActionContext, args: Dict[str, Any]):
        iid = args["interaction_id"]
        reason = args.get("reason", "rejected")
        state = _inc_counter(ctx.state, "anna", "rejects_left", -1, default=0, floor=0)
        state, res = task_reject(state, target="anna", interaction_id=iid, reason=str(reason))
        if not res.ok:
            return state, res
        return state, ToolResult(True, res.message + f" (rejects left: {_get_counter(state,'anna','rejects_left',0)})", events=res.events, consume_turn=True)

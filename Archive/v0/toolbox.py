# tools.py (MicroBB v1 - minimal tool specs + handlers)
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Tuple, Optional, Protocol

from db import add_event


# ---------------------------------------------
# Prompt formatting helpers
# ---------------------------------------------

def _h(title: str) -> str:
    # Matches your style: _h("TOOL USE")
    return f"=== {title} ==="


# ---------------------------------------------
# Runtime context contract (keep it lightweight)
# ---------------------------------------------

class ToolContext(Protocol):
    """
    Your engine/runtime should provide these fields to tool handlers.

    Required:
      - conn: sqlite connection
      - session_id: str
      - turn_id: int
      - actor: str (npc id executing the tool)
      - world: dict (mutable world state)

    Optional but recommended:
      - pending_talk: dict[str, str] mapping target_npc -> source_npc (or a list of dicts)
      - tasks: dict with task definitions/state
      - guesses: list to record guesses
    """
    conn: Any
    session_id: str
    turn_id: int
    actor: str
    world: Dict[str, Any]
    pending_talk: Dict[str, str]
    tasks: Dict[str, Any]
    guesses: List[Dict[str, Any]]


# ---------------------------------------------
# Tool spec
# ---------------------------------------------

@dataclass(frozen=True)
class ToolSpec:
    name: str
    args_schema: Dict[str, Any]         # simple schema for your prompt + validation
    description: str


ToolHandler = Callable[[ToolContext, Dict[str, Any]], Dict[str, Any]]


# ---------------------------------------------
# Minimal validation (don’t over-engineer)
# ---------------------------------------------

def _require_args(args: Dict[str, Any], required: List[str]) -> None:
    for k in required:
        if k not in args:
            raise ValueError(f"Missing required arg: {k}")


def _as_str(x: Any, field: str) -> str:
    if not isinstance(x, str) or not x.strip():
        raise ValueError(f"Arg '{field}' must be a non-empty string")
    return x.strip()


# ---------------------------------------------
# Tool handlers (v1: simple, deterministic)
# ---------------------------------------------

def tool_wait(ctx: ToolContext, args: Dict[str, Any]) -> Dict[str, Any]:
    # No args.
    add_event(
        ctx.conn,
        session_id=ctx.session_id,
        turn_id=ctx.turn_id,
        actor=ctx.actor,
        event_type="wait",
        content=f"{ctx.actor} waited.",
    )
    return {"ok": True}


def tool_move_to(ctx: ToolContext, args: Dict[str, Any]) -> Dict[str, Any]:
    _require_args(args, ["room"])
    room = _as_str(args["room"], "room")

    # Minimal world model expectation:
    # ctx.world["locations"] = { "anna": "Living Room", "kevin": "Kitchen" }
    # ctx.world["adjacency"] = { "Living Room": ["Kitchen", ...], ... }  (optional)
    locations = ctx.world.setdefault("locations", {})
    current = locations.get(ctx.actor)

    adjacency = ctx.world.get("adjacency")
    if adjacency and current:
        allowed = adjacency.get(current, [])
        if room not in allowed:
            raise ValueError(f"Invalid move: {current} -> {room}")

    locations[ctx.actor] = room

    add_event(
        ctx.conn,
        session_id=ctx.session_id,
        turn_id=ctx.turn_id,
        actor=ctx.actor,
        event_type="move",
        content=f"{ctx.actor} moved to {room}.",
    )
    return {"ok": True, "location": room}


def tool_talk_request(ctx: ToolContext, args: Dict[str, Any]) -> Dict[str, Any]:
    _require_args(args, ["target"])
    target = _as_str(args["target"], "target")

    # Minimal pending talk model:
    # pending_talk[target] = source
    pending = getattr(ctx, "pending_talk", None)
    if pending is None:
        raise ValueError("Runtime missing ctx.pending_talk dict")

    # Overwrite or prevent spamming—pick one. For MicroBB: prevent stacking.
    if target in pending:
        raise ValueError(f"{target} already has a pending talk request.")

    pending[target] = ctx.actor

    add_event(
        ctx.conn,
        session_id=ctx.session_id,
        turn_id=ctx.turn_id,
        actor=ctx.actor,
        event_type="talk_request",
        content=f"{ctx.actor} requested to talk to {target}.",
    )
    return {"ok": True, "target": target}


def tool_accept_talk(ctx: ToolContext, args: Dict[str, Any]) -> Dict[str, Any]:
    _require_args(args, ["source"])
    source = _as_str(args["source"], "source")

    pending = getattr(ctx, "pending_talk", None)
    if pending is None:
        raise ValueError("Runtime missing ctx.pending_talk dict")

    # Accept means: ctx.actor is the target, source must match the pending request
    if pending.get(ctx.actor) != source:
        raise ValueError(f"No pending talk request from {source} to {ctx.actor}.")

    # Consume pending
    del pending[ctx.actor]

    add_event(
        ctx.conn,
        session_id=ctx.session_id,
        turn_id=ctx.turn_id,
        actor=ctx.actor,
        event_type="talk_accept",
        content=f"{ctx.actor} accepted a talk with {source}.",
    )

    # v1 keeps “talk” as an event marker; your dialogue system can run after this.
    # (Example: a 2–6 line exchange in your main loop.)
    return {"ok": True, "talk_with": source}


def tool_reject_talk(ctx: ToolContext, args: Dict[str, Any]) -> Dict[str, Any]:
    _require_args(args, ["source"])
    source = _as_str(args["source"], "source")

    pending = getattr(ctx, "pending_talk", None)
    if pending is None:
        raise ValueError("Runtime missing ctx.pending_talk dict")

    if pending.get(ctx.actor) != source:
        raise ValueError(f"No pending talk request from {source} to {ctx.actor}.")

    del pending[ctx.actor]

    add_event(
        ctx.conn,
        session_id=ctx.session_id,
        turn_id=ctx.turn_id,
        actor=ctx.actor,
        event_type="talk_reject",
        content=f"{ctx.actor} rejected a talk with {source}.",
    )
    return {"ok": True, "rejected": source}


def tool_do_task(ctx: ToolContext, args: Dict[str, Any]) -> Dict[str, Any]:
    _require_args(args, ["task_name"])
    task_name = _as_str(args["task_name"], "task_name")

    # Minimal tasks model:
    # ctx.tasks = {
    #   "clean_living_room": {"location": "Living Room", "done": False},
    #   "wash_dishes": {"location": "Kitchen", "done": False},
    # }
    tasks = getattr(ctx, "tasks", None)
    if tasks is None:
        raise ValueError("Runtime missing ctx.tasks dict")

    if task_name not in tasks:
        raise ValueError(f"Unknown task: {task_name}")

    task = tasks[task_name]
    required_loc = task.get("location")

    locations = ctx.world.setdefault("locations", {})
    my_loc = locations.get(ctx.actor)

    if required_loc and my_loc != required_loc:
        raise ValueError(f"Task '{task_name}' requires location '{required_loc}', you are in '{my_loc}'.")

    # v1: mark done and move on
    task["done"] = True

    add_event(
        ctx.conn,
        session_id=ctx.session_id,
        turn_id=ctx.turn_id,
        actor=ctx.actor,
        event_type="task",
        content=f"{ctx.actor} completed task: {task_name}.",
    )
    return {"ok": True, "task_name": task_name, "done": True}


def tool_make_guess(ctx: ToolContext, args: Dict[str, Any]) -> Dict[str, Any]:
    _require_args(args, ["target", "claim"])
    target = _as_str(args["target"], "target")
    claim = _as_str(args["claim"], "claim")

    # v1: just record it; scoring/validation belongs elsewhere
    guesses = getattr(ctx, "guesses", None)
    if guesses is None:
        raise ValueError("Runtime missing ctx.guesses list")

    entry = {
        "session_id": ctx.session_id,
        "turn_id": ctx.turn_id,
        "actor": ctx.actor,
        "target": target,
        "claim": claim,
    }
    guesses.append(entry)

    add_event(
        ctx.conn,
        session_id=ctx.session_id,
        turn_id=ctx.turn_id,
        actor=ctx.actor,
        event_type="guess",
        content=f"{ctx.actor} made a guess about {target}: {claim}",
    )
    return {"ok": True, "guess": entry}


# ---------------------------------------------
# Toolbox registry
# ---------------------------------------------

TOOLS: List[ToolSpec] = [
    ToolSpec(
        name="move_to",
        args_schema={"room": "string"},
        description="Move to a room (must be allowed by world adjacency if enforced).",
    ),
    ToolSpec(
        name="talk_request",
        args_schema={"target": "string"},
        description="Request to talk with another NPC; creates a pending request for the target.",
    ),
    ToolSpec(
        name="accept_talk",
        args_schema={"source": "string"},
        description="Accept a pending talk request from the given NPC.",
    ),
    ToolSpec(
        name="reject_talk",
        args_schema={"source": "string"},
        description="Reject a pending talk request from the given NPC.",
    ),
    ToolSpec(
        name="do_task",
        args_schema={"task_name": "string"},
        description="Perform a location-gated task (if available).",
    ),
    ToolSpec(
        name="make_guess",
        args_schema={"target": "string", "claim": "string"},
        description="Record a guess (game mechanic / scoring).",
    ),
    ToolSpec(
        name="wait",
        args_schema={},
        description="Do nothing this turn.",
    ),
]

HANDLERS: Dict[str, ToolHandler] = {
    "move_to": tool_move_to,
    "talk_request": tool_talk_request,
    "accept_talk": tool_accept_talk,
    "reject_talk": tool_reject_talk,
    "do_task": tool_do_task,
    "make_guess": tool_make_guess,
    "wait": tool_wait,
}


# ---------------------------------------------
# Prompt block builder (matches your format)
# ---------------------------------------------

def build_toolbox_prompt(TOOL_CALL_PREFIX: str) -> List[str]:
    """
    Returns a list[str] you can extend into your compiled prompt.
    Matches the exact format you pasted.
    """
    lines: List[str] = [
        _h("TOOL USE"),
        "Tools may be used ONLY if needed to answer the user accurately.",
        "If you do not need a tool, reply normally.",
        "",
        "To call a tool, output exactly ONE LINE in this format:",
        f'{TOOL_CALL_PREFIX} {{"name":"<tool_name>","args":{{}}}}',
        "",
        "Rules:",
        "- No extra text before or after the tool call line.",
        "- args MUST be a JSON object ({} if none).",
        "- Use only tool names listed below.",
        "",
        "Available Tools:",
    ]

    for t in TOOLS:
        # Keep it readable and copy-pasteable
        lines.append(f'- {t.name}: {t.description} Args schema: {t.args_schema}')

    return lines


# ---------------------------------------------
# Tool dispatcher (one tool per turn)
# ---------------------------------------------

def dispatch_tool(ctx: ToolContext, tool_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
    if tool_name not in HANDLERS:
        raise ValueError(f"Unknown tool: {tool_name}")
    if not isinstance(args, dict):
        raise ValueError("Tool args must be a JSON object")
    return HANDLERS[tool_name](ctx, args)

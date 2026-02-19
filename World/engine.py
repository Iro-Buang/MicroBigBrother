# World/engine.py
from __future__ import annotations

from dataclasses import replace
from typing import Dict, List, Tuple, Any

from World.house import House
from World.state import WorldState, current_actor
from World.events import Event, new_event
from World.results import ToolResult

# ----------------------------
# Small helpers (keep the file sane)
# ----------------------------

def _get_locked(state: WorldState) -> Dict[str, bool]:
    return dict(getattr(state, "room_locked", {}) or {})

def _get_turn_order(state: WorldState) -> List[str]:
    return list(getattr(state, "turn_order", []) or [])

def _get_turn_index(state: WorldState) -> int:
    return int(getattr(state, "turn_index", 0) or 0)

def _with_state(
    state: WorldState,
    *,
    locations: Dict[str, str] | None = None,
    room_locked: Dict[str, bool] | None = None,
    completed_tasks=None,
    actor_counters=None,
    actor_flags=None,
    turn: int | None = None,
    turn_order: List[str] | None = None,
    turn_index: int | None = None,
    actors=None,
    events=None,
    tasks=None,
    interactions=None,
    next_task_id: int | None = None,
    next_interaction_id: int | None = None,
) -> WorldState:
    """
    Canonical way to copy/update WorldState without forgetting fields.
    Uses dataclasses.replace if possible; falls back to constructing.
    """
    kwargs = {}

    if locations is not None:
        kwargs["locations"] = locations
    if room_locked is not None:
        kwargs["room_locked"] = room_locked

    if completed_tasks is not None:
        kwargs["completed_tasks"] = completed_tasks
    if actor_counters is not None:
        kwargs["actor_counters"] = actor_counters
    if actor_flags is not None:
        kwargs["actor_flags"] = actor_flags
    if turn is not None:
        kwargs["turn"] = turn
    if turn_order is not None:
        kwargs["turn_order"] = turn_order
    if turn_index is not None:
        kwargs["turn_index"] = turn_index
    if actors is not None:
        kwargs["actors"] = actors
    if events is not None:
        kwargs["events"] = events
    if tasks is not None:
        kwargs["tasks"] = tasks
    if interactions is not None:
        kwargs["interactions"] = interactions
    if next_task_id is not None:
        kwargs["next_task_id"] = next_task_id
    if next_interaction_id is not None:
        kwargs["next_interaction_id"] = next_interaction_id

    try:
        return replace(state, **kwargs)
    except Exception:
        # fallback for older versions if replace fails
        return WorldState(
            locations=kwargs.get("locations", dict(state.locations)),
            turn=kwargs.get("turn", state.turn),
            room_locked=kwargs.get("room_locked", _get_locked(state)),
            turn_order=kwargs.get("turn_order", _get_turn_order(state)),
            turn_index=kwargs.get("turn_index", _get_turn_index(state)),
            actors=kwargs.get("actors", getattr(state, "actors", {})),
            events=kwargs.get("events", getattr(state, "events", tuple())),
            tasks=kwargs.get("tasks", getattr(state, "tasks", {})),
            interactions=kwargs.get("interactions", getattr(state, "interactions", {})),
            next_task_id=kwargs.get("next_task_id", getattr(state, "next_task_id", 1)),
            next_interaction_id=kwargs.get("next_interaction_id", getattr(state, "next_interaction_id", 1)),
        )





def append_events(state: WorldState, events: Tuple[Event, ...]) -> WorldState:
    if not events:
        return state
    existing = tuple(getattr(state, "events", tuple()) or tuple())
    return _with_state(state, events=existing + tuple(events))

def emit(state: WorldState, *, actor: str, type: str, args: Dict[str, Any] | None = None, ok: bool = True, message: str = "") -> Tuple[WorldState, Event]:
    ev = new_event(turn=state.turn, actor=actor, type=type, args=args, ok=ok, message=message)
    return append_events(state, (ev,)), ev


# ----------------------------
# Queries
# ----------------------------

def whereami(state: WorldState, who: str = "player") -> str:
    return state.locations[who]

def entities_in_room(state: WorldState, room: str) -> List[str]:
    return sorted([eid for eid, r in state.locations.items() if r == room])

def is_locked(state: WorldState, room_id: str) -> bool:
    return bool(_get_locked(state).get(room_id, False))


# ✅ Semantics: locks block ENTRY only, never EXIT
def can_enter_room(state: WorldState, who: str, room_id: str) -> bool:
    return not is_locked(state, room_id)

def can_exit_room(state: WorldState, who: str, room_id: str) -> bool:
    return True


# ----------------------------
# Ownership / permissions
# ----------------------------

def room_owner(state: WorldState, room_id: str) -> str | None:
    for actor_id, actor in (getattr(state, "actors", {}) or {}).items():
        if room_id in getattr(actor, "owned_rooms", set()):
            return actor_id
    return None

def is_owner_of_room(state: WorldState, who: str, room_id: str) -> bool:
    return room_owner(state, room_id) == who


def can_toggle_lock(house: House, state: WorldState, who: str, room_id: str) -> Tuple[bool, str]:
    if room_id not in house.rooms:
        return False, f"Unknown room: {room_id}"

    owner = room_owner(state, room_id)
    if owner is None:
        return False, f"Room has no owner: {room_id}"

    if who != owner:
        return False, f"Denied: only {owner} can lock/unlock {room_id}"

    who_loc = state.locations.get(who)
    if who_loc is None:
        return False, f"Unknown entity: {who}"

    if who_loc == room_id:
        return True, "OK"

    if room_id in house.edges.get(who_loc, set()):
        return True, "OK"

    return False, f"Denied: {who} must be in {room_id} or adjacent to it to lock/unlock"




# ----------------------------
# Turn system
# ----------------------------


def _reset_turn_flags(state: WorldState, actor_id: str) -> WorldState:
    flags = dict(getattr(state, "actor_flags", {}) or {})
    actor_flags = dict(flags.get(actor_id, {}) or {})
    # per-turn tool constraints
    actor_flags["cooked_this_turn"] = False
    flags[actor_id] = actor_flags
    return _with_state(state, actor_flags=flags)


def advance_turn(state: WorldState) -> WorldState:
    order = _get_turn_order(state)
    idx = _get_turn_index(state)

    if not order:
        # fallback: single-actor world; just increment rounds
        return _with_state(state, turn=state.turn + 1)

    next_idx = idx + 1
    next_turn = state.turn

    # increment round only when we wrap actor index
    if next_idx >= len(order):
        next_idx = 0
        next_turn += 1

    return _with_state(state, turn=next_turn, turn_index=next_idx, turn_order=order)


# ----------------------------
# Actions
# ----------------------------

def apply_move(house: House, state: WorldState, who: str, dst: str) -> Tuple[WorldState, ToolResult]:
    src = state.locations.get(who)
    if src is None:
        return state, ToolResult(False, f"Unknown entity: {who}")

    if dst not in house.rooms:
        return state, ToolResult(False, f"Unknown room: {dst}")

    if dst == src:
        return state, ToolResult(False, f"Invalid move: {src} -> {dst} is not allowed.")

    if dst not in house.edges.get(src, set()):
        return state, ToolResult(False, f"Blocked: {src} -> {dst}")

    if not can_enter_room(state, who, dst):
        return state, ToolResult(False, f"Locked: cannot enter {dst}")

    new_locations = dict(state.locations)
    new_locations[who] = dst

    new_state = _with_state(state, locations=new_locations)
    # emit event before advancing turn
    new_state, ev = emit(new_state, actor=who, type="move", args={"src": src, "dst": dst}, ok=True, message=f"moved {src} -> {dst}")
    # Turn advancement is handled by the toolbox invocation pipeline.
    return new_state, ToolResult(True, f"OK: {who} moved to {dst}.", events=(ev,))


def end_turn(state: WorldState, who: str) -> Tuple[WorldState, ToolResult]:
    """
    Manual skip. Advances to next actor. Round increases only on wrap.
    """
    state, ev = emit(state, actor=who, type="end_turn", args={}, ok=True, message="ended turn")
    new_state = advance_turn(state)
    return new_state, ToolResult(True, f"Turn advanced to {new_state.turn}.", events=(ev,), consume_turn=False)


def skip_turn(state: WorldState, who: str) -> Tuple[WorldState, ToolResult]:
    """
    Explicit skip. Advances to next actor. Round increases only on wrap.
    (Different from end_turn for logging/intent purposes.)
    """
    state, ev = emit(state, actor=who, type="skip", args={}, ok=True, message="skipped turn")
    new_state = advance_turn(state)
    return new_state, ToolResult(True, f"Turn advanced to {new_state.turn}.", events=(ev,), consume_turn=False)


def unlock_room(house: House, state: WorldState, who: str, room_id: str) -> Tuple[WorldState, ToolResult]:
    locked = _get_locked(state)
    if room_id not in locked:
        return state, ToolResult(False, f"No lock state for room: {room_id}")

    ok, msg = can_toggle_lock(house, state, who, room_id)
    if not ok:
        return state, ToolResult(False, msg)

    if not locked.get(room_id, False):
        return state, ToolResult(False, f"Already unlocked: {room_id}")

    locked[room_id] = False
    new_state = _with_state(state, room_locked=locked)
    new_state, ev = emit(new_state, actor=who, type="unlock_room", args={"room_id": room_id}, ok=True, message=f"unlocked {room_id}")
    return new_state, ToolResult(True, f"OK: {who} unlocked {room_id}.", events=(ev,))


def lock_room(house: House, state: WorldState, who: str, room_id: str) -> Tuple[WorldState, ToolResult]:
    locked = _get_locked(state)
    if room_id not in locked:
        return state, ToolResult(False, f"No lock state for room: {room_id}")

    ok, msg = can_toggle_lock(house, state, who, room_id)
    if not ok:
        return state, ToolResult(False, msg)

    if locked.get(room_id, False):
        return state, ToolResult(False, f"Already locked: {room_id}")

    locked[room_id] = True
    new_state = _with_state(state, room_locked=locked)
    new_state, ev = emit(new_state, actor=who, type="lock_room", args={"room_id": room_id}, ok=True, message=f"locked {room_id}")
    return new_state, ToolResult(True, f"OK: {who} locked {room_id}.", events=(ev,))

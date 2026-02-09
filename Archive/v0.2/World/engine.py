# World/engine.py
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Dict, List, Tuple

from World.house import House
from World.state import WorldState

@dataclass(frozen=True)
class Result:
    ok: bool
    message: str


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
    turn: int | None = None,
    turn_order: List[str] | None = None,
    turn_index: int | None = None,
    actors=None,
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
    if turn is not None:
        kwargs["turn"] = turn
    if turn_order is not None:
        kwargs["turn_order"] = turn_order
    if turn_index is not None:
        kwargs["turn_index"] = turn_index
    if actors is not None:
        kwargs["actors"] = actors

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
        )


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

def apply_move(house: House, state: WorldState, who: str, dst: str) -> Tuple[WorldState, Result]:
    src = state.locations.get(who)
    if src is None:
        return state, Result(False, f"Unknown entity: {who}")

    if dst not in house.rooms:
        return state, Result(False, f"Unknown room: {dst}")

    if dst == src:
        return state, Result(False, f"Invalid move: {src} -> {dst} is not allowed.")

    if dst not in house.edges.get(src, set()):
        return state, Result(False, f"Blocked: {src} -> {dst}")

    if not can_enter_room(state, who, dst):
        return state, Result(False, f"Locked: cannot enter {dst}")

    new_locations = dict(state.locations)
    new_locations[who] = dst

    new_state = _with_state(state, locations=new_locations)
    return advance_turn(new_state), Result(True, f"OK: {who} moved to {dst}.")


def end_turn(state: WorldState) -> Tuple[WorldState, Result]:
    """
    Manual skip. Advances to next actor. Round increases only on wrap.
    """
    new_state = advance_turn(state)
    return new_state, Result(True, f"Turn advanced to {new_state.turn}.")


def unlock_room(house: House, state: WorldState, who: str, room_id: str) -> Tuple[WorldState, Result]:
    locked = _get_locked(state)
    if room_id not in locked:
        return state, Result(False, f"No lock state for room: {room_id}")

    ok, msg = can_toggle_lock(house, state, who, room_id)
    if not ok:
        return state, Result(False, msg)

    if not locked.get(room_id, False):
        return state, Result(False, f"Already unlocked: {room_id}")

    locked[room_id] = False
    new_state = _with_state(state, room_locked=locked)
    return advance_turn(new_state), Result(True, f"OK: {who} unlocked {room_id}.")


def lock_room(house: House, state: WorldState, who: str, room_id: str) -> Tuple[WorldState, Result]:
    locked = _get_locked(state)
    if room_id not in locked:
        return state, Result(False, f"No lock state for room: {room_id}")

    ok, msg = can_toggle_lock(house, state, who, room_id)
    if not ok:
        return state, Result(False, msg)

    if locked.get(room_id, False):
        return state, Result(False, f"Already locked: {room_id}")

    locked[room_id] = True
    new_state = _with_state(state, room_locked=locked)
    return advance_turn(new_state), Result(True, f"OK: {who} locked {room_id}.")

# World/engine.py
from dataclasses import dataclass
from typing import Dict, List, Tuple

from .house import House
from .state import WorldState

@dataclass(frozen=True)
class Result:
    ok: bool
    message: str


def whereami(state: WorldState, who: str = "player") -> str:
    return state.locations[who]


def entities_in_room(state: WorldState, room: str) -> List[str]:
    return sorted([eid for eid, r in state.locations.items() if r == room])


def _room_locked_dict(state: WorldState) -> Dict[str, bool]:
    return dict(state.room_locked) if getattr(state, "room_locked", None) else {}


def is_locked(state: WorldState, room_id: str) -> bool:
    return bool(getattr(state, "room_locked", None) and state.room_locked.get(room_id, False))


# ✅ NEW SEMANTICS: locked blocks ENTRY only, never EXIT
def can_enter_room(state: WorldState, who: str, room_id: str) -> bool:
    return not is_locked(state, room_id)

def can_exit_room(state: WorldState, who: str, room_id: str) -> bool:
    return True


def room_owner(room_id: str) -> str | None:
    """
    Generic ownership map.
    You can later move this to House/Room metadata, but this keeps complexity low.
    """
    owners = {
        "anna_room": "anna",
        "kevin_room": "kevin",
    }
    return owners.get(room_id)


def is_owner_of_room(who: str, room_id: str) -> bool:
    return room_owner(room_id) == who


def can_toggle_lock(house: House, state: WorldState, who: str, room_id: str) -> Tuple[bool, str]:
    """
    Owner can lock/unlock their room if:
    - they are inside the room, OR
    - they are in a room adjacent to it (e.g., living_room hub behavior)
    """
    if room_id not in house.rooms:
        return False, f"Unknown room: {room_id}"

    owner = room_owner(room_id)
    if owner is None:
        return False, f"Room has no owner: {room_id}"

    if who != owner:
        return False, f"Denied: only {owner} can lock/unlock {room_id}"

    who_loc = state.locations.get(who)
    if who_loc is None:
        return False, f"Unknown entity: {who}"

    if who_loc == room_id:
        return True, "OK"

    neighbors = house.edges.get(who_loc, set())
    if room_id in neighbors:
        return True, "OK"

    return False, f"Denied: {who} must be in {room_id} or adjacent to it to lock/unlock"


def advance_turn(state: WorldState) -> WorldState:
    order = list(getattr(state, "turn_order", []) or [])
    idx = int(getattr(state, "turn_index", 0) or 0)

    if not order:
        # fallback: single-actor world
        return WorldState(
            locations=dict(state.locations),
            turn=state.turn + 1,
            room_locked=_room_locked_dict(state),
        )

    next_idx = idx + 1
    next_turn = state.turn

    # ONLY increment turn when we wrap
    if next_idx >= len(order):
        next_idx = 0
        next_turn += 1

    return WorldState(
        locations=dict(state.locations),
        turn=next_turn,
        room_locked=_room_locked_dict(state),
        turn_order=order,
        turn_index=next_idx,
    )



def apply_move(house: House, state: WorldState, who: str, dst: str) -> Tuple[WorldState, Result]:
    src = state.locations.get(who)
    if src is None:
        return state, Result(False, f"Unknown entity: {who}")

    if dst not in house.rooms:
        return state, Result(False, f"Unknown room: {dst}")

    if dst == src:
        return state, Result(False, f"Invalid move: {src} -> {dst} is not allowed.")

    allowed = house.edges.get(src, set())
    if dst not in allowed:
        return state, Result(False, f"Blocked: {src} -> {dst}")

    # exit always allowed now; only entry can be blocked
    if not can_enter_room(state, who, dst):
        return state, Result(False, f"Locked: cannot enter {dst}")

    new_locations = dict(state.locations)
    new_locations[who] = dst

    new_state = WorldState(
        locations=new_locations,
        turn=state.turn,
        room_locked=_room_locked_dict(state),
        turn_order=list(getattr(state, "turn_order", []) or []),
        turn_index=int(getattr(state, "turn_index", 0) or 0),
    )
    return advance_turn(new_state), Result(True, f"OK: {who} moved to {dst}.")


def end_turn(state: WorldState) -> Tuple[WorldState, Result]:
    """
    Manual skip. You can keep or remove later.
    """
    return advance_turn(state), Result(True, f"Turn advanced to {state.turn + 1}.")


def unlock_room(house: House, state: WorldState, who: str, room_id: str) -> Tuple[WorldState, Result]:
    locked = _room_locked_dict(state)
    if room_id not in locked:
        return state, Result(False, f"No lock state for room: {room_id}")

    ok, msg = can_toggle_lock(house, state, who, room_id)
    if not ok:
        return state, Result(False, msg)

    if not is_locked(state, room_id):
        return state, Result(False, f"Already unlocked: {room_id}")

    locked[room_id] = False

    new_state = WorldState(
        locations=dict(state.locations),
        turn=state.turn,
        room_locked=locked,
        turn_order=list(getattr(state, "turn_order", []) or []),
        turn_index=int(getattr(state, "turn_index", 0) or 0),
    )
    return advance_turn(new_state), Result(True, f"OK: {who} unlocked {room_id}.")


def lock_room(house: House, state: WorldState, who: str, room_id: str) -> Tuple[WorldState, Result]:
    locked = _room_locked_dict(state)
    if room_id not in locked:
        return state, Result(False, f"No lock state for room: {room_id}")

    ok, msg = can_toggle_lock(house, state, who, room_id)
    if not ok:
        return state, Result(False, msg)

    if is_locked(state, room_id):
        return state, Result(False, f"Already locked: {room_id}")

    locked[room_id] = True

    new_state = WorldState(
        locations=dict(state.locations),
        turn=state.turn,
        room_locked=locked,
        turn_order=list(getattr(state, "turn_order", []) or []),
        turn_index=int(getattr(state, "turn_index", 0) or 0),
    )
    return advance_turn(new_state), Result(True, f"OK: {who} locked {room_id}.")

# World/Tools/tool_validators.py
from __future__ import annotations
from typing import Tuple

from World.house import House
from World.state import WorldState


def ok() -> Tuple[bool, str]:
    return True, "OK"


def actor_exists(state: WorldState, who: str) -> Tuple[bool, str]:
    if who not in state.locations:
        return False, f"Unknown entity: {who}"
    return ok()


def room_exists(house: House, room_id: str) -> Tuple[bool, str]:
    if room_id not in house.rooms:
        return False, f"Unknown room: {room_id}"
    return ok()


def in_room(state: WorldState, who: str, room_id: str) -> Tuple[bool, str]:
    loc = state.locations.get(who)
    if loc != room_id:
        return False, f"Denied: {who} must be in {room_id}"
    return ok()


def adjacent_to(house: House, state: WorldState, who: str, room_id: str) -> Tuple[bool, str]:
    loc = state.locations.get(who)
    if loc is None:
        return False, f"Unknown entity: {who}"
    if room_id in house.edges.get(loc, set()):
        return ok()
    return False, f"Denied: {who} must be adjacent to {room_id}"


def in_or_adjacent(house: House, state: WorldState, who: str, room_id: str) -> Tuple[bool, str]:
    loc = state.locations.get(who)
    if loc is None:
        return False, f"Unknown entity: {who}"
    if loc == room_id or room_id in house.edges.get(loc, set()):
        return ok()
    return False, f"Denied: {who} must be in or adjacent to {room_id}"


# --- lock/ownership checks implemented locally to avoid engine import ---

def is_locked(state: WorldState, room_id: str) -> bool:
    locked = dict(getattr(state, "room_locked", {}) or {})
    return bool(locked.get(room_id, False))


def unlocked_for_entry(state: WorldState, room_id: str) -> Tuple[bool, str]:
    if is_locked(state, room_id):
        return False, f"Locked: cannot enter {room_id}"
    return ok()


def room_owner(state: WorldState, room_id: str) -> str | None:
    for actor_id, actor in (getattr(state, "actors", {}) or {}).items():
        if room_id in getattr(actor, "owned_rooms", set()):
            return actor_id
    return None


def owns_room(state: WorldState, who: str, room_id: str) -> Tuple[bool, str]:
    owner = room_owner(state, room_id)
    if owner is None:
        return False, f"Room has no owner: {room_id}"
    if owner != who:
        return False, f"Denied: only {owner} can do that for {room_id}"
    return ok()


def has_permission(state: WorldState, who: str, perm: str) -> Tuple[bool, str]:
    actor = (getattr(state, "actors", {}) or {}).get(who)
    if actor is None:
        return False, f"Unknown actor metadata: {who}"
    if not getattr(actor, "permissions", {}).get(perm, False):
        return False, f"Denied: {who} lacks permission: {perm}"
    return ok()


def run_validators(*checks: Tuple[bool, str]) -> Tuple[bool, str]:
    for ok_, msg in checks:
        if not ok_:
            return False, msg
    return ok()

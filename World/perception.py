# World/perception.py
from __future__ import annotations
from typing import List

from World.house import House
from World.state import WorldState
from World.engine import entities_in_room

def render_look(house: House, state: WorldState, actor: str) -> str:
    room_id = state.locations.get(actor)
    if not room_id or room_id not in house.rooms:
        return "You are nowhere. (This is probably a bug.)"

    room = house.rooms[room_id]
    movable = sorted(house.edges.get(room_id, set()))
    known = sorted(house.rooms.keys())
    occupants = entities_in_room(state, room_id)

    out: List[str] = []
    out.append(f"{room.name} ({room.id})")

    locked = state.room_locked.get(room.id) if getattr(state, "room_locked", None) else None
    if locked is True:
        out.append("Room state: LOCKED")
    elif locked is False:
        out.append("Room state: unlocked")

    out.append(room.description)

    if room.objects:
        out.append("Notable objects: " + ", ".join(room.objects))

    out.append("Movable spaces: " + (", ".join(movable) if movable else "(none)"))
    out.append("Known spaces: " + ", ".join(known))

    others = [e for e in occupants if e != actor]
    if others:
        out.append("Also here: " + ", ".join(others))
    else:
        out.append("You are alone.")

    return "\n".join(out)

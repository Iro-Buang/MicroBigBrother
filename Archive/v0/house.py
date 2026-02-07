# microbb/house.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Set, Tuple


Room = str
NPCId = str


@dataclass(frozen=True)
class HouseConfig:
    """
    Static house layout + rules.
    This never changes during a run.
    """
    rooms: Tuple[Room, ...]
    hub_room: Room
    adjacency: Dict[Room, Tuple[Room, ...]]
    lockable_rooms: Set[Room]
    initial_locked: Set[Room]
    npcs: Tuple[NPCId, ...]


def default_house() -> HouseConfig:
    rooms = ("living_room", "kitchen", "dining_room", "anna_room", "kevin_room")
    hub = "living_room"

    # Rule: from any non-hub room, you can only go to hub.
    adjacency = {
        "living_room": ("kitchen", "dining_room", "anna_room", "kevin_room"),
        "kitchen": ("living_room",),
        "dining_room": ("living_room",),
        "anna_room": ("living_room",),
        "kevin_room": ("living_room",),
    }

    lockable = {"anna_room", "kevin_room"}  # can expand later
    initial_locked = {"anna_room"}          # per your spec: Anna's room locked initially

    npcs = ("kevin", "anna")

    return HouseConfig(
        rooms=rooms,
        hub_room=hub,
        adjacency=adjacency,
        lockable_rooms=lockable,
        initial_locked=initial_locked,
        npcs=npcs,
    )

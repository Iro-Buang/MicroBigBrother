# World/house.py
from dataclasses import dataclass
from typing import Dict, List, Set

@dataclass(frozen=True)
class Room:
    id: str
    name: str
    description: str
    objects: List[str]

@dataclass(frozen=True)
class House:
    rooms: Dict[str, Room]               # room_id -> Room
    edges: Dict[str, Set[str]]           # adjacency list (movable spaces)

def default_house() -> House:
    rooms = {
        "living_room": Room(
            id="living_room",
            name="Living Room",
            description=(
                "A cramped but functional living room. A sagging couch faces a small TV. "
                "There’s a faint hum from a router that’s holding the whole universe together."
            ),
            objects=["couch", "coffee_table", "tv", "router", "window_curtains"],
        ),
        "dining_room": Room(
            id="dining_room",
            name="Dining Room",
            description=(
                "A modest dining room with a table that looks like it’s seen too many 'serious talks'. "
                "Chairs slightly misaligned, like someone stood up mid-conversation."
            ),
            objects=["dining_table", "chairs", "placemats", "cabinet"],
        ),
        "kitchen": Room(
            id="kitchen",
            name="Kitchen",
            description=(
                "A practical kitchen. Clean enough to cook, messy enough to be believable. "
                "There’s a rice cooker that feels like a national infrastructure asset."
            ),
            objects=["rice_cooker", "sink", "fridge", "counter", "knife_rack"],
        ),
        "anna_room": Room(
            id="anna_room",
            name="Anna's Room",
            description=(
                "Anna’s room is neat in a deliberate way—like order is a defense mechanism. "
                "Soft lighting, a desk, and a quiet sense of 'don’t touch my stuff'."
            ),
            objects=["desk", "lamp", "bookshelf", "bed", "closet"],
        ),
        "kevin_room": Room(
            id="kevin_room",
            name="Kevin's Room",
            description=(
                "Kevin’s room has the energy of unfinished projects. "
                "A chair with clothes on it. A desk that’s trying its best. "
                "The vibe says: 'I’ll optimize this later.'"
            ),
            objects=["desk", "chair", "laundry_pile", "bed", "power_strip"],
        ),
    }

    edges = {
        "living_room": {"dining_room", "kitchen", "kevin_room", "anna_room"},
        "dining_room": {"living_room", "kitchen"},
        "kitchen": {"living_room", "dining_room"},
        "anna_room": {"living_room"},     # rooms exist even if not “public”; adjacency controls access
        "kevin_room": {"living_room"},
    }

    return House(rooms=rooms, edges=edges)

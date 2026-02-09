# World/state.py
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List

from NPC.actors import Actor

@dataclass(frozen=True)
class WorldState:
    locations: Dict[str, str]                      # entity_id -> room_id (canonical)
    turn: int = 0                                  # round index
    room_locked: Dict[str, bool] = field(default_factory=dict)

    turn_order: List[str] = field(default_factory=list)
    turn_index: int = 0

    actors: Dict[str, Actor] = field(default_factory=dict)  # entity_id -> Actor metadata


def current_actor(state: WorldState) -> str:
    if not state.turn_order:
        return "player"
    return state.turn_order[state.turn_index]


def make_initial_state() -> WorldState:
    actors = {
        # "player": Actor(id="player", display_name="Player", kind="player"),
        "kevin": Actor(id="kevin", display_name="Kevin", kind="npc", owned_rooms={"kevin_room"}),
        "anna": Actor(id="anna", display_name="Anna", kind="npc", owned_rooms={"anna_room"}),
    }

    return WorldState(
        locations={
            # "player": "living_room",
            "kevin": "kevin_room",
            "anna": "anna_room",
        },
        turn=0,
        room_locked={
            "anna_room": True,
            "kevin_room": False,
        },
        turn_order=["kevin", "anna"],
        turn_index=0,
        actors=actors,
    )

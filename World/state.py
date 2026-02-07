# World/state.py
from dataclasses import dataclass
from typing import Dict, List


@dataclass
class WorldState:
    locations: Dict[str, str]
    turn: int = 0
    room_locked: Dict[str, bool] = None
    turn_order: List[str] = None
    turn_index: int = 0

def make_initial_state() -> WorldState:
    return WorldState(
        locations={
            "player": "living_room",
            "kevin": "kevin_room",
            "anna": "anna_room",
        },
        turn=0,
        room_locked={
            "anna_room": True,
            "kevin_room": False,
        },
        turn_order=["kevin", "anna", "player"],
        turn_index=0,
    )

def current_actor(state: WorldState) -> str:
    return state.turn_order[state.turn_index]

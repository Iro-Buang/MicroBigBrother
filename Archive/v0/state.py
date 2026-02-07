# microbb/state.py
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional, Set


@dataclass
class WorldState:
    """
    Mutable truth about the world at time t.
    This is NOT memory. It's the game save.
    """
    turn_id: int = 1

    # locations[npc_id] = room
    locations: Dict[str, str] = field(default_factory=dict)

    # locked rooms
    locked: Set[str] = field(default_factory=set)

    # pending talk request: who requested to talk to whom (simple v0)
    talk_request_from: Dict[str, Optional[str]] = field(default_factory=dict)  # target -> requester

    # optional counters for later
    rejects_left: Dict[str, int] = field(default_factory=dict)
    requests_left: Dict[str, int] = field(default_factory=dict)
    guesses_left: Dict[str, int] = field(default_factory=dict)


def make_initial_state() -> WorldState:
    st = WorldState()

    st.locations = {
        "kevin": "living_room",
        "anna": "kitchen",
    }

    st.locked = {"anna_room"}

    st.talk_request_from = {
        "kevin": None,
        "anna": None,
    }

    # Counters: keep these but you can ignore them until needed
    st.rejects_left = {"anna": 6}
    st.requests_left = {"kevin": 9}
    st.guesses_left = {"anna": 3}

    return st

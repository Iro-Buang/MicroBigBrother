# World/state.py
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Any, FrozenSet

from NPC.actors import Actor
from World.events import Event
from World.tasks import TaskInstance
from World.interactions import Interaction

@dataclass(frozen=True)
class WorldState:
    # Core world
    locations: Dict[str, str]                      # entity_id -> room_id (canonical)
    turn: int = 0                                  # round index
    room_locked: Dict[str, bool] = field(default_factory=dict)

    # Gameplay/task state
    completed_tasks: FrozenSet[str] = field(default_factory=frozenset)   # one-time tasks completed (e.g. "cook:egg")
    actor_counters: Dict[str, Dict[str, int]] = field(default_factory=dict)  # per-actor resources (guesses, rejects, requests)
    actor_flags: Dict[str, Dict[str, Any]] = field(default_factory=dict)     # per-actor per-turn flags (reset on turn start)

    # Turn system
    turn_order: List[str] = field(default_factory=list)
    turn_index: int = 0

    # Actors metadata
    actors: Dict[str, Actor] = field(default_factory=dict)  # entity_id -> Actor metadata

    # v0.3: state trackers
    events: Tuple[Event, ...] = field(default_factory=tuple)
    tasks: Dict[str, TaskInstance] = field(default_factory=dict)
    interactions: Dict[str, Interaction] = field(default_factory=dict)

    # deterministic id counters (keeps debug sane)
    next_task_id: int = 1
    next_interaction_id: int = 1


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

    # Tunable gameplay parameters (kept in state for deterministic replays)
    actor_counters = {
        "kevin": {"requests_left": 9},
        "anna": {"guesses_left": 1, "rejects_left": 3},
    }
    actor_flags = {
        "kevin": {"cooked_this_turn": False},
        "anna": {"cooked_this_turn": False},
    }
    completed_tasks = frozenset()

    return WorldState(
        locations={
            # "player": "living_room",
            "kevin": "living_room",
            "anna": "living_room",
        },
        turn=0,
        room_locked={
            "anna_room": True,
            "kevin_room": False,
        },
        completed_tasks=completed_tasks,
        actor_counters=actor_counters,
        actor_flags=actor_flags,
        turn_order=["kevin", "anna"],
        turn_index=0,
        actors=actors,
        events=tuple(),
        tasks={},
        interactions={},
        next_task_id=1,
        next_interaction_id=1,
    )

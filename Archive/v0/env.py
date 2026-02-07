# microbb/env.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from house import HouseConfig
from state import WorldState


@dataclass
class ActionResult:
    ok: bool
    message: str
    # list of (scope, owner_id, key, op, value) — compatible with your state_deltas table idea
    deltas: List[Tuple[str, str, str, str, Any]]


class MicroBBEnv:
    def __init__(self, house: HouseConfig, state: WorldState):
        self.house = house
        self.state = state

    # -----------------------
    # Observation / Perception
    # -----------------------
    def get_observation(self, npc_id: str) -> List[str]:
        """
        Facts visible to this NPC this turn.
        Keep it factual, not interpretive.
        """
        room = self.state.locations[npc_id]
        others_here = [
            other for other, r in self.state.locations.items()
            if other != npc_id and r == room
        ]

        facts = [
            f"You are in the {room}.",
        ]

        if others_here:
            facts.append(f"Also here: {', '.join(others_here)}.")
        else:
            facts.append("You are alone in this room.")

        if room in self.house.lockable_rooms:
            if room in self.state.locked:
                facts.append(f"The {room} is locked.")
            else:
                facts.append(f"The {room} is unlocked.")

        # talk request visibility (simple)
        requester = self.state.talk_request_from.get(npc_id)
        if requester:
            facts.append(f"{requester} requested to talk to you.")

        return facts

    # -----------------------
    # Tool curation (what can be done THIS turn)
    # -----------------------
    def get_allowed_actions(self, npc_id: str) -> List[Dict[str, Any]]:
        """
        Returns ToolSpec-like dicts (minimal) so later you can map to ToolSpec objects.
        For now: we just return {name, args_schema, description}.
        """
        room = self.state.locations[npc_id]
        neighbors = self.house.adjacency.get(room, ())

        actions: List[Dict[str, Any]] = []

        # move_to is always available, but constrained by adjacency + locks
        actions.append({
            "name": "move_to",
            "description": "Move to another room.",
            "args_schema": {
                "room": {"type": "string", "enum": list(neighbors)}
            }
        })

        # skip_turn always allowed
        actions.append({
            "name": "skip_turn",
            "description": "Do nothing this turn.",
            "args_schema": {}
        })

        # talk actions only if someone else is present
        others_here = [
            other for other, r in self.state.locations.items()
            if other != npc_id and r == room
        ]
        if others_here:
            actions.append({
                "name": "talk_request",
                "description": "Request to talk to the other NPC in the room.",
                "args_schema": {"target": {"type": "string", "enum": others_here}},
            })

        # accept/reject talk only if someone requested you
        if self.state.talk_request_from.get(npc_id):
            actions.append({
                "name": "accept_talk",
                "description": "Accept the talk request.",
                "args_schema": {},
            })
            actions.append({
                "name": "reject_talk",
                "description": "Reject the talk request.",
                "args_schema": {},
            })

        return actions

    # -----------------------
    # Reducer / physics (apply one action)
    # -----------------------
    def apply_action(self, npc_id: str, action_name: str, args: Optional[Dict[str, Any]] = None) -> ActionResult:
        args = args or {}

        if action_name == "skip_turn":
            return ActionResult(True, f"{npc_id} skipped the turn.", deltas=[])

        if action_name == "move_to":
            return self._move_to(npc_id, args.get("room"))

        if action_name == "talk_request":
            return self._talk_request(npc_id, args.get("target"))

        if action_name == "accept_talk":
            return self._accept_talk(npc_id)

        if action_name == "reject_talk":
            return self._reject_talk(npc_id)

        return ActionResult(False, f"Unknown action: {action_name}", deltas=[])

    def end_turn(self) -> None:
        self.state.turn_id += 1

    # -----------------------
    # Action implementations
    # -----------------------
    def _move_to(self, npc_id: str, room: Optional[str]) -> ActionResult:
        if not room:
            return ActionResult(False, "move_to requires 'room'.", [])

        current = self.state.locations[npc_id]
        allowed = self.house.adjacency.get(current, ())

        if room not in allowed:
            return ActionResult(False, f"Invalid move: {current} -> {room} is not allowed.", [])

        if room in self.state.locked:
            return ActionResult(False, f"Cannot enter {room}: it is locked.", [])

        self.state.locations[npc_id] = room
        deltas = [("world", npc_id, "location", "set", room)]
        return ActionResult(True, f"{npc_id} moved to {room}.", deltas)

    def _talk_request(self, npc_id: str, target: Optional[str]) -> ActionResult:
        if not target:
            return ActionResult(False, "talk_request requires 'target'.", [])

        room = self.state.locations[npc_id]
        if self.state.locations.get(target) != room:
            return ActionResult(False, f"{target} is not in the same room.", [])

        if self.state.talk_request_from.get(target):
            return ActionResult(False, f"{target} already has a pending talk request.", [])

        self.state.talk_request_from[target] = npc_id
        deltas = [("world", target, "talk_request_from", "set", npc_id)]
        return ActionResult(True, f"{npc_id} requested to talk to {target}.", deltas)

    def _accept_talk(self, npc_id: str) -> ActionResult:
        requester = self.state.talk_request_from.get(npc_id)
        if not requester:
            return ActionResult(False, "No pending talk request to accept.", [])

        # Clear request (v0)
        self.state.talk_request_from[npc_id] = None
        deltas = [("world", npc_id, "talk_request_from", "set", None)]
        return ActionResult(True, f"{npc_id} accepted the talk request from {requester}.", deltas)

    def _reject_talk(self, npc_id: str) -> ActionResult:
        requester = self.state.talk_request_from.get(npc_id)
        if not requester:
            return ActionResult(False, "No pending talk request to reject.", [])

        self.state.talk_request_from[npc_id] = None
        deltas = [("world", npc_id, "talk_request_from", "set", None)]
        return ActionResult(True, f"{npc_id} rejected the talk request from {requester}.", deltas)

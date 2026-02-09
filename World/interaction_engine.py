# World/interaction_engine.py
from __future__ import annotations
from dataclasses import replace
from typing import Any, Dict, Tuple

from World.state import WorldState
from World.interactions import Interaction
from World.results import ToolResult
from World.engine import emit


def auto_decline_pending_talks(state: WorldState, *, target: str, reason: str = "decay") -> Tuple[WorldState, Tuple]:
    """Auto-decline all pending talk requests directed at `target`.

    Used for "decay" behavior: if the target does something else on their turn,
    any pending talk requests are treated as implicitly declined.

    Returns: (new_state, events_emitted)
    """
    interactions = dict(getattr(state, "interactions", {}) or {})
    evs = []
    changed = False
    for iid, inter in list(interactions.items()):
        if inter.kind == "talk" and inter.status == "pending" and inter.target == target:
            interactions[iid] = replace(inter, status="declined", ended_by=target, ended_reason=reason, ended_turn=state.turn)
            changed = True
            state, ev = emit(state, actor=target, type="talk_decline", args={"interaction_id": iid, "reason": reason, "auto": True}, ok=True, message=f"auto-declined ({reason})")
            evs.append(ev)
    if changed:
        state = replace(state, interactions=interactions)
    return state, tuple(evs)

def _new_interaction_id(state: WorldState) -> Tuple[WorldState, str]:
    n = int(getattr(state, "next_interaction_id", 1) or 1)
    new_state = replace(state, next_interaction_id=n + 1)
    return new_state, f"i{n}"

def _close_interaction(state: WorldState, interaction_id: str, *, ended_by: str, reason: str) -> WorldState:
    interactions = dict(getattr(state, "interactions", {}) or {})
    inter = interactions.get(interaction_id)
    if not inter:
        return state
    interactions[interaction_id] = replace(
        inter,
        status="closed",
        ended_by=ended_by,
        ended_reason=reason,
        ended_turn=state.turn,
    )
    return replace(state, interactions=interactions)

def talk_request(state: WorldState, *, initiator: str, target: str, room_id: str) -> Tuple[WorldState, ToolResult]:
    if initiator == target:
        return state, ToolResult(False, "Denied: you cannot request to talk with yourself.")

    # must be co-located
    if state.locations.get(initiator) != room_id or state.locations.get(target) != room_id:
        return state, ToolResult(False, "Talk request requires both actors to be in the same room.")

    # deny if either is already in active talk
    for it in (getattr(state, "interactions", {}) or {}).values():
        if it.kind == "talk" and it.status == "active":
            if initiator in (it.initiator, it.target) or target in (it.initiator, it.target):
                return state, ToolResult(False, "Denied: someone is already in an active conversation.")

    # one pending request at a time per (initiator,target)
    for it in (getattr(state, "interactions", {}) or {}).values():
        if it.kind == "talk" and it.status == "pending" and it.initiator == initiator and it.target == target:
            return state, ToolResult(False, f"Denied: you already have a pending talk request to {target}.")

    state, iid = _new_interaction_id(state)
    interactions = dict(getattr(state, "interactions", {}) or {})
    inter = Interaction(
        id=iid,
        kind="talk",
        initiator=initiator,
        target=target,
        room_id=room_id,
        status="pending",
        created_turn=state.turn,
        messages=tuple(),
        max_exchanges=3,
    )
    interactions[iid] = inter
    state = replace(state, interactions=interactions)

    state, ev = emit(
        state,
        actor=initiator,
        type="talk_request",
        args={"target": target, "room_id": room_id, "interaction_id": iid},
        ok=True,
        message="talk requested",
    )
    return state, ToolResult(True, f"OK: {initiator} requested to talk with {target}.", events=(ev,), data={"interaction_id": iid})

def talk_accept(state: WorldState, *, who: str, interaction_id: str) -> Tuple[WorldState, ToolResult]:
    interactions = dict(getattr(state, "interactions", {}) or {})
    inter = interactions.get(interaction_id)
    if not inter:
        return state, ToolResult(False, f"Unknown interaction: {interaction_id}")
    if inter.kind != "talk":
        return state, ToolResult(False, "Not a talk interaction.")
    if inter.status != "pending":
        return state, ToolResult(False, f"Invalid state: {inter.status}")
    if who != inter.target:
        return state, ToolResult(False, f"Denied: only {inter.target} can accept this talk request.")
    if state.locations.get(inter.initiator) != inter.room_id or state.locations.get(inter.target) != inter.room_id:
        return state, ToolResult(False, "Talk no longer possible: not in the same room.")

    interactions[interaction_id] = replace(inter, status="active", started_turn=state.turn)
    state = replace(state, interactions=interactions)

    state, ev = emit(state, actor=who, type="talk_start", args={"interaction_id": interaction_id}, ok=True, message="talk started")

    # Conversation windows are meant to run as a short "sub-loop" and should not
    # force turn-advancement on every utterance. We keep the turn pointer as-is
    # and let the CLI decide when to advance the broader sim.
    return state, ToolResult(True, f"OK: talk started between {inter.initiator} and {inter.target}.", events=(ev,), consume_turn=False)

def talk_decline(state: WorldState, *, who: str, interaction_id: str) -> Tuple[WorldState, ToolResult]:
    interactions = dict(getattr(state, "interactions", {}) or {})
    inter = interactions.get(interaction_id)
    if not inter:
        return state, ToolResult(False, f"Unknown interaction: {interaction_id}")
    if inter.kind != "talk":
        return state, ToolResult(False, "Not a talk interaction.")
    if inter.status != "pending":
        return state, ToolResult(False, f"Invalid state: {inter.status}")
    if who != inter.target:
        return state, ToolResult(False, f"Denied: only {inter.target} can decline this talk request.")

    interactions[interaction_id] = replace(inter, status="declined")
    state = replace(state, interactions=interactions)
    state, ev = emit(state, actor=who, type="talk_decline", args={"interaction_id": interaction_id}, ok=True, message="talk declined")
    return state, ToolResult(True, f"OK: {who} declined the talk request.", events=(ev,), consume_turn=False)

def talk_end(state: WorldState, *, who: str, interaction_id: str) -> Tuple[WorldState, ToolResult]:
    interactions = dict(getattr(state, "interactions", {}) or {})
    inter = interactions.get(interaction_id)
    if not inter:
        return state, ToolResult(False, f"Unknown interaction: {interaction_id}")
    if inter.kind != "talk":
        return state, ToolResult(False, "Not a talk interaction.")
    if inter.status != "active":
        return state, ToolResult(False, f"Invalid state: {inter.status}")
    if who not in (inter.initiator, inter.target):
        return state, ToolResult(False, "Denied: you are not a participant in this talk.")

    state = _close_interaction(state, interaction_id, ended_by=who, reason="ended_by_actor")
    state, ev = emit(state, actor=who, type="talk_end", args={"interaction_id": interaction_id, "reason": "ended_by_actor"}, ok=True, message="talk ended")
    # Don't advance turns for talk_end; the CLI may be running a convo sub-loop.
    return state, ToolResult(True, f"OK: talk ended by {who}.", events=(ev,), consume_turn=False)

def talk_say(state: WorldState, *, who: str, interaction_id: str, text: str) -> Tuple[WorldState, ToolResult]:
    interactions = dict(getattr(state, "interactions", {}) or {})
    inter = interactions.get(interaction_id)
    if not inter:
        return state, ToolResult(False, f"Unknown interaction: {interaction_id}")
    if inter.kind != "talk":
        return state, ToolResult(False, "Not a talk interaction.")
    if inter.status != "active":
        return state, ToolResult(False, f"Invalid state: {inter.status}")
    if who not in (inter.initiator, inter.target):
        return state, ToolResult(False, "Denied: you are not a participant in this talk.")
    if state.locations.get(inter.initiator) != inter.room_id or state.locations.get(inter.target) != inter.room_id:
        # auto-close
        state = _close_interaction(state, interaction_id, ended_by=who, reason="separated")
        state, ev_end = emit(state, actor=who, type="talk_end", args={"interaction_id": interaction_id, "reason": "separated"}, ok=True, message="talk ended (separated)")
        return state, ToolResult(True, "Talk ended: participants are no longer in the same room.", events=(ev_end,), consume_turn=False)

    msg = {"speaker": who, "text": text, "turn": state.turn}
    updated = replace(inter, messages=inter.messages + (msg,))
    interactions[interaction_id] = updated
    state = replace(state, interactions=interactions)

    state, ev_say = emit(state, actor=who, type="talk_say", args={"interaction_id": interaction_id, "text": text}, ok=True, message="said something")

    # Auto-close after 3 exchanges total (6 utterances)
    evs = [ev_say]
    if updated.utterances >= updated.max_utterances:
        state = _close_interaction(state, interaction_id, ended_by=who, reason="max_exchanges")
        state, ev_end = emit(state, actor=who, type="talk_end", args={"interaction_id": interaction_id, "reason": "max_exchanges"}, ok=True, message="talk ended (max exchanges)")
        evs.append(ev_end)
        msg_out = f"{who}: {text}  [talk ended: max exchanges]"
    else:
        msg_out = f"{who}: {text}"

    # Do not advance turns on every utterance; let the convo window handle flow.
    return state, ToolResult(True, msg_out, events=tuple(evs), consume_turn=False)

# World/interactions.py
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, Tuple, Any, Literal, Optional

InteractionStatus = Literal["pending", "active", "declined", "closed"]

@dataclass(frozen=True)
class Interaction:
    id: str
    kind: str                       # e.g. "talk"
    initiator: str
    target: str
    room_id: str
    status: InteractionStatus = "pending"
    created_turn: int = 0
    started_turn: Optional[int] = None
    ended_turn: Optional[int] = None
    ended_by: Optional[str] = None
    ended_reason: Optional[str] = None

    # Generic payload (used by non-talk interactions)
    data: Dict[str, Any] = field(default_factory=dict)

    # Talk mechanics
    max_exchanges: int = 3          # 1 exchange = initiator+target back-and-forth (2 utterances)
    messages: Tuple[Dict[str, Any], ...] = field(default_factory=tuple)  # {"speaker":..., "text":..., "turn":...}

    @property
    def utterances(self) -> int:
        return len(self.messages)

    @property
    def exchanges_used(self) -> int:
        return self.utterances // 2

    @property
    def max_utterances(self) -> int:
        return max(0, int(self.max_exchanges)) * 2


def active_talk_id(state: Any, actor: str) -> Optional[str]:
    """Return the active talk interaction id the actor is part of (at most one by design)."""
    for iid, inter in (getattr(state, "interactions", {}) or {}).items():
        if inter.kind == "talk" and inter.status == "active" and actor in (inter.initiator, inter.target):
            return iid
    return None


def pending_talk_ids_for_target(state: Any, actor: str) -> list[str]:
    out: list[str] = []
    for iid, inter in (getattr(state, "interactions", {}) or {}).items():
        if inter.kind == "talk" and inter.status == "pending" and inter.target == actor:
            out.append(iid)
    return sorted(out)

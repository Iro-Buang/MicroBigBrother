from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, Set

@dataclass(frozen=True)
class Actor:
    """
    Metadata about an entity in the world.
    Location is stored in WorldState.locations to keep movement simple.
    """
    id: str
    display_name: str
    kind: str = "npc"  # "player" | "npc" | "operator" etc.

    # Rooms this actor can lock/unlock as "owner"
    owned_rooms: Set[str] = field(default_factory=set)

    # Generic permission switches you’ll use in Step 4
    permissions: Dict[str, bool] = field(default_factory=dict)

    # Step 4/5 counters (requests, rejections, etc.)
    counters: Dict[str, int] = field(default_factory=dict)

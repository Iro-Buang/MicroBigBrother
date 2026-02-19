# World/prompt_compiler.py
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Tuple

import yaml

from World.perception import render_look
from World.engine import can_enter_room
from World.Tools.base import ActionContext

# v0.4 task ownership hints (used for prompt clarity)
TASK_DOERS: Dict[str, List[str]] = {
    # Realism mode: Anna-only chores.
    "clean_living_room": ["anna"],
    "wash_dishes": ["anna"],
    "cook": ["anna"],  # cook <food>
}

def _project_root() -> Path:
    # .../World/prompt_compiler.py -> project root is parent of World/
    return Path(__file__).resolve().parents[1]


def _load_yaml(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_world_prompt_config() -> Dict[str, Any]:
    return _load_yaml(_project_root() / "World" / "world_prompt_config.yaml")


def load_transient_goals() -> Dict[str, Any]:
    return _load_yaml(_project_root() / "LLM Engine" / "transient_goals.yaml")


def _completed_tasks(state: Any) -> set[str]:
    return set(getattr(state, "completed_tasks", frozenset()) or frozenset())


def _summarize_last_events(state: Any, n: int = 20) -> List[str]:
    evs = list(getattr(state, "events", []) or [])
    if not evs:
        return []
    # Keep last N events (not necessarily turns; good enough for now)
    out: List[str] = []
    for ev in evs[-n:]:
        turn = getattr(ev, "turn", "?")
        actor = getattr(ev, "actor", "?")
        typ = getattr(ev, "type", "?")
        msg = getattr(ev, "message", "") or ""
        ok = getattr(ev, "ok", True)
        tag = "ok" if ok else "fail"
        if msg:
            out.append(f"round={turn} actor={actor} action={typ} ({tag}): {msg}")
        else:
            out.append(f"round={turn} actor={actor} action={typ} ({tag})")
    return out


def build_perception_facts(*, actor_id: str, house: Any, state: Any, toolbox: Any | None = None) -> List[str]:
    facts: List[str] = []
    if house is None or state is None:
        return ["(no world context)"]

    room_id = (state.locations or {}).get(actor_id, "unknown")
    facts.append(f"You are in: {room_id}")
    # Reuse existing look renderer (gives room description + occupants + objects)
    try:
        facts.append("Room details:")
        look = render_look(house, state, actor_id)
        for line in str(look).splitlines():
            if line.strip():
                facts.append(f"  {line}")
    except Exception:
        pass

    # Adjacent / accessible rooms
    edges = getattr(house, "edges", {}) or {}
    neighbors = sorted(list((edges.get(room_id, set()) or set())))
    accessible: List[str] = []
    blocked: List[str] = []
    for dst in neighbors:
        try:
            if can_enter_room(state, actor_id, dst):
                accessible.append(dst)
            else:
                blocked.append(dst)
        except Exception:
            # if we can't evaluate, still list as unknown-access
            accessible.append(dst)

    facts.append("Rooms you can move into:")
    if accessible:
        facts.append("  " + ", ".join(accessible))
    else:
        facts.append("  (none)")
    if blocked:
        facts.append("Rooms nearby but blocked:")
        facts.append("  " + ", ".join(blocked))

    # Pending interactions relevant to this actor
    try:
        interactions = dict(getattr(state, "interactions", {}) or {})
        pending_lines: List[str] = []
        for inter in interactions.values():
            status = getattr(inter, "status", None)
            if status not in ("pending", "active"):
                continue
            initiator = getattr(inter, "initiator", "")
            target = getattr(inter, "target", "")
            kind = getattr(inter, "kind", "")
            iid = getattr(inter, "id", "")
            # Show interactions the actor is involved in (either side)
            if actor_id not in (initiator, target):
                continue
            if kind == "task_request":
                data = getattr(inter, "data", {}) or {}
                tool = data.get("tool", "")
                args = data.get("args", {}) or {}
                pending_lines.append(f"- {kind} {iid}: {initiator} -> {target} wants {tool} {args} (status={status})")
            elif kind == "talk":
                pending_lines.append(f"- {kind} {iid}: {initiator} -> {target} (status={status})")
            else:
                pending_lines.append(f"- {kind} {iid}: {initiator} -> {target} (status={status})")
        facts.append("Pending interactions:")
        if pending_lines:
            for line in pending_lines:
                facts.append(f"  {line}")
        else:
            facts.append("  (none)")
    except Exception:
        pass

    # Tasks needed in current area (simple v0.4 heuristics)
    done = _completed_tasks(state)
    facts.append("Tasks needed here:")
    needed: List[str] = []
    if room_id == "living_room":
        if "clean_living_room" not in done:
            needed.append("clean_living_room")
    if room_id == "kitchen":
        if "wash_dishes" not in done:
            needed.append("wash_dishes")
        for food in ("egg", "bacon", "hotdog"):
            if f"cook:{food}" not in done:
                needed.append(f"cook {food}")

    def _label_task(task: str) -> str:
        key = "cook" if task.startswith("cook ") else task
        doers = TASK_DOERS.get(key, [])
        if doers and actor_id not in doers:
            return f"{task} (doable by: {', '.join(doers)})"
        return task

    if needed:
        for t in needed:
            facts.append(f"  - {_label_task(t)}")
    else:
        facts.append("  (none)")

    # Optional: available actions snapshot (helps explain what tools exist without dumping everything)
    if toolbox is not None:
        try:
            ctx = ActionContext(house=house, state=state, actor=actor_id)
            specs = toolbox.list_specs(ctx)
            names = [getattr(s, "name", "") for s in specs if getattr(s, "name", "")]
            if names:
                facts.append("Available actions now:")
                facts.append("  " + ", ".join(sorted(names)))
        except Exception:
            pass

    return facts


@dataclass
class PromptBundle:
    environment_name: str
    environment_rules: List[str]
    environment_facts: List[str]
    identity_role_append: str
    additional_policies: List[str]

    perception_facts: List[str]
    goals: List[str]
    working_memory: List[str]

    recalled_contexts: List[str]
    semantic_memory: List[str]

    def render(self) -> str:
        def block(title: str, body: str) -> str:
            return f"{title}\n{body}".rstrip()

        def bullets(items: List[str]) -> str:
            if not items:
                return "(blank)"
            return "\n".join(f"- {x}" for x in items)

        def lines(items: List[str]) -> str:
            if not items:
                return "(blank)"
            return "\n".join(items)

        parts: List[str] = []
        parts.append(block("environment_name:", str(self.environment_name)))
        parts.append(block("environment_rules:", bullets(self.environment_rules)))
        parts.append(block("environment_facts:", bullets(self.environment_facts)))
        parts.append(block("identity_role_append:", str(self.identity_role_append or "(blank)")))
        parts.append(block("additional_policies:", bullets(self.additional_policies)))
        parts.append(block("perception_facts:", lines(self.perception_facts)))
        parts.append(block("goals:", bullets(self.goals)))
        parts.append(block("working_memory (last 20):", bullets(self.working_memory)))
        parts.append(block("recalled_contexts:", "(blank)"))
        parts.append(block("semantic_memory:", "(blank)"))
        return "\n\n".join(parts)


def compile_prompt_bundle(
    *,
    actor_id: str,
    house: Any,
    state: Any,
    toolbox: Any | None = None,
) -> PromptBundle:
    world_cfg = load_world_prompt_config()
    goals_cfg = load_transient_goals()

    env_name = world_cfg.get("environment_name", "MicroBigBrother House")
    env_rules = list(world_cfg.get("environment_rules", []) or [])
    env_facts = list(world_cfg.get("environment_facts", []) or [])
    identity_append = world_cfg.get("identity_role_append", "") or ""
    add_policies = list(world_cfg.get("additional_policies", []) or [])

    perception = build_perception_facts(actor_id=actor_id, house=house, state=state, toolbox=toolbox)

    actor_goals = list(((goals_cfg.get(actor_id, {}) or {}).get("goals", []) or []))

    working = _summarize_last_events(state, n=20)

    return PromptBundle(
        environment_name=env_name,
        environment_rules=env_rules,
        environment_facts=env_facts,
        identity_role_append=identity_append,
        additional_policies=add_policies,
        perception_facts=perception,
        goals=actor_goals,
        working_memory=working,
        recalled_contexts=[],
        semantic_memory=[],
    )

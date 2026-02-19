from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Tuple, Any
from collections import deque

import yaml
from npcframework.api import Engine, Session, RuntimeConfig
from npcframework.npcframework_types import EngineConfig, TurnInput
from npcframework.tools.builtin import builtin_toolset


# -----------------------------
# Config
# -----------------------------

@dataclass(frozen=True)
class Paths:
    npc_dir: Path
    model_path: Path
    debug_dir: Path


@dataclass(frozen=True)
class ModelSettings:
    backend: str = "llamacpp"
    n_ctx: int = 8192
    n_threads: int = 8
    n_gpu_layers: int = 0
    temperature: float = 0.7
    top_p: float = 0.9
    max_tokens: int = 512


@dataclass(frozen=True)
class Tooling:
    allowlist: Tuple[str, ...] = ("time_now", "add")


# -----------------------------
# Turn builder (single source o
# -----------------------------
# Prompt composition (MicroBB)
# -----------------------------

_WORKING_MEMORY: deque[str] = deque(maxlen=5)
_CACHED_YAML: Dict[str, Any] = {}

def _project_root() -> Path:
    # HelloKevin.py lives in "LLM Engine/"; project root is its parent.
    return Path(__file__).resolve().parents[1]

def _load_yaml(path: Path) -> dict:
    key = str(path.resolve())
    if key in _CACHED_YAML:
        return _CACHED_YAML[key]
    if not path.exists():
        data = {}
    else:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    _CACHED_YAML[key] = data
    return data

def load_world_prompt_config() -> dict:
    """World-level prompt config stored under /World."""
    cfg_path = _project_root() / "World" / "world_prompt_config.yaml"
    return _load_yaml(cfg_path)

def load_transient_goals() -> dict:
    """Actor transient goals stored under /LLM Engine."""
    goals_path = _project_root() / "LLM Engine" / "transient_goals.yaml"
    return _load_yaml(goals_path)

def format_working_memory(lines: List[str]) -> List[str]:
    if not lines:
        return ["Working memory (last 5 turns): (none)"]
    out = ["Working memory (last 5 turns):"]
    out.extend([f"- {x}" for x in lines[-5:]])
    return out

def push_working_memory(line: str) -> None:
    if line:
        _WORKING_MEMORY.append(line)

def _summarize_last_events(state: Any, n: int = 5) -> List[str]:
    events = list(getattr(state, "events", []) or [])
    tail = events[-n:]
    out: List[str] = []
    for ev in tail:
        turn = getattr(ev, "turn", "?")
        actor = getattr(ev, "actor", "?")
        typ = getattr(ev, "type", "?")
        msg = getattr(ev, "message", "") or ""
        out.append(f"t={turn} {actor}: {typ} — {msg}".strip())
    return out

def _needed_tasks_for_actor(*, actor: str, house: Any, state: Any) -> List[str]:
    """Very small v0.4 'what needs doing' helper (one-time tasks)."""
    completed = set(getattr(state, "completed_tasks", frozenset()) or frozenset())
    loc = (getattr(state, "locations", {}) or {}).get(actor)
    needed: List[str] = []

    # Location-gated tasks
    if loc == "living_room" and "clean_living_room" not in completed:
        needed.append("clean_living_room (living_room)")
    if loc == "kitchen" and "wash_dishes" not in completed:
        needed.append("wash_dishes (kitchen)")

    # Cooking variants (only in kitchen)
    if loc == "kitchen":
        for food in ("egg", "bacon", "hotdog"):
            tid = f"cook:{food}"
            if tid not in completed:
                needed.append(f"cook {food} (kitchen)")

    return needed

def build_perception_facts(
    *,
    actor_id: str,
    house: Any | None = None,
    state: Any | None = None,
    toolbox: Any | None = None,
) -> List[str]:
    """Compose perception_facts: room details, adjacent rooms, needed tasks."""
    facts: List[str] = []

    if house is not None and state is not None:
        try:
            from World.perception import render_look
            look = render_look(house, state, actor_id)
            # render_look already includes room desc, objects, movable spaces, occupants.
            facts.extend([x.strip() for x in look.splitlines() if x.strip()])
        except Exception:
            # Keep it resilient; perception shouldn't crash the turn.
            loc = (getattr(state, "locations", {}) or {}).get(actor_id, "(unknown)")
            facts.append(f"Location: {loc}")

        # Adjacent rooms (explicit)
        loc = (getattr(state, "locations", {}) or {}).get(actor_id)
        if loc and getattr(house, "edges", None):
            adj = sorted(list((house.edges or {}).get(loc, set()) or []))
            facts.append("Rooms you can move into: " + (", ".join(adj) if adj else "(none)"))

        # Tasks needed (based on location + completion flags)
        needed = _needed_tasks_for_actor(actor=actor_id, house=house, state=state)
        if needed:
            facts.append("Tasks needed here:")
            facts.extend([f"- {t}" for t in needed])
        else:
            facts.append("Tasks needed here: (none)")

        # If toolbox exists, include currently available actions (useful for LLM tool selection)
        if toolbox is not None:
            try:
                from World.Tools.base import ActionContext
                ctx = ActionContext(house=house, state=state, actor=actor_id)
                specs = toolbox.list_specs(ctx)
                # Keep it compact: tool name only (args are in tool schema)
                tool_names = [getattr(s, "name", "") for s in specs if getattr(s, "name", "")]
                if tool_names:
                    facts.append("Available actions right now: " + ", ".join(sorted(set(tool_names))))
            except Exception:
                pass

    else:
        # Fallback if you haven't wired the environment yet
        facts.append("Room details: (not connected to MicroBB world state yet)")
        facts.append("Rooms you can move into: (unknown)")
        facts.append("Tasks needed here: (unknown)")
    return facts


# -----------------------------
# Composer bundle + preview
# -----------------------------

def build_working_memory(*, state: Any | None = None, n: int = 5) -> List[str]:
    """Working memory summary of last N turns (from events if available, else local buffer)."""
    if state is not None:
        return _summarize_last_events(state, n=n)
    return list(_WORKING_MEMORY)[-n:]


def compose_prompt_fields(
    *,
    actor_id: str,
    user_text: str,
    available_tools: List[dict],
    tool_handlers: Dict[str, Callable[..., Any]] | None = None,
    house: Any | None = None,
    state: Any | None = None,
    toolbox: Any | None = None,
) -> Dict[str, Any]:
    """Compose all sections that will be fed into NPCFramework for a given actor turn.

    Returns a plain dict so callers (e.g., player_cli) can preview without instantiating TurnInput.
    """
    world_cfg = load_world_prompt_config()
    goals_cfg = load_transient_goals()

    environment_name = world_cfg.get("environment_name", "MicroBigBrother House")
    environment_rules = list(world_cfg.get("environment_rules", []) or [])
    environment_facts = list(world_cfg.get("environment_facts", []) or [])
    identity_role_append = world_cfg.get("identity_role_append", "")
    additional_policies = list(world_cfg.get("additional_policies", []) or [])

    perception_facts = build_perception_facts(actor_id=actor_id, house=house, state=state, toolbox=toolbox)

    transient_goals = list((goals_cfg.get(actor_id, {}) or {}).get("goals", []) or [])

    working_memory = build_working_memory(state=state, n=5)

    return {
        "environment_name": environment_name,
        "environment_rules": environment_rules,
        "environment_facts": environment_facts,
        "identity_role_append": identity_role_append,
        "additional_policies": additional_policies,
        "perception_facts": perception_facts,
        "goals": transient_goals,
        "working_memory": working_memory,
        "recalled_contexts": [],  # blank for now
        "semantic_memory": [],    # blank for now

        # passthroughs
        "user_input": user_text,
        "available_tools": available_tools,
        "tool_handlers": tool_handlers or {},
    }


def render_prompt_preview(bundle: Dict[str, Any]) -> str:
    """Pretty print the composer output in the exact order expected by the operator."""
    def _bullets(items: List[str]) -> str:
        if not items:
            return "(blank)"
        return "\n".join([f"- {x}" for x in items])

    out: List[str] = []
    out.append("=== LLM Prompt Context (preview) ===")

    out.append(f"\nenvironment_name\n{bundle.get('environment_name','')}")

    out.append("\nenvironment_rules")
    out.append(_bullets(list(bundle.get("environment_rules", []) or [])))

    out.append("\nenvironment_facts")
    out.append(_bullets(list(bundle.get("environment_facts", []) or [])))

    out.append("\nidentity_role_append")
    ira = (bundle.get("identity_role_append", "") or "").strip()
    out.append(ira if ira else "(blank)")

    out.append("\nadditional_policies")
    out.append(_bullets(list(bundle.get("additional_policies", []) or [])))

    out.append("\nperception_facts")
    out.append(_bullets(list(bundle.get("perception_facts", []) or [])))

    out.append("\ngoals")
    out.append(_bullets(list(bundle.get("goals", []) or [])))

    out.append("\nworking memory (last 5 turns)")
    out.append(_bullets(list(bundle.get("working_memory", []) or [])))

    out.append("\nrecalled_contexts")
    out.append("(blank)")

    out.append("\nsemantic_memory")
    out.append("(blank)")

    out.append("\n=== end preview ===")
    return "\n".join(out) + "\n"


def build_turn(
    user_text: str,
    *,
    actor_id: str = "kevin",
    available_tools: List[dict],
    tool_handlers: Dict[str, Callable[..., Any]],
    house: Any | None = None,
    state: Any | None = None,
    toolbox: Any | None = None,
) -> TurnInput:
    """
    Build a TurnInput with MicroBB composer fields.

    Required sections (loaded/constructed per turn):
      - environment_name
      - environment_rules
      - environment_facts
      - identity_role_append
      - additional_policies
      - perception_facts (room/adjacent/tasks + working memory)
      - goals (actor transient goals)
      - recalled_contexts (blank for now)
      - semantic_memory (blank for now)
    """
    
    bundle = compose_prompt_fields(
        actor_id=actor_id,
        user_text=user_text,
        available_tools=available_tools,
        tool_handlers=tool_handlers,
        house=house,
        state=state,
        toolbox=toolbox,
    )

    # NPCFramework TurnInput doesn't have a dedicated working_memory field, so we append it
    # into perception_facts as an explicit block the model can read.
    wm_lines = list(bundle.get("working_memory", []) or [])
    if wm_lines:
        bundle["perception_facts"] = list(bundle.get("perception_facts", []) or []) + ["Working memory (last 5 turns):"] + [f"- {x}" for x in wm_lines]
    else:
        bundle["perception_facts"] = list(bundle.get("perception_facts", []) or []) + ["Working memory (last 5 turns): (none)"]

    return TurnInput(
        user_input=user_text,

        # ---- TOOLS ----
        allow_spontaneous_tools=False,
        available_tools=available_tools,
        tool_handlers=tool_handlers,
        include_tools_in_prompt=True,
        tool_prompt_style="compact",

        # ---- ENVIRONMENT ----
        environment_name=bundle['environment_name'],
        environment_facts=bundle['environment_facts'],
        environment_rules=bundle['environment_rules'],

        # ---- PERCEPTION ----
        perception_facts=bundle['perception_facts'],

        # ---- GOALS ----
        transient_goals=bundle['goals'],

        # ---- MEMORY ----
        semantic_memory=[],  # leave blank for now

        # ---- POLICY ----
        additional_policies=bundle['additional_policies'],

        # ---- IDENTITY APPEND ----
        identity_role_append=bundle['identity_role_append'],

        # ---- STATE ----
        external_state={
            "actor_id": actor_id,
        },
    )
# on helpers
# -----------------------------

def make_engine(model_path: Path, s: ModelSettings) -> Engine:
    return Engine(
        EngineConfig(
            backend=s.backend,
            model_path=str(model_path),
            n_ctx=s.n_ctx,
            n_threads=s.n_threads,
            n_gpu_layers=s.n_gpu_layers,
            temperature=s.temperature,
            top_p=s.top_p,
            max_tokens=s.max_tokens,
        )
    )


def make_runtime_cfg(debug_dir: Path) -> RuntimeConfig:
    return RuntimeConfig(
        debug_dump_messages_json=True,
        debug_dump_messages_txt=True,
        debug_dump_dir=str(debug_dir),
    )


def make_tooling(t: Tooling):
    return builtin_toolset(allowlist=list(t.allowlist))


def new_session(engine: Engine, npc_dir: Path, runtime_cfg: RuntimeConfig) -> Session:
    return Session(engine=engine, npc_dir=str(npc_dir), runtime_cfg=runtime_cfg)


# -----------------------------
# CLI loop
# -----------------------------
#REPL - Read, Eval, Print, Loop - Will guillotine whoever the hell called it like this first later
def repl(session: Session, *, available_tools, tool_handlers, engine: Engine, npc_dir: Path, runtime_cfg: RuntimeConfig) -> int:
    # Optional: prime/warm
    first = build_turn("Session started. Say something as a greeting.", available_tools=available_tools, tool_handlers=tool_handlers)
    result = session.run_turn(first)
    print(f"{result.npc_name} > {result.assistant_reply}")

    print("\nCommands: /quit, /reset")
    while True:
        try:
            user_text = input("\nYou > ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye.")
            return 0

        if not user_text:
            continue

        cmd = user_text.lower()
        if cmd in {"/q", "/quit", "exit"}:
            print("Bye.")
            return 0

        if cmd == "/reset":
            session = new_session(engine, npc_dir, runtime_cfg)
            print("Session reset. (Engine kept alive.)")
            continue

        turn = build_turn(user_text, available_tools=available_tools, tool_handlers=tool_handlers)
        result = session.run_turn(turn)

        if result.error:
            print(f"[error] {result.error}")
        else:
            print(f"{result.npc_name} > {result.assistant_reply}")


def main() -> int:
    # --- Change these 3 paths and you're good ---


    base = Path(r"C:\Users\Nitro\Desktop\NPCFramework")

    paths = Paths(
        npc_dir=base / "npc" / "kevin.npc",
        model_path=base / "npcframework" / "inference" / "models" / "Meta-Llama-3-8B-Instruct.Q4_K_M.gguf",
        debug_dir=base / ".npc" / "debug",
    )

    # Tools (keep tiny for now)
    available_tools, tool_handlers = make_tooling(Tooling())

    # Engine + runtime config
    engine = make_engine(paths.model_path, ModelSettings())
    runtime_cfg = make_runtime_cfg(paths.debug_dir)


    # Optional: quick sanity print
    import npcframework
    print("npcframework install:", npcframework.__file__)
    print("model path:", paths.model_path )

    # Session
    session = new_session(engine, paths.npc_dir, runtime_cfg)


    return repl(
        session,
        available_tools=available_tools,
        tool_handlers=tool_handlers,
        engine=engine,
        npc_dir=paths.npc_dir,
        runtime_cfg=runtime_cfg,
    )


if __name__ == "__main__":
    raise SystemExit(main())

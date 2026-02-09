from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Tuple, Any

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
# Turn builder (single source of truth)
# -----------------------------

def build_turn(
    user_text: str,
    *,
    available_tools: List[dict],
    tool_handlers: Dict[str, Callable[..., Any]],
    perception_facts: List[str] | None = None,
    environment_facts: List[str] | None = None,
    transient_goals: List[str] | None = None,
) -> TurnInput:
    """
    Build a TurnInput with MicroBB-ish scaffolding.
    Keep this as the single source of truth for per-turn defaults.

    Later: you can pass perception_facts/tools from your Environment layer.
    """
    perception_facts = perception_facts or [
        "You are in the living room.",
        "There is a couch, a coffee table, and a wall-mounted TV.",
    ]

    environment_facts = environment_facts or [
        "You are inside the MicroBigBrother house simulation.",
    ]

    transient_goals = transient_goals or [
        "Avoid rule-breaking and tool misuse.",
        "If the user asks for time/date/math, you MUST use tools; do not guess.",
    ]

    return TurnInput(
        user_input=user_text,

        # ---- TOOLS ----
        allow_spontaneous_tools=False,
        available_tools=available_tools,
        tool_handlers=tool_handlers,
        include_tools_in_prompt=True,
        tool_prompt_style="compact",

        # ---- ENVIRONMENT ----
        environment_name="MicroBigBrother House",
        environment_facts=environment_facts,
        environment_rules=[
            "Be consistent with your identity/persona/policy and the environment facts.",
        ],

        # ---- PERCEPTION ----
        perception_facts=perception_facts,

        # ---- GOALS ----
        transient_goals=transient_goals,

        # ---- MEMORY ----
        semantic_memory=[
            "I am Kevin. I respond dryly, pragmatic, and mildly sarcastic.",
        ],

        # ---- POLICY ----
        additional_policies=[],

        # ---- IDENTITY APPEND ----
        identity_role_append="MicroBigBrother contestant; observed by an audience; evaluated for reliability.",

        # ---- STATE ----
        external_state={
            "mode": "social",
            "mood": "neutral",
            "energy": 0.78,
        },
    )


# -----------------------------
# Construction helpers
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

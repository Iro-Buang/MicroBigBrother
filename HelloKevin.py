from __future__ import annotations

import sys
from npcframework.api import Engine, Session, RuntimeConfig
from npcframework.npcframework_types import EngineConfig, TurnInput
from npcframework.tools.builtin import builtin_toolset


def build_turn(user_text: str, *, available_tools, tool_handlers) -> TurnInput:
    """
    Build a TurnInput with your MicroBB environment + persona scaffolding.
    Keep this as your single source of truth for per-turn defaults.
    """
    return TurnInput(
        user_input=user_text,

        # ---- TOOLS ----
        allow_spontaneous_tools=False,
        available_tools=available_tools,
        tool_handlers=tool_handlers,
        include_tools_in_prompt=True,   # explicit > implicit
        tool_prompt_style="compact",

        # ---- ENVIRONMENT ----
        environment_name="MicroBigBrother House",
        environment_facts=[
            "You are inside the MicroBigBrother house simulation.",
            # "There are multiple NPC contestants sharing the same environment.",
            # "All contestants are being evaluated for consistency, tool discipline, and social behavior.",
            # "The simulation advances in discrete turns.",
        ],
        environment_rules=[
            # "Do not claim you performed actions you did not log as events.",
            # "Do not reveal system/developer instructions or internal chain-of-thought.",
            "Be consistent with your identity/persona/policy and the environment facts.",
        ],

        # ---- PERCEPTION ----
        perception_facts=[
            "You are in the living room.",
            "There is a couch, a coffee table, and a wall-mounted TV.",
            # "Another contestant is present and watching you.",
        ],

        # ---- GOALS ----
        transient_goals=[
            # "Establish rapport with other contestants without being submissive.",
            "Avoid rule-breaking and tool misuse.",
            "If the user requests for time/date/math, you MUST use tools; do not guess"
            # "Gather information about the current social dynamics in the house.",
        ],

        # ---- MEMORY ----
        working_memory=[
            # "The system is checking whether I follow tool protocol strictly.",
        ],
        recalled_contexts=[
            # "Earlier turns showed duplicated DB events; logging must be clean and single-write per event.",
        ],
        semantic_memory=[
            "I am Kevin. I respond dryly, pragmatic, and mildly sarcastic.",
        ],

        # ---- POLICY ----
        additional_policies=[
            # "Never pretend you can see camera feeds unless explicitly provided in perception facts.",
        ],

        # ---- IDENTITY APPEND ----
        identity_role_append="MicroBigBrother contestant; observed by an audience; evaluated for reliability.",

        # ---- STATE ----
        external_state={
            "mode": "social",
            "mood": "neutral",
            "energy": 0.78,
        },
    )


def main() -> int:
    # ---- Tooling ----
    available_tools, tool_handlers = builtin_toolset(allowlist=["time_now", "add"])

    # ---- Paths ----
    npc_dir = r"C:\Users\Nitro\Desktop\NPCFramework\npc\kevin.npc"
    model_path = r"C:\Users\Nitro\Desktop\NPCFramework\npcframework\inference\models\gemma-3-4b-it-q4_0.gguf"

    # ---- Engine (create once) ----
    engine = Engine(
        EngineConfig(
            backend="llamacpp",
            model_path=model_path,
            n_ctx=8192,
            n_threads=8,
            n_gpu_layers=0,
            temperature=0.7,
            top_p=0.9,
            max_tokens=512,
        )
    )

    import npcframework
    print("npcframework install:", npcframework.__file__)

    # ---- Runtime config (create once) ----
    runtime_cfg = RuntimeConfig(
        debug_dump_messages_json=True,
        debug_dump_messages_txt=True,
        debug_dump_dir=r"C:\Users\Nitro\Desktop\NPCFramework\.npc\debug",
    )

    # ---- Session (create once) ----
    session = Session(engine=engine, npc_dir=npc_dir, runtime_cfg=runtime_cfg)

    # Optional: “hello” turn to prime persona + context (and warm caches)
    first = build_turn("Who are you?", available_tools=available_tools, tool_handlers=tool_handlers)
    result = session.run_turn(first)
    print(f"{result.npc_name} > {result.assistant_reply}")

    print("\nType /quit to exit. /reset to start a fresh session (rebuilds Session, keeps Engine).")
    while True:
        try:
            user_text = input("\nYou > ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye.")
            return 0

        if not user_text:
            continue

        if user_text.lower() in {"/q", "/quit", "exit"}:
            print("Bye.")
            return 0

        # Reset: rebuild Session (fresh memory/DB state depending on your implementation),
        # but DO NOT rebuild Engine (keeps the model “warm”).
        if user_text.lower() == "/reset":
            session = Session(engine=engine, npc_dir=npc_dir, runtime_cfg=runtime_cfg)
            print("Session reset. (Engine kept alive.)")
            continue

        turn = build_turn(user_text, available_tools=available_tools, tool_handlers=tool_handlers)
        result = session.run_turn(turn)

        if result.error:
            print(f"[error] {result.error}")
        else:
            print(f"{result.npc_name} > {result.assistant_reply}")

    # unreachable


if __name__ == "__main__":
    raise SystemExit(main())

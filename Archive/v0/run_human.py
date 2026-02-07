# microbb/run_human.py
from __future__ import annotations

import json
import re
from typing import Any, Dict, Optional, Tuple

from house import default_house
from state import make_initial_state
from env import MicroBBEnv


TOOL_CALL_PREFIX = "/tool_call"


def parse_human_command(raw: str) -> Optional[Tuple[str, Dict[str, Any]]]:
    """
    Accepts multiple input styles so you don't fight the harness.

    Supported:
      - tools | obs | quit
      - skip | skip_turn
      - move_to kitchen
      - move_to(kitchen) / move_to('kitchen') / move_to("kitchen")
      - talk anna
      - talk_request(anna)
      - accept | accept_talk
      - reject | reject_talk
      - /tool_call {"name":"move_to","args":{"room":"kitchen"}}
    """
    raw = raw.strip()
    if not raw:
        return None

    cmd = raw.lower()

    # meta commands
    if cmd in {"quit", "exit"}:
        return ("quit", {})
    if cmd == "obs":
        return ("obs", {})
    if cmd == "tools":
        return ("tools", {})

    # skip
    if cmd in {"skip", "skip_turn"}:
        return ("skip_turn", {})

    # /tool_call JSON
    if raw.startswith(TOOL_CALL_PREFIX):
        payload = raw[len(TOOL_CALL_PREFIX):].strip()
        try:
            obj = json.loads(payload)
            name = obj["name"]
            args = obj.get("args", {}) or {}
            if not isinstance(args, dict):
                return ("unknown", {"raw": raw, "reason": "args must be an object/dict"})
            return (name, args)
        except Exception as e:
            return ("unknown", {"raw": raw, "reason": f"invalid /tool_call JSON: {e}"})

    # move_to kitchen
    if cmd.startswith("move_to "):
        room = raw.split(" ", 1)[1].strip()
        return ("move_to", {"room": room})

    # move_to(kitchen) or move_to('kitchen') or move_to("kitchen")
    m = re.match(r"""^move_to\(\s*['"]?([a-zA-Z_]+)['"]?\s*\)\s*$""", raw)
    if m:
        return ("move_to", {"room": m.group(1)})

    # talk anna
    if cmd.startswith("talk "):
        target = raw.split(" ", 1)[1].strip()
        return ("talk_request", {"target": target})

    # talk_request(anna)
    m = re.match(r"""^talk_request\(\s*['"]?([a-zA-Z_]+)['"]?\s*\)\s*$""", raw)
    if m:
        return ("talk_request", {"target": m.group(1)})

    # accept/reject
    if cmd in {"accept", "accept_talk"}:
        return ("accept_talk", {})
    if cmd in {"reject", "reject_talk"}:
        return ("reject_talk", {})

    return ("unknown", {"raw": raw})


def print_help():
    print(
        "\nCommands:\n"
        "  tools | obs | quit\n"
        "  skip | skip_turn\n"
        "  move_to kitchen\n"
        "  move_to(kitchen)  (also accepts quotes)\n"
        "  talk anna\n"
        "  talk_request(anna)\n"
        "  accept | reject\n"
        f"  {TOOL_CALL_PREFIX} {{\"name\":\"move_to\",\"args\":{{\"room\":\"kitchen\"}}}}\n"
    )


def main():
    house = default_house()
    state = make_initial_state()
    env = MicroBBEnv(house, state)

    actor = "kevin"  # you pilot Kevin first

    print("MicroBB Human Test. Type: tools to see actions. Type: quit to exit.")
    print_help()

    while True:
        print(f"\n--- TURN {env.state.turn_id} | You are {actor} ---")
        obs = env.get_observation(actor)
        for line in obs:
            print(" ", line)

        raw = input("\n> ").strip()
        parsed = parse_human_command(raw)

        if not parsed:
            continue

        action, args = parsed

        if action == "quit":
            break

        if action == "obs":
            continue

        if action == "tools":
            tools = env.get_allowed_actions(actor)
            for t in tools:
                print(f"- {t['name']}: {t['description']} | args_schema={t.get('args_schema')}")
            continue

        if action == "unknown":
            reason = args.get("reason")
            if reason:
                print(f"Unknown/invalid command: {args.get('raw')} ({reason})")
            else:
                print(f"Unknown command: {args.get('raw')}")
            print_help()
            continue

        # Apply action (same path NPCs will use later)
        res = env.apply_action(actor, action, args)
        print(("OK: " if res.ok else "NO: ") + res.message)

        # Alternate actor each turn to mimic two-agent turns
        actor = "anna" if actor == "kevin" else "kevin"
        env.end_turn()


if __name__ == "__main__":
    main()

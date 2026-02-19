# NPC/player_cli.py
import re
import importlib.util
from pathlib import Path

from World.house import default_house
from World.state import make_initial_state, current_actor
from World.engine import whereami
from World.perception import render_look
from World.Tools.factory import build_toolbox
from World.Tools.base import ActionContext
from World.interaction_engine import talk_say as _talk_say_engine, talk_end as _talk_end_engine


def _norm_token(s: str) -> str:
    """Normalize room/ids typed by humans: case-insensitive, allow spaces/hyphens."""
    s = s.strip().strip('"').strip("'")
    s = s.lower().replace(" ", "_").replace("-", "_")
    return s



# -----------------------------
# LLM prompt preview helpers
# -----------------------------

_HELLOKEVIN_MOD = None

def _load_hellokevin():
    """Dynamically load LLM Engine/HelloKevin.py without requiring it to be a package."""
    global _HELLOKEVIN_MOD
    if _HELLOKEVIN_MOD is not None:
        return _HELLOKEVIN_MOD

    hk_path = Path(__file__).resolve().parents[1] / "LLM Engine" / "HelloKevin.py"
    spec = importlib.util.spec_from_file_location("hellokevin", hk_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Failed to load HelloKevin.py from: {hk_path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[attr-defined]
    _HELLOKEVIN_MOD = mod
    return mod

def _specs_to_tools(specs, ctx):
    """Convert MicroBB tool specs into TurnInput available_tools format (compact)."""
    tools = []
    for s in specs:
        # keep it minimal; TurnInput just needs name/desc for prompt display
        desc = getattr(s, "doc", None) or getattr(s, "description", None) or ""
        tools.append({
            "name": s.name,
            "description": desc.strip(),
        })
    return tools

def _print_turninput_preview(turn):
    print("\n=== LLM Prompt Context (preview) ===")
    print(f"environment_name: {getattr(turn, 'environment_name', '')}")
    print("\nenvironment_rules:")
    for x in (getattr(turn, "environment_rules", []) or []):
        print(f"- {x}")
    print("\nenvironment_facts:")
    for x in (getattr(turn, "environment_facts", []) or []):
        print(f"- {x}")
    print("\nidentity_role_append:")
    ira = getattr(turn, "identity_role_append", "") or ""
    print(ira if ira.strip() else "(blank)")
    print("\nadditional_policies:")
    for x in (getattr(turn, "additional_policies", []) or []):
        print(f"- {x}")
    print("\nperception_facts:")
    for x in (getattr(turn, "perception_facts", []) or []):
        print(f"- {x}")
    print("\ngoals:")
    for x in (getattr(turn, "transient_goals", []) or []):
        print(f"- {x}")
    print("\nworking_memory:")
    # working memory is already appended into perception_facts as a block by composer
    print("(included above in perception_facts)")
    print("\nrecalled_contexts: (blank)")
    print("semantic_memory: (blank)")
    print("=== end preview ===\n")
def _active_talk_for(state, actor: str):
    for iid, inter in (getattr(state, "interactions", {}) or {}).items():
        if inter.kind == "talk" and inter.status == "active" and actor in (inter.initiator, inter.target):
            return iid, inter
    return None, None


def _run_conversation_window(house, toolbox, state, *, interaction_id: str):
    """A short, non-turn-based convo sub-loop.

    - Alternates speakers automatically.
    - Does NOT advance global turns per utterance.
    - Ends when max exchanges reached, participants separate, or someone ends it.
    """
    iid = interaction_id
    inter = (state.interactions or {}).get(iid)
    if not inter or inter.kind != "talk" or inter.status != "active":
        return state

    # requester (initiator) speaks first by default
    speaker = inter.initiator

    def exchange_label(cur_state):
        cur = (cur_state.interactions or {}).get(iid)
        if not cur:
            return "?"
        # 3 exchanges total == 6 utterances total
        # exchange index is floor(utterances/2)
        ex = cur.utterances // 2
        return f"{ex}/{cur.max_exchanges}"

    print(f"\n--- Conversation started ({iid}) {inter.initiator} <-> {inter.target} ---")
    # Make it hard to accidentally end a convo when you *meant* to say "end".
    # Commands are slash-prefixed; bare text is treated as speech.
    print("Type: say <text> | /end | /quit | help")

    while True:
        # refresh current interaction
        cur = (state.interactions or {}).get(iid)
        if not cur or cur.status != "active":
            print("--- Conversation ended ---\n")
            return state

        # if separated, auto-end will be handled on say, but we can hint early
        room_ok = state.locations.get(cur.initiator) == cur.room_id and state.locations.get(cur.target) == cur.room_id
        if not room_ok:
            # force close (mirrors engine behavior)
            state, res = _talk_end_engine(state, who=speaker, interaction_id=iid)
            print(res.message)
            continue

        prompt = f"[talk {iid} ex={exchange_label(state)}] {speaker}> "
        raw = input(prompt).strip()

        if raw in ("/quit", "/exit", "/quit_convo", "/exit_convo"):
            state, res = _talk_end_engine(state, who=speaker, interaction_id=iid)
            print(res.message)
            continue

        if raw in ("help", "?", "/help"):
            print("say <text>   -> speak as the current speaker")
            print("/end         -> end the conversation")
            print("/quit        -> end the conversation (alias for /end)")
            continue

        if raw == "/end":
            state, res = _talk_end_engine(state, who=speaker, interaction_id=iid)
            print(res.message)
            continue

        # Allow bare text as shorthand for say
        if raw.startswith("say "):
            text = raw[4:].strip()
        else:
            text = raw

        if not text:
            print("(empty)" )
            continue

        # Speak
        state, res = _talk_say_engine(state, who=speaker, interaction_id=iid, text=text)
        print(res.message)

        # Toggle speaker if still active
        cur2 = (state.interactions or {}).get(iid)
        if cur2 and cur2.status == "active":
            speaker = cur2.target if speaker == cur2.initiator else cur2.initiator



HELP = """Commands:
  look
  whereami
  who
  actions
  prompt   # show the composed LLM prompt context for the current actor
  move_to <room>
  unlock <room>
  lock <room>
  end_turn | skip

  # Tasks (Anna)
  clean_living_room
  wash_dishes
  cook <egg|bacon|hotdog>
  guess <task_id>

  # Task requests (Kevin -> Anna)
  request_anna <clean_living_room|wash_dishes|cook|move_to> [arg]
    - cook requires: egg|bacon|hotdog
    - move_to requires: <room>

  # Anna responses to task requests
  task_accept [interaction_id|kevin]
  task_reject [interaction_id|kevin]

  # Talk system
  talk_request <target>
  talk_accept [interaction_id|initiator]
  talk_decline [interaction_id|initiator]
  talk_say <interaction_id> <text>
  talk_end [interaction_id]

  events
  state
  help
  quit

Debug:
  control <entity>   # overrides turn rotation
  control auto       # return to turn-based control
"""

MAX_TURNS = 25

def _compute_scores(state):
    """Scoreboard rules:

    - Kevin score: number of completed tasks in the house.
    - Anna score: number of *correct* guesses.
    - Tie-break: Kevin wins by default.
    """
    tasks_done = len(getattr(state, "completed_tasks", []) or [])
    correct_guesses = 0
    for ev in (getattr(state, "events", []) or []):
        if getattr(ev, "type", None) != "guess":
            continue
        args = getattr(ev, "args", {}) or {}
        if bool(args.get("correct")):
            correct_guesses += 1
    return {
        "kevin": int(tasks_done),
        "anna": int(correct_guesses),
        "tasks_done": int(tasks_done),
        "correct_guesses": int(correct_guesses),
    }


def _print_scoreboard(state):
    s = _compute_scores(state)
    kevin = s["kevin"]
    anna = s["anna"]
    winner = "kevin" if kevin >= anna else "anna"  # Kevin wins ties.

    print("\n=== SCOREBOARD ===")
    print(f"Kevin score (tasks completed): {kevin}")
    print(f"Anna score (correct guesses):  {anna}")
    print("------------------")
    print(f"Winner: {winner.upper()} (tie -> KEVIN)")
    print("==================\n")

def main():
    house = default_house()
    state = make_initial_state()
    toolbox = build_toolbox()

    debug_controlled = None  # debug override only

    print("You are the operator.")
    print(HELP)

    while True:
        # Hard stop so the sim doesn't run forever.
        if state.turn >= MAX_TURNS:
            print(f"Simulation ended: reached max turns ({MAX_TURNS}).")
            _print_scoreboard(state)
            break

        controlled = debug_controlled or current_actor(state)
        loc = state.locations.get(controlled, "???")
        cmd = input(f"[{controlled}@{loc} t={state.turn}] > ").strip()

        # If you're in an active talk, most world actions are blocked unless you
        # explicitly use the conversation window or talk_* tools.
        active_iid, _ = _active_talk_for(state, controlled)

        # ---------- non-tool commands ----------

        if cmd in ("quit", "exit"):
            print("bye")
            _print_scoreboard(state)
            break

        if cmd in ("help", "?"):
            print(HELP)
            continue

        if cmd == "who":
            base = current_actor(state)
            if debug_controlled:
                print(f"Turn actor: {base} | Controlling (DEBUG): {debug_controlled}")
            else:
                print(f"Turn actor: {base} | Controlling: {base}")
            continue

        if cmd == "whereami":
            print(whereami(state, controlled))
            continue

        if cmd == "state":
            print(state)
            continue

        if cmd == "events":
            evs = list(getattr(state, "events", []) or [])
            if not evs:
                print("(no events)")
            else:
                # show last 25
                for ev in evs[-25:]:
                    print(f"[{ev.turn}] {ev.actor} {ev.type} ok={ev.ok} {ev.message}")
            continue

        if cmd == "prompt":
            try:
                from World.prompt_compiler import compile_prompt_bundle
                bundle = compile_prompt_bundle(actor_id=controlled, house=house, state=state, toolbox=toolbox)
                print(bundle.render())
            except Exception as e:
                print(f"Failed to build prompt preview: {e}")
            continue


        # ---------- look (read-only, no tool) ----------

        if cmd == "look":
            print(render_look(house, state, controlled))
            continue

        # ---------- TOOL INVOCATION PATH ----------

        ctx = ActionContext(house=house, state=state, actor=controlled)

        # Normalize common "human" room typing (case/space tolerant)
        m = re.match(r"^(move_to)\s+(.+)$", cmd)
        if m:
            if active_iid:
                print("Blocked: you are in an active conversation. Use talk_say/talk_end or enter the convo window.")
                continue
            dst = _norm_token(m.group(2))
            ctx, res = toolbox.invoke(m.group(1), ctx, {"dst": dst})
            state = ctx.state
            print(res.message)
            continue

        m = re.match(r"^(lock|unlock)\s+(.+)$", cmd)
        if m:
            if active_iid:
                print("Blocked: you are in an active conversation.")
                continue
            room_id = _norm_token(m.group(2))
            ctx, res = toolbox.invoke(m.group(1), ctx, {"room_id": room_id})
            state = ctx.state
            print(res.message)
            continue

        m = re.match(r"^(talk_request)\s+(.+)$", cmd)
        if m:
            if active_iid:
                print("Blocked: you are already in an active conversation.")
                continue
            target = _norm_token(m.group(2))
            ctx, res = toolbox.invoke(m.group(1), ctx, {"target": target})
            state = ctx.state
            print(res.message)
            continue

        m = re.match(r"^(talk_accept|talk_decline)\s+(.+)$", cmd)
        if m:
            token = _norm_token(m.group(2))
            # Allow: talk_accept kevin  (accept the pending request FROM kevin)
            if not re.match(r"^i\d+$", token):
                pending = [
                    iid for iid, inter in (state.interactions or {}).items()
                    if inter.kind == "talk" and inter.status == "pending" and inter.target == controlled and inter.initiator == token
                ]
                if not pending:
                    print(f"No pending talk requests from: {token}")
                    continue
                if len(pending) > 1:
                    # Should not happen due to de-dup rules, but be safe.
                    print("Multiple pending talk requests from that actor. Specify one of: " + ", ".join(pending))
                    continue
                token = pending[0]

            ctx, res = toolbox.invoke(m.group(1), ctx, {"interaction_id": token})
            state = ctx.state
            print(res.message)
            # If we just started a talk, drop into the convo window.
            if m.group(1) == "talk_accept" and res.ok:
                iid = token
                state = _run_conversation_window(house, toolbox, state, interaction_id=iid)
            continue

        # Convenience: if there's exactly one pending talk request directed at you,
        # allow `talk_accept` / `talk_decline` without specifying the interaction id.
        m = re.match(r"^(talk_accept|talk_decline)$", cmd)
        if m:
            # Find pending interactions directed at the current actor
            pending = [
                iid for iid, inter in (state.interactions or {}).items()
                if inter.kind == "talk" and inter.status == "pending" and inter.target == controlled
            ]
            if not pending:
                print("No pending talk requests directed at you.")
                continue
            if len(pending) > 1:
                print("Multiple pending talk requests. Specify one of: " + ", ".join(pending))
                continue
            iid = pending[0]
            ctx, res = toolbox.invoke(m.group(1), ctx, {"interaction_id": iid})
            state = ctx.state
            print(res.message)
            if m.group(1) == "talk_accept" and res.ok:
                state = _run_conversation_window(house, toolbox, state, interaction_id=iid)
            continue

        # talk_say:
        #   - talk_say <interaction_id> <text>
        #   - talk_say <text>            (if you're in exactly one active talk)
        m = re.match(r"^(talk_say)\s+(i\d+)\s+(.+)$", cmd)
        if m:
            text = m.group(3).strip()
            # strip simple surrounding quotes
            if (text.startswith('"') and text.endswith('"')) or (text.startswith("\'") and text.endswith("\'")):
                text = text[1:-1]
            ctx, res = toolbox.invoke(m.group(1), ctx, {"interaction_id": m.group(2), "text": text})
            state = ctx.state
            print(res.message)
            continue

        m = re.match(r"^(talk_say)\s+(.+)$", cmd)
        if m:
            text = m.group(2).strip()
            # If user accidentally typed just an interaction id, guide them.
            if re.match(r"^i\d+$", text):
                print("Usage: talk_say <interaction_id> <text>  (or: talk_say <text> if you\'re in one active talk)")
                continue

            active = [
                iid for iid, inter in (state.interactions or {}).items()
                if inter.kind == "talk" and inter.status == "active" and controlled in (inter.initiator, inter.target)
            ]
            if not active:
                print("You are not in an active talk. Use: talk_request <target> then talk_accept.")
                continue
            if len(active) > 1:
                print("Multiple active talks. Specify one of: " + ", ".join(active))
                continue

            if (text.startswith('"') and text.endswith('"')) or (text.startswith("\'") and text.endswith("\'")):
                text = text[1:-1]
            ctx, res = toolbox.invoke("talk_say", ctx, {"interaction_id": active[0], "text": text})
            state = ctx.state
            print(res.message)
            continue

        m = re.match(r"^(talk_end)\s+(\w+)$", cmd)
        if m:
            ctx, res = toolbox.invoke(m.group(1), ctx, {"interaction_id": m.group(2)})
            state = ctx.state
            print(res.message)
            continue

        # Convenience: if there's exactly one active talk you're part of,
        # allow `talk_end` without specifying the interaction id.
        m = re.match(r"^(talk_end)$", cmd)
        if m:
            active = [
                iid for iid, inter in (state.interactions or {}).items()
                if inter.kind == "talk" and inter.status == "active" and controlled in (inter.initiator, inter.target)
            ]
            if not active:
                print("You are not in an active talk.")
                continue
            if len(active) > 1:
                print("Multiple active talks. Specify one of: " + ", ".join(active))
                continue
            iid = active[0]
            ctx, res = toolbox.invoke(m.group(1), ctx, {"interaction_id": iid})
            state = ctx.state
            print(res.message)
            continue


        # ---------- TASK / TASK REQUESTS ----------

        # Anna-only task shortcuts
        if cmd in ("clean_living_room", "wash_dishes", "cook", "guess", "task_accept", "task_reject"):
            pass  # fall through to regex handlers below

        # clean_living_room / wash_dishes (no args)
        m = re.match(r"^(clean_living_room|wash_dishes)$", cmd)
        if m:
            if active_iid:
                print("Blocked: you are in an active conversation.")
                continue
            ctx, res = toolbox.invoke(m.group(1), ctx, {})
            state = ctx.state
            print(res.message)
            continue

        # cook <food>
        m = re.match(r"^(cook)\s+(.+)$", cmd)
        if m:
            if active_iid:
                print("Blocked: you are in an active conversation.")
                continue
            food = _norm_token(m.group(2))
            ctx, res = toolbox.invoke("cook", ctx, {"food": food})
            state = ctx.state
            print(res.message)
            continue

        # guess <task_id>
        m = re.match(r"^(guess)\s+(.+)$", cmd)
        if m:
            if active_iid:
                print("Blocked: you are in an active conversation.")
                continue
            task_id = _norm_token(m.group(2))
            ctx, res = toolbox.invoke("guess", ctx, {"task_id": task_id})
            state = ctx.state
            print(res.message)
            continue

        # Kevin: request_anna <tool> [arg]
        # Examples:
        #   request_anna clean_living_room
        #   request_anna wash_dishes
        #   request_anna cook egg
        #   request_anna move_to kitchen
        m = re.match(r"^(request_anna)\s+(\w+)(?:\s+(.+))?$", cmd)
        if m:
            if active_iid:
                print("Blocked: you are in an active conversation.")
                continue
            tool = _norm_token(m.group(2))
            raw_arg = m.group(3).strip() if m.group(3) else ""
            args = {}
            if tool == "cook":
                if not raw_arg:
                    print("Usage: request_anna cook <egg|bacon|hotdog>")
                    continue
                args = {"food": _norm_token(raw_arg)}
            elif tool == "move_to":
                if not raw_arg:
                    print("Usage: request_anna move_to <room>")
                    continue
                args = {"dst": _norm_token(raw_arg)}
            elif raw_arg:
                # Unknown extra argument; keep it strict to avoid silent errors.
                print(f"Usage: request_anna {tool}   (no extra args expected)")
                continue

            ctx, res = toolbox.invoke("request_anna", ctx, {"tool": tool, "args": args})
            state = ctx.state
            print(res.message)
            continue

        # Anna: task_accept / task_reject [interaction_id|kevin]
        m = re.match(r"^(task_accept|task_reject)\s+(.+)$", cmd)
        if m:
            if active_iid:
                print("Blocked: you are in an active conversation.")
                continue
            token = _norm_token(m.group(2))
            # Allow: task_accept kevin  (accept the pending task request FROM kevin)
            if not re.match(r"^i\d+$", token):
                pending = [
                    iid for iid, inter in (state.interactions or {}).items()
                    if inter.kind == "task_request" and inter.status == "pending" and inter.target == controlled and inter.initiator == token
                ]
                if not pending:
                    print(f"No pending task requests from: {token}")
                    continue
                if len(pending) > 1:
                    print("Multiple pending task requests from that actor. Specify one of: " + ", ".join(pending))
                    continue
                token = pending[0]

            ctx, res = toolbox.invoke(m.group(1), ctx, {"interaction_id": token})
            state = ctx.state
            print(res.message)
            continue

        # Convenience: if there's exactly one pending task request directed at you,
        # allow `task_accept` / `task_reject` without specifying the interaction id.
        m = re.match(r"^(task_accept|task_reject)$", cmd)
        if m:
            pending = [
                iid for iid, inter in (state.interactions or {}).items()
                if inter.kind == "task_request" and inter.status == "pending" and inter.target == controlled
            ]
            if not pending:
                print("No pending task requests directed at you.")
                continue
            if len(pending) > 1:
                print("Multiple pending task requests. Specify one of: " + ", ".join(pending))
                continue
            iid = pending[0]
            ctx, res = toolbox.invoke(m.group(1), ctx, {"interaction_id": iid})
            state = ctx.state
            print(res.message)
            continue
        if cmd in ("end_turn", "skip"):
            tool_name = "skip" if cmd == "skip" else "end_turn"
            ctx, res = toolbox.invoke(tool_name, ctx, {})
            state = ctx.state
            print(res.message)
            continue

        if cmd == "actions":
            ctx = ActionContext(house=house, state=state, actor=controlled)
            specs = toolbox.list_specs(ctx)

            for spec in specs:
                # if tool provides dynamic choices, print them
                choices = spec.choices(ctx) if spec.choices else {}
                if choices:
                    # UX sugar: show talk accept/decline options as actor names, not opaque ids.
                    if spec.name in ("talk_accept", "talk_decline") and "interaction_id" in choices:
                        iids = choices.get("interaction_id") or []
                        names = []
                        for iid in iids:
                            inter = (state.interactions or {}).get(iid)
                            if inter and getattr(inter, "initiator", None):
                                names.append(inter.initiator)
                        if names:
                            sig = "from=" + "|".join(sorted(set(names)))
                            print(f"- {spec.name}({sig})")
                        else:
                            print(f"- {spec.name}(from=(none))")
                        print(f"    {spec.description}")
                        continue

                    parts = []
                    for arg, opts in choices.items():
                        if opts:
                            parts.append(f"{arg}=" + "|".join(opts))
                        else:
                            parts.append(f"{arg}=(none)")
                    sig = ", ".join(parts)
                    print(f"- {spec.name}({sig})")
                else:
                    args = ", ".join(spec.args_schema.keys())
                    print(f"- {spec.name}({args})")

                print(f"    {spec.description}")
            continue

        # ---------- DEBUG CONTROL ----------

        if cmd == "control auto":
            debug_controlled = None
            print("OK: returned to turn-based control.")
            continue

        m = re.match(r"^control\s+(\w+)$", cmd)
        if m:
            target = m.group(1)
            if target not in state.locations:
                print(f"Unknown entity: {target}")
            else:
                debug_controlled = target
                print(f"OK: DEBUG controlling {debug_controlled} (turn rotation overridden).")
            continue

        print("Unknown command. Type 'help'.")


if __name__ == "__main__":
    main()
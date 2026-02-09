# NPC/player_cli.py
import re

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
    # quit_convo is treated as an explicit end (users expect it to actually quit).
    print("Type: say <text> | end | help | quit_convo")

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

        if raw in ("quit_convo", "exit_convo"):
            # Users expect "quit" to end the convo, not just hide the window.
            state, res = _talk_end_engine(state, who=speaker, interaction_id=iid)
            print(res.message)
            continue

        if raw in ("help", "?"):
            print("say <text>   -> speak as the current speaker")
            print("end          -> end the conversation")
            print("quit_convo   -> end the conversation (alias for end)")
            continue

        if raw == "end":
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
  move_to <room>
  unlock <room>
  lock <room>
  end_turn | skip
  talk_request <target>
  talk_accept <interaction_id>
  talk_decline <interaction_id>
  talk_say <interaction_id> <text>
  talk_end <interaction_id>
  events
  state
  help
  quit

Debug:
  control <entity>   # overrides turn rotation
  control auto       # return to turn-based control
"""

def main():
    house = default_house()
    state = make_initial_state()
    toolbox = build_toolbox()

    debug_controlled = None  # debug override only

    print("You are the operator.")
    print(HELP)

    while True:
        controlled = debug_controlled or current_actor(state)
        loc = state.locations.get(controlled, "???")
        cmd = input(f"[{controlled}@{loc} t={state.turn}] > ").strip()

        # If you're in an active talk, most world actions are blocked unless you
        # explicitly use the conversation window or talk_* tools.
        active_iid, _ = _active_talk_for(state, controlled)

        # ---------- non-tool commands ----------

        if cmd in ("quit", "exit"):
            print("bye")
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

        if cmd in ("end_turn", "skip"):
            ctx, res = toolbox.invoke("end_turn", ctx, {})
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

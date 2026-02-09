# NPC/player_cli.py
import re

from World.house import default_house
from World.state import make_initial_state, current_actor
from World.engine import whereami, entities_in_room
from World.Tools.factory import build_toolbox
from World.Tools.base import ActionContext


HELP = """Commands:
  look
  whereami
  who
  actions
  move_to <room>
  unlock <room>
  lock <room>
  end_turn | skip
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

        # ---------- look (read-only, no tool) ----------

        if cmd == "look":
            room_id = whereami(state, controlled)
            room = house.rooms[room_id]

            movable = sorted(house.edges.get(room_id, set()))
            known = sorted(house.rooms.keys())
            occupants = entities_in_room(state, room_id)

            print(f"{room.name} ({room.id})")

            locked = state.room_locked.get(room.id) if getattr(state, "room_locked", None) else None
            if locked is True:
                print("Room state: LOCKED")
            elif locked is False:
                print("Room state: unlocked")

            print(room.description)

            if room.objects:
                print("Notable objects: " + ", ".join(room.objects))

            print("Movable spaces: " + (", ".join(movable) if movable else "(none)"))
            print("Known spaces: " + ", ".join(known))

            others = [e for e in occupants if e != controlled]
            if others:
                print("Also here: " + ", ".join(others))
            else:
                print("You are alone.")
            continue

        # ---------- TOOL INVOCATION PATH ----------

        ctx = ActionContext(house=house, state=state, actor=controlled)

        m = re.match(r"^(move_to)\s+(\w+)$", cmd)
        if m:
            ctx, res = toolbox.invoke(m.group(1), ctx, {"dst": m.group(2)})
            state = ctx.state
            print(res.message)
            continue

        m = re.match(r"^(lock|unlock)\s+(\w+)$", cmd)
        if m:
            ctx, res = toolbox.invoke(m.group(1), ctx, {"room_id": m.group(2)})
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

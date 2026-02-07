# NPC/player_cli.py
import re

from World.house import default_house
from World.state import make_initial_state, current_actor
from World.engine import apply_move, whereami, entities_in_room, end_turn, unlock_room, lock_room


HELP = """Commands:
  look
  whereami
  who
  move_to <room>
  unlock <room>
  lock <room>
  end_turn
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

    debug_controlled = None  # if set, overrides turn rotation

    print("You are the operator.")
    print(HELP)

    while True:
        controlled = debug_controlled or current_actor(state)
        loc = state.locations.get(controlled, "???")
        cmd = input(f"[{controlled}@{loc} t={state.turn}] > ").strip()

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

        if cmd == "look":
            room_id = whereami(state, controlled)
            room = house.rooms[room_id]

            movable = sorted(house.edges.get(room_id, set()))
            known = sorted(house.rooms.keys())
            occupants = entities_in_room(state, room_id)

            print(f"{room.name} ({room.id})")

            locked = state.room_locked.get(room.id, None) if getattr(state, "room_locked", None) else None
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
            if not others:
                print("You are alone.")
            else:
                print("Also here: " + ", ".join(others))
            continue

        # --- actions that can advance the turn (engine decides) ---

        m = re.match(r"^move_to\s+([a-zA-Z0-9_]+)$", cmd)
        if m:
            dst = m.group(1)
            state, res = apply_move(house, state, controlled, dst)
            print(res.message)
            continue

        m = re.match(r"^unlock\s+([a-zA-Z0-9_]+)$", cmd)
        if m:
            room_id = m.group(1)
            state, res = unlock_room(house, state, controlled, room_id)
            print(res.message)
            continue

        m = re.match(r"^lock\s+([a-zA-Z0-9_]+)$", cmd)
        if m:
            room_id = m.group(1)
            state, res = lock_room(house, state, controlled, room_id)
            print(res.message)
            continue

        if cmd == "end_turn":
            state, res = end_turn(state)
            print(res.message)
            continue

        if cmd == "state":
            print(state)
            continue

        # --- debug control override ---
        if cmd == "control auto":
            debug_controlled = None
            print("OK: returned to turn-based control.")
            continue

        m = re.match(r"^control\s+([a-zA-Z0-9_]+)$", cmd)
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

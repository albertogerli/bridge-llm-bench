"""
Interactive bridge card play: user plays one seat, LLM plays the other 3.

Information hiding is strictly enforced — you only see your own cards
and dummy (after the opening lead). LLM players also see only what
they're allowed to.

Usage:
    # Play as South with default LLM
    python scripts/play_interactive.py --seat S

    # Play a specific deal
    python scripts/play_interactive.py --seat S --deal 0

    # Choose LLM model
    python scripts/play_interactive.py --seat S --model gemini-3.1-flash-lite-preview
"""

import argparse
import os
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bridge_llm_bench.play.data import load_play_records
from bridge_llm_bench.play.engine import (
    PlayEngine, PlayResult,
    make_llm_player, make_human_player, make_dd_player,
    _is_declarer_side, _format_hand_display,
)
from bridge_llm_bench.play.prompts import play_prompt, parse_card_from_response
from bridge_llm_bench.metrics.dd_scoring import contract_score, imp_diff

_root = Path(__file__).resolve().parent.parent
DATA_PATH = _root / "data" / "open_spiel" / "test.txt"
DD_CACHE = _root / "data" / "dd_tables_play.json"

# Auto-load .env
_env_file = _root / ".env"
if _env_file.exists():
    for line in _env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            key, val = line.split('=', 1)
            os.environ.setdefault(key.strip(), val.strip())

SEATS = ["N", "E", "S", "W"]
SEAT_NAMES = {"N": "North", "E": "East", "S": "South", "W": "West"}


def play_interactive(args):
    """Main interactive play loop."""
    user_seat = args.seat.upper()

    # Load deals
    print("Loading deals...")
    records = load_play_records(
        str(DATA_PATH),
        n_games=args.pool_size,
        compute_dd=True,
        dd_cache_path=str(DD_CACHE),
    )
    print(f"  {len(records)} deals loaded.\n")

    # Set up LLM client for opponents
    if args.player == "llm":
        from bridge_llm_bench.clients import get_client
        client = get_client(args.model, temperature=0.0)
    else:
        client = None

    imp_running = 0
    deals_played = 0

    while True:
        # Pick a deal
        if args.deal is not None and deals_played == 0:
            # Find deal by index
            matching = [r for r in records if r.deal_id == args.deal]
            if not matching:
                matching = [records[min(args.deal, len(records) - 1)]]
            record = matching[0]
        else:
            record = random.choice(records)

        deals_played += 1
        print(f"\n{'='*60}")
        print(f"  DEAL #{deals_played} (id={record.deal_id})")
        print(f"{'='*60}")

        # Show auction
        print(f"\n  Dealer: {SEAT_NAMES[SEATS[record.dealer]]}")
        print(f"  Auction: {' '.join(record.auction)}")
        print(f"  Contract: {record.contract_str}")
        print(f"  You are {SEAT_NAMES[user_seat]} ({user_seat})")

        declarer = record.declarer_seat
        dummy = record.dummy_seat
        is_user_declarer = (user_seat == declarer)
        is_user_dummy = (user_seat == dummy)

        if is_user_dummy:
            print("  You are dummy! Declarer plays your cards. Watching...")

        partner = SEATS[(SEATS.index(user_seat) + 2) % 4]
        print(f"  Partner: {SEAT_NAMES[partner]} ({partner})")
        user_side = "NS" if user_seat in ("N", "S") else "EW"

        # Show user's hand
        print(f"\n  Your hand: {_format_hand_display(record.hands[user_seat])}")

        # Build player function
        human = make_human_player()
        if args.player == "llm":
            llm = make_llm_player(client, args.model, play_prompt, parse_card_from_response)
        else:
            llm = make_dd_player()

        def interactive_player(seat, vs, legal_moves, is_from_dummy):
            """Route to human or LLM based on seat."""
            acting_seat = declarer if is_from_dummy else seat

            if acting_seat == user_seat:
                return human(seat, vs, legal_moves, is_from_dummy)
            else:
                # LLM plays
                card = llm(seat, vs, legal_moves, is_from_dummy)
                label = f"{'Dummy' if is_from_dummy else SEAT_NAMES[seat]}"
                print(f"  {label} plays: {card}")
                return card

        # Play the deal
        engine = PlayEngine(record)
        result = engine.play_deal(interactive_player)

        # Show result
        print(f"\n{'='*60}")
        print(f"  RESULT")
        print(f"{'='*60}")

        decl_tricks = result.tricks_won_ns if declarer in ("N", "S") else result.tricks_won_ew
        needed = record.contract[0] + 6
        made = decl_tricks >= needed

        print(f"  Contract: {record.contract_str}")
        print(f"  Tricks: Declarer {decl_tricks}, Defense {13 - decl_tricks}")
        if made:
            overtricks = decl_tricks - needed
            ot_str = f" +{overtricks}" if overtricks > 0 else ""
            print(f"  MADE{ot_str}! Score: {result.contract_score_actual}")
        else:
            down = needed - decl_tricks
            print(f"  DOWN {down}. Score: {result.contract_score_actual}")

        # DD comparison
        dd_key = f"{record.contract[1]}_{declarer}"
        dd_tricks = record.dd_table.get(dd_key, "?")
        print(f"\n  DD optimal: {dd_tricks} tricks (score: {result.contract_score_dd})")
        print(f"  IMP difference: {result.imp_diff_vs_dd:+d}")

        # Mistake summary
        if result.n_declarer_mistakes or result.n_defense_mistakes:
            print(f"  Mistakes: Declarer={result.n_declarer_mistakes}, Defense={result.n_defense_mistakes}")

        # User IMP accounting
        # From user's perspective: positive = user did well
        if _is_declarer_side(user_seat, declarer):
            user_imp = result.imp_diff_vs_dd
        else:
            user_imp = -result.imp_diff_vs_dd

        imp_running += user_imp
        print(f"\n  Your IMPs this deal: {user_imp:+d}")
        print(f"  Running total: {imp_running:+d} IMPs over {deals_played} deals "
              f"({imp_running/deals_played:+.1f}/deal)")

        # Play again?
        print()
        again = input("  Play another deal? (y/n): ").strip().lower()
        if again != "y":
            break

    print(f"\n  Final: {imp_running:+d} IMPs over {deals_played} deals. "
          f"Avg: {imp_running/deals_played:+.1f}/deal")
    print("  Thanks for playing!\n")


def main():
    parser = argparse.ArgumentParser(description="Interactive bridge card play")
    parser.add_argument("--seat", type=str, required=True, choices=["N", "E", "S", "W"],
                        help="Your seat")
    parser.add_argument("--deal", type=int, default=None,
                        help="Specific deal index (default: random)")
    parser.add_argument("--model", type=str, default="gemini-3.1-flash-lite-preview",
                        help="LLM model for other players")
    parser.add_argument("--player", choices=["llm", "dd"], default="dd",
                        help="Other players: llm or dd (double-dummy)")
    parser.add_argument("--pool-size", type=int, default=100,
                        help="Number of deals to load (pool for random selection)")
    args = parser.parse_args()
    play_interactive(args)


if __name__ == "__main__":
    main()

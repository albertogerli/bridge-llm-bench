"""
Bridge card play benchmark: evaluate LLM play against double-dummy optimal.

Usage:
    # Play 10 deals with DD solver (reference baseline)
    python scripts/play_benchmark.py --n_games 10 --player dd

    # Play with WBridge5 recorded play
    python scripts/play_benchmark.py --n_games 10 --player reference

    # Play with LLM
    python scripts/play_benchmark.py --model gemini-3.1-flash-lite-preview --n_games 5

    # Export for web viewer
    python scripts/play_benchmark.py --n_games 5 --player reference --export-web web/play_data/
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bridge_llm_bench.play.data import load_play_records
from bridge_llm_bench.play.engine import (
    PlayEngine, PlayResult,
    make_dd_player, make_reference_player, make_llm_player,
)
from bridge_llm_bench.play.prompts import play_prompt, parse_card_from_response
from bridge_llm_bench.play.stats import compute_stats, print_stats

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


def run_benchmark(args):
    """Run the card play benchmark."""
    print(f"Loading {args.n_games} deals from {DATA_PATH}...")
    records = load_play_records(
        str(DATA_PATH),
        n_games=args.n_games,
        compute_dd=True,
        dd_cache_path=str(DD_CACHE),
    )
    print(f"  Loaded {len(records)} deals with contracts\n")

    results: list[PlayResult] = []

    for i, record in enumerate(records):
        print(f"[{i+1}/{len(records)}] {record.contract_str} "
              f"(DD: {record.dd_table.get(f'{record.contract[1]}_{record.declarer_seat}', '?')} tricks)")

        engine = PlayEngine(record)

        if args.player == "dd":
            player = make_dd_player()
        elif args.player == "reference":
            player = make_reference_player(record.play_cards)
        elif args.player == "llm":
            from bridge_llm_bench.clients import get_client
            client = get_client(args.model, temperature=0.0)
            player = make_llm_player(client, args.model, play_prompt, parse_card_from_response)
        else:
            raise ValueError(f"Unknown player type: {args.player}")

        t0 = time.time()
        result = engine.play_deal(player)
        elapsed = time.time() - t0

        decl_tricks = result.tricks_won_ns if record.declarer_seat in ("N", "S") else result.tricks_won_ew
        dd_tricks = record.dd_table.get(f"{record.contract[1]}_{record.declarer_seat}", "?")
        print(f"  → {decl_tricks} tricks (DD: {dd_tricks}) | "
              f"Score: {result.contract_score_actual} (DD: {result.contract_score_dd}) | "
              f"IMP: {result.imp_diff_vs_dd:+d} | "
              f"Mistakes: D={result.n_declarer_mistakes} Def={result.n_defense_mistakes} | "
              f"{elapsed:.1f}s")

        results.append(result)

    # Print aggregate stats
    stats = compute_stats(results)
    print_stats(stats)

    # Export web data if requested
    if args.export_web:
        export_web_data(records, results, args.export_web)

    # Save results
    if args.output:
        save_results(records, results, args.output)


def export_web_data(records, results, output_dir):
    """Export results as JSON for the web viewer."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    deals_index = []

    for record, result in zip(records, results):
        deal_data = {
            "deal_id": record.deal_id,
            "hands": record.hands,
            "auction": record.auction,
            "contract": {
                "level": record.contract[0],
                "strain": record.contract[1],
                "declarer": record.declarer_seat,
                "doubled": record.contract[3],
            },
            "vulnerability": record.vulnerability,
            "tricks": [],
            "result": {
                "tricks_ns": result.tricks_won_ns,
                "tricks_ew": result.tricks_won_ew,
                "score": result.contract_score_actual,
                "dd_score": result.contract_score_dd,
                "imp_diff": result.imp_diff_vs_dd,
            },
        }

        for trick in result.tricks:
            trick_data = {
                "lead": trick.lead_seat,
                "cards": [
                    {
                        "seat": cp.seat,
                        "card": cp.card,
                        "dd_optimal": cp.dd_optimal,
                        "is_mistake": cp.is_mistake,
                        "from_dummy": cp.from_dummy,
                    }
                    for cp in trick.cards
                ],
                "winner": trick.winner,
            }
            deal_data["tricks"].append(trick_data)

        filename = f"deal_{record.deal_id}.json"
        with open(out / filename, "w") as f:
            json.dump(deal_data, f, indent=2)
        deals_index.append({"deal_id": record.deal_id, "contract": result.contract_str, "file": filename})

    # Write index
    with open(out / "index.json", "w") as f:
        json.dump(deals_index, f, indent=2)
    print(f"\n  Exported {len(deals_index)} deals to {out}/")


def save_results(records, results, output_path):
    """Save results summary to JSON."""
    out = Path(output_path)
    out.mkdir(parents=True, exist_ok=True)

    summary = []
    for record, result in zip(records, results):
        summary.append({
            "deal_id": record.deal_id,
            "contract": result.contract_str,
            "tricks_ns": result.tricks_won_ns,
            "tricks_ew": result.tricks_won_ew,
            "score": result.contract_score_actual,
            "dd_score": result.contract_score_dd,
            "imp_vs_dd": result.imp_diff_vs_dd,
            "lead": result.lead_card,
            "lead_dd": result.lead_dd_optimal,
            "lead_mistake": result.lead_is_mistake,
            "decl_mistakes": result.n_declarer_mistakes,
            "def_mistakes": result.n_defense_mistakes,
        })

    with open(out / "results.json", "w") as f:
        json.dump(summary, f, indent=2)
    print(f"  Saved results to {out}/results.json")


def main():
    parser = argparse.ArgumentParser(description="Bridge card play benchmark")
    parser.add_argument("--n_games", type=int, default=10, help="Number of deals to play")
    parser.add_argument("--player", choices=["dd", "reference", "llm"], default="reference",
                        help="Player type: dd (double-dummy), reference (WBridge5), llm")
    parser.add_argument("--model", type=str, default="gemini-3.1-flash-lite-preview",
                        help="LLM model (when --player llm)")
    parser.add_argument("--export-web", type=str, default=None,
                        help="Export JSON for web viewer to this directory")
    parser.add_argument("--output", type=str, default=None,
                        help="Save results to this directory")
    args = parser.parse_args()

    if args.player == "llm" and not args.model:
        parser.error("--model required when --player is llm")

    run_benchmark(args)


if __name__ == "__main__":
    main()

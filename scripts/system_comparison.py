"""
Compare bidding systems by DD/IMP performance.

Runs P30 (system-adaptive prompt) for each bidding system on N positions,
then compares using double-dummy IMP analysis against BBA oracle.

Usage:
    python scripts/system_comparison.py
    python scripts/system_comparison.py --n 150 --model gemini-3.1-flash-lite-preview
"""

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

# Auto-load .env
_root = Path(__file__).resolve().parent.parent
_env_file = _root / ".env"
if _env_file.exists():
    for line in _env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            key, val = line.split('=', 1)
            os.environ.setdefault(key.strip(), val.strip())

from ev_analysis import (
    load_deals, compute_dd_tables, run_llm, score_bid_dd,
    bid_to_strain, bid_to_level, DD_CACHE, DATA_CSV
)
from bridge_llm_bench.metrics.dd_scoring import imp_diff

SYSTEMS = ["SAYC", "2/1", "ACOL", "PRECISION", "SEF", "POLISH_CLUB"]


def compare_systems(deals, positions, model_name, prompt_id, n, oracle="bba"):
    """Run all systems and compare DD/IMP results."""
    oracle_col = {"ben": "ben_sayc_bid", "bba": "bba_bid", "wbridge5": "wbridge5_bid"}[oracle]

    results = {}

    for conv in SYSTEMS:
        print(f"\n{'='*60}")
        print(f"  System: {conv}")
        print(f"{'='*60}")

        llm_bids = run_llm(positions, model_name, prompt_id, n, conv=conv)
        target = positions[:len(llm_bids)]

        # Compute bid accuracy vs oracle
        exact = sum(1 for i, p in enumerate(target)
                    if llm_bids[i].upper() == p[oracle_col].upper())

        # Compute IMP analysis
        imp_diffs = []
        for i, pos in enumerate(target):
            deal = deals[pos["deal_id"]]
            dd = deal.get("dd_table", {})
            if not dd:
                imp_diffs.append(0)
                continue

            oracle_bid = pos[oracle_col]
            llm_bid = llm_bids[i]

            if llm_bid.upper() == oracle_bid.upper():
                imp_diffs.append(0)
                continue

            o_score = score_bid_dd(deal, oracle_bid, pos["auction"])
            l_score = score_bid_dd(deal, llm_bid, pos["auction"])
            imp_val = imp_diff(l_score, o_score)
            imp_diffs.append(imp_val)

        n_pos = len(imp_diffs)
        n_same = sum(1 for x in imp_diffs if x == 0)
        n_better = sum(1 for x in imp_diffs if x > 0)
        n_worse = sum(1 for x in imp_diffs if x < 0)
        total_imp = sum(imp_diffs)
        mean_imp = total_imp / n_pos if n_pos else 0

        results[conv] = {
            "accuracy": exact / n_pos if n_pos else 0,
            "exact": exact,
            "n": n_pos,
            "net_imps": total_imp,
            "mean_imp": mean_imp,
            "n_better": n_better,
            "n_worse": n_worse,
            "n_zero": n_same,
            "bids": llm_bids,
        }

        print(f"  Accuracy: {exact}/{n_pos} ({100*exact/n_pos:.1f}%)")
        print(f"  Net IMPs: {total_imp:+d} | Mean: {mean_imp:+.2f}/pos")
        print(f"  LLM better: {n_better} | Oracle better: {n_worse} | Same: {n_same}")

    return results


def print_comparison_table(results, oracle):
    """Print final comparison table."""
    print(f"\n{'='*80}")
    print(f"BIDDING SYSTEM COMPARISON (P30, vs {oracle.upper()} oracle)")
    print(f"{'='*80}")
    print(f"{'System':<15} {'Accuracy':>10} {'Net IMPs':>10} {'IMP/pos':>10} "
          f"{'LLM+':>6} {'Orc+':>6} {'Same':>6}")
    print(f"{'-'*15} {'-'*10} {'-'*10} {'-'*10} {'-'*6} {'-'*6} {'-'*6}")

    # Sort by net IMPs (best first)
    for conv in sorted(results, key=lambda c: -results[c]["net_imps"]):
        r = results[conv]
        acc_str = f"{r['exact']}/{r['n']} ({100*r['accuracy']:.1f}%)"
        print(f"{conv:<15} {acc_str:>10} {r['net_imps']:>+10d} {r['mean_imp']:>+10.2f} "
              f"{r['n_better']:>6d} {r['n_worse']:>6d} {r['n_zero']:>6d}")

    # Head-to-head IMP comparison between systems
    print(f"\n{'='*80}")
    print("HEAD-TO-HEAD IMP COMPARISON (pairwise)")
    print(f"{'='*80}")

    convs = sorted(results.keys())
    # Print header
    print(f"{'':>15}", end="")
    for c in convs:
        print(f" {c[:8]:>8}", end="")
    print()

    for c1 in convs:
        print(f"{c1:<15}", end="")
        bids1 = results[c1]["bids"]
        for c2 in convs:
            if c1 == c2:
                print(f" {'---':>8}", end="")
                continue
            bids2 = results[c2]["bids"]
            # Count positions where c1 and c2 differ
            n = min(len(bids1), len(bids2))
            diff_count = sum(1 for i in range(n) if bids1[i].upper() != bids2[i].upper())
            print(f" {diff_count:>8d}", end="")
        print()


def main():
    parser = argparse.ArgumentParser(description="Compare bidding systems by DD/IMP")
    parser.add_argument("--model", default="gemini-3.1-flash-lite-preview")
    parser.add_argument("--prompt_id", type=int, default=30)
    parser.add_argument("--n", type=int, default=150)
    parser.add_argument("--oracle", default="bba", choices=["ben", "bba", "wbridge5"])
    parser.add_argument("--systems", nargs="+", default=None,
                        help="Specific systems to test (default: all)")
    args = parser.parse_args()

    global SYSTEMS
    if args.systems:
        SYSTEMS = [s.upper() for s in args.systems]

    print("=" * 80)
    print("BIDDING SYSTEM COMPARISON — DD/IMP ANALYSIS")
    print(f"Model: {args.model} | Prompt: P{args.prompt_id} | N={args.n} | Oracle: {args.oracle}")
    print("=" * 80)

    # Load data
    print(f"\n1. Loading dataset...")
    deals, positions = load_deals(DATA_CSV)
    print(f"   {len(deals)} deals, {len(positions)} positions")

    print(f"\n2. Computing DD tables...")
    compute_dd_tables(deals, DD_CACHE)

    print(f"\n3. Running all systems...")
    results = compare_systems(deals, positions, args.model, args.prompt_id, args.n, args.oracle)

    # Print final comparison
    print_comparison_table(results, args.oracle)

    # Save results
    save_path = _root / "data" / "system_comparison.json"
    save_data = {conv: {k: v for k, v in r.items() if k != "bids"}
                 for conv, r in results.items()}
    with open(save_path, "w") as f:
        json.dump(save_data, f, indent=2)
    print(f"\nResults saved to {save_path}")

    print("\n" + "=" * 80)
    print("DONE")
    print("=" * 80)


if __name__ == "__main__":
    main()

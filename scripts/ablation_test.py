"""
Ablation test: systematically remove each rule block from P20 to measure its contribution.
Runs all variants and reports accuracy delta vs baseline P20.

Usage:
    python3 scripts/ablation_test.py --n 150 --oracle bba
"""

import argparse
import csv
import json
import os
import sys
import time
from pathlib import Path

# Auto-load .env
_env_file = Path(__file__).resolve().parent.parent / ".env"
if _env_file.exists():
    for line in _env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            key, val = line.split('=', 1)
            os.environ.setdefault(key.strip(), val.strip())

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from bridge_llm_bench.parsers.bid_parser import parse_bid_from_response
from bridge_llm_bench.utils.config import CONVENTIONS, SAYC_KNOWLEDGE

# ── Hand info helper ──
def hand_info(hand):
    suits = {}
    for part in hand.split():
        if part.startswith(('S:', 'H:', 'D:', 'C:')):
            suit = part[0]
            cards = part[2:]
            suits[suit] = cards
    hcp_map = {'A': 4, 'K': 3, 'Q': 2, 'J': 1}
    hcp = sum(hcp_map.get(c, 0) for s in suits.values() for c in s)
    lengths = []
    for s in 'SHDC':
        n = len(suits.get(s, ''))
        if n >= 5:
            lengths.append(f"{n}{s}")
    return f"{hcp} HCP" + (", " + " ".join(lengths) if lengths else "")

# ── P20 decomposed into blocks ──

HEADER = lambda hand, auction, conv: (
    f"You are an expert SAYC bridge bidder. {CONVENTIONS[conv]}\n"
    f"{SAYC_KNOWLEDGE}\n"
)

BLOCK_A = (  # COMPETITIVE BIDDING RULES
    "\nCOMPETITIVE BIDDING RULES:\n"
    "After opponents overcall your partner's opening:\n"
    "- With 3+ card support for partner's major + 8+ HCP → DOUBLE (support/competitive X)\n"
    "- With 5+ card side suit → bid your suit (even with minimum values)\n"
    "- With 13-15 HCP balanced + stopper in opponent's suit → bid 3NT directly\n"
    "- In competitive auctions, DON'T just pass with a fit. Compete!\n"
)

BLOCK_B = (  # TAKEOUT DOUBLE RESPONSE
    "\nAfter a takeout double of partner's bid:\n"
    "- With a good 6+ card suit, JUMP in your suit (preemptive/competitive)\n"
    "- Don't just bid at the cheapest level with a long strong suit\n"
)

BLOCK_C = (  # PENALTY DOUBLES
    "\nPENALTY DOUBLES:\n"
    "- When partner makes a PENALTY double (double of a suit at 2+ level), PASS to defend\n"
    "- Do NOT pull partner's penalty double unless you have extreme distribution (void in their suit)\n"
    "- If you have trump honors (A, K, Q) in the doubled suit → definitely pass\n"
)

BLOCK_D = (  # 5-LEVEL DECISIONS
    "\n5-LEVEL DECISIONS:\n"
    "- 'The 5-level belongs to the opponents' — do NOT compete to 5-minor unless forced\n"
    "- If opponents bid 5 of their suit, Pass is usually right unless you have extreme shape\n"
    "- Once the auction has reached the 5-level, STOP competing\n"
)

BLOCK_E = (  # WHEN NOT TO COMPETE
    "\nWhen NOT to compete:\n"
    "- With a MISFIT (no support, no good suit) → Pass\n"
    "- Too weak for 2-level overcall (need 10+ HCP + 5+ card suit)\n"
    "- After your initial Pass, don't JUMP aggressively — but still bid with a good long suit\n"
    "- If partner PASSED your bid, don't bid again without extra shape/strength\n"
)

BLOCK_F = (  # OPENING SUIT CHOICE
    "\nOPENING SUIT CHOICE:\n"
    "- With 6-5 in two suits, open the LONGER suit (6C+5D = open 1C, not 1D)\n"
    "- With 5-5, open the HIGHER-ranking suit (5H+5S = open 1S)\n"
)

BLOCK_G = (  # RESPONSES TO 1-MINOR
    "\nRESPONSES TO 1-MINOR:\n"
    "- With a 4-card major, ALWAYS bid it (bid 4-card suits UP THE LINE: 1D then 1H then 1S)\n"
    "- 1S over partner's 1H opening with 4 spades is ALWAYS correct\n"
)

BLOCK_H = (  # WEAK 2 OPENINGS
    "\nWEAK 2 OPENINGS:\n"
    "- Need a GOOD 6-card suit (2+ honors like KQxxxx, QJTxxx, AJTxxx)\n"
    "- Do NOT open weak 2 with Axxxxx (only 1 honor) — suit too weak\n"
    "- Do NOT open weak 2 with a side Ace — hand is too strong-looking\n"
)

# Examples grouped
EX_OPENING = (
    "S:AKJ74 H:Q93 D:K84 C:T6 (14 HCP) | None → 1S\n"
    "S:AK4 H:AQT3 D:5 C:J8742 (16 HCP) | None → 1C\n"
    "S:KJ5 H:AQ4 D:KT93 C:Q72 (16 HCP) | None → 1NT\n"
    "S:97 H:KJ984 D:T5 C:QJ32 (8 HCP) | None → Pass\n"
    "S:QT7 H:A86542 D:764 C:A (10 HCP, 6H) | None → Pass "
    "(6H suit has only Ace — too weak for weak 2. Side Ace also wrong. Pass!)\n"
)

EX_COMPETITIVE = (
    "S:Q52 H:6543 D:K732 C:AJ (10 HCP, 3S) | P P 1S 1NT → X "
    "(COMPETITIVE DOUBLE: 10 HCP + 3-card S support. Do NOT pass!)\n"
    "S:97 H:A9872 D:AJ65 C:43 (9 HCP, 5H 4D) | P P 1S 1NT P → 2D "
    "(compete with 5-card D suit. Don't let them play 1NT!)\n"
    "S:T3 H:84 D:KQJ982 C:KQT (10 HCP, 6D) | P 1H P 2C X P → 3D "
    "(JUMP to 3D with strong 6-card suit KQJ982. Don't bid only 2D!)\n"
    "S:54 H: D:AQ953 C:AKQJT6 (16 HCP, 6C 5D) | P 1D X 1S → 5C "
    "(huge hand with 11-card minor suits - jump to game in C!)\n"
    "S:Q862 H:AJT9875 D:86 C: (8 HCP, 7H) | P 1D X → 1H "
    "(bid at cheapest level first, NOT 2H. Show your suit economically)\n"
)

EX_RESPONSE = (
    "S:QJ75 H:7 D:AT63 C:A965 (11 HCP) | 1H P → 1S (new suit forcing, bid 4-card major)\n"
    "S:J8742 H:3 D:K5 C:AQT96 (11 HCP) | 1H → 1S (overcall with 5-card suit)\n"
    "S:T3 H:84 D:KQJ982 C:KQT (10 HCP) | 1H → Pass (2-level overcall too risky)\n"
)

EX_3NT = (
    "S:J32 H:KT3 D:AKJT C:Q65 (14 HCP, bal) | 1D 1H → 3NT "
    "(14 HCP + heart stopper KT3 = jump to 3NT over overcall)\n"
)

EX_PENALTY = (
    "S:AK4 H:AQT3 D:5 C:J8742 (16 HCP) | P 1H P 2C X → 3C (support partner's clubs)\n"
    "S:AK4 H:AQT3 D:5 C:J8742 | P 1H P 2C X P 2S X P → Pass "
    "(partner's X of 2S is PENALTY. We have AK of spades. PASS and defend!)\n"
)

EX_COMP_RAISE = (
    "S:KJ93 H:KQ64 D:T74 C:73 (9 HCP, 4S) | P 1D X 1S P 2C P 4D P → 4S "
    "(4-card support for partner's 1S + opponents at 4D = compete to 4S)\n"
)

EX_5LEVEL = (
    "S:54 H: D:AQ953 C:AKQJT6 | P 1D X 1S P 2C P 4D P 4H P 5D → Pass "
    "(STOP at 5-level! Do NOT bid 5C or higher. The 5-level belongs to opponents.)\n"
)

FOOTER = lambda hand, auction: (
    f"\nPosition: {'Opener' if not auction else 'Seat ' + str(len(auction.split())+1)}. "
    f"Your hand: {hand} ({hand_info(hand)})\n"
    f"Auction: {auction if auction else 'None'}\n"
    "Your bid:"
)

ALL_RULES = [BLOCK_A, BLOCK_B, BLOCK_C, BLOCK_D, BLOCK_E, BLOCK_F, BLOCK_G, BLOCK_H]
ALL_EXAMPLES = [EX_OPENING, EX_COMPETITIVE, EX_RESPONSE, EX_3NT, EX_PENALTY, EX_COMP_RAISE, EX_5LEVEL]

RULE_NAMES = ["A:competitive", "B:takeout_X", "C:penalty_X", "D:5level",
              "E:not_compete", "F:suit_choice", "G:resp_1minor", "H:weak2"]
EXAMPLE_NAMES = ["ex:opening", "ex:competitive", "ex:response", "ex:3NT",
                 "ex:penalty", "ex:comp_raise", "ex:5level"]

def build_prompt(hand, auction, conv, skip_rules=None, skip_examples=None):
    """Build P20 variant with specified blocks removed."""
    skip_rules = skip_rules or set()
    skip_examples = skip_examples or set()

    parts = [HEADER(hand, auction, conv)]

    for i, rule in enumerate(ALL_RULES):
        if i not in skip_rules:
            parts.append(rule)

    examples = []
    for i, ex in enumerate(ALL_EXAMPLES):
        if i not in skip_examples:
            examples.append(ex)

    if examples:
        parts.append("\nExamples (study carefully):\n")
        parts.extend(examples)

    parts.append(FOOTER(hand, auction))
    return "".join(parts)


def load_positions(csv_path, n, oracle):
    """Load test positions from CSV."""
    col_map = {'bba': 'bba_bid', 'ben': 'ben_sayc_bid', 'wbridge5': 'wbridge5_bid'}
    oracle_col = col_map.get(oracle, oracle)

    positions = []
    with open(csv_path, 'r') as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader):
            if i >= n:
                break
            hand = row['hand']
            auction = row.get('auction', '') or ''
            if auction == 'nan':
                auction = ''
            ref_bid = row[oracle_col]
            positions.append((hand, auction.strip(), ref_bid))
    return positions


def run_variant(model_ref, safety, positions, variant_name, skip_rules=None, skip_examples=None, conv='SAYC'):
    """Run a single ablation variant and return accuracy."""
    import google.generativeai as genai

    correct = 0
    total = len(positions)
    cfg = genai.types.GenerationConfig(temperature=0.0, max_output_tokens=50, candidate_count=1)

    for i, (hand, auction, ref_bid) in enumerate(positions):
        prompt = build_prompt(hand, auction, conv, skip_rules, skip_examples)

        try:
            resp = model_ref.generate_content(prompt, generation_config=cfg, safety_settings=safety)
            text = resp.text.strip() if resp.text else "Pass"
            bid = parse_bid_from_response(text)
        except Exception as e:
            bid = "?"

        if bid.upper() == ref_bid.upper():
            correct += 1

        if (i + 1) % 50 == 0:
            print(f"  {variant_name}: {i+1}/{total} acc={correct}/{i+1} ({100*correct/(i+1):.1f}%)")

    acc = correct / total
    print(f"  -> {variant_name}: {correct}/{total} = {100*acc:.1f}%")
    return correct, total


def main():
    import google.generativeai as genai

    parser = argparse.ArgumentParser()
    parser.add_argument('--n', type=int, default=150)
    parser.add_argument('--oracle', default='bba')
    parser.add_argument('--model', default='gemini-3.1-flash-lite-preview')
    parser.add_argument('--variant', default='all', help='Which variant to run: all, rules, examples, or specific index like r0,r1,e0')
    args = parser.parse_args()

    api_key = os.environ.get("GOOGLE_API_KEY")
    genai.configure(api_key=api_key)
    model_ref = genai.GenerativeModel(model_name=args.model)

    safety = [
        {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
    ]

    csv_path = Path(__file__).resolve().parent.parent / "data" / "ben_sayc_100.csv"
    positions = load_positions(csv_path, args.n, args.oracle)

    # Define variants
    variants = []

    if args.variant in ('all', 'rules'):
        for i in range(len(ALL_RULES)):
            variants.append((f"no_{RULE_NAMES[i]}", {i}, set()))

    if args.variant in ('all', 'examples'):
        for i in range(len(ALL_EXAMPLES)):
            variants.append((f"no_{EXAMPLE_NAMES[i]}", set(), {i}))

    if args.variant in ('all',):
        variants.append(("no_ALL_rules", set(range(8)), set()))
        variants.append(("no_ALL_examples", set(), set(range(7))))

    if args.variant == 'big':
        variants.append(("no_ALL_rules", set(range(8)), set()))
        variants.append(("no_ALL_examples", set(), set(range(7))))
        # Drop harmful rules A+B+E
        variants.append(("no_A+B+E", {0, 1, 4}, set()))
        # Drop A+B+E + neutral rules C+G+H
        variants.append(("no_A+B+C+E+G+H", {0, 1, 2, 4, 6, 7}, set()))

    if args.variant.startswith('r') and args.variant[1:].isdigit():
        idx = int(args.variant[1:])
        variants = [(f"no_{RULE_NAMES[idx]}", {idx}, set())]
    elif args.variant.startswith('e') and args.variant[1:].isdigit():
        idx = int(args.variant[1:])
        variants = [(f"no_{EXAMPLE_NAMES[idx]}", set(), {idx})]

    print(f"{'='*60}")
    print(f"ABLATION TEST — P20 decomposition")
    print(f"Model: {args.model}, Oracle: {args.oracle}, N={args.n}")
    print(f"Variants to test: {len(variants) + 1} (incl. baseline)")
    print(f"{'='*60}")

    results = {}

    print(f"\n--- BASELINE (full P20) ---")
    correct, total = run_variant(model_ref, safety, positions, "P20_baseline", set(), set())
    baseline_acc = correct / total
    results["P20_baseline"] = (correct, total, 0.0)

    for name, skip_r, skip_e in variants:
        print(f"\n--- {name} ---")
        correct, total = run_variant(model_ref, safety, positions, name, skip_r, skip_e)
        acc = correct / total
        delta = acc - baseline_acc
        results[name] = (correct, total, delta)

    # Summary
    print(f"\n{'='*60}")
    print(f"SUMMARY — sorted by delta")
    print(f"Negative delta = removing this block HURTS (block is valuable)")
    print(f"Positive delta = removing this block HELPS (block is harmful)")
    print(f"{'='*60}")
    print(f"{'Variant':<30} {'Acc':>8} {'Delta':>8} {'Verdict'}")
    print(f"{'-'*30} {'-'*8} {'-'*8} {'-'*20}")

    sorted_results = sorted(results.items(), key=lambda x: x[1][2])
    for name, (correct, total, delta) in sorted_results:
        acc_str = f"{correct}/{total}"
        delta_str = f"{delta:+.1%}"
        if name == "P20_baseline":
            verdict = "BASELINE"
        elif delta < -0.02:
            verdict = "KEEP (removing hurts)"
        elif delta > 0.02:
            verdict = "DROP (removing helps!)"
        else:
            verdict = "~neutral"
        print(f"{name:<30} {acc_str:>8} {delta_str:>8} {verdict}")

    # Save results
    results_path = Path(__file__).resolve().parent.parent / "data" / "ablation_results.json"
    save_data = {
        "model": args.model,
        "oracle": args.oracle,
        "n": args.n,
        "baseline": baseline_acc,
        "results": {k: {"correct": v[0], "total": v[1], "acc": round(v[0]/v[1], 4), "delta": round(v[2], 4)} for k, v in results.items()}
    }
    with open(results_path, 'w') as f:
        json.dump(save_data, f, indent=2)
    print(f"\nResults saved to {results_path}")


if __name__ == '__main__':
    main()

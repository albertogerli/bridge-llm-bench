"""
EV/IMP analysis with double-dummy scoring.

Reconstructs full deals from the CSV dataset, computes DD tables using endplay,
and evaluates bids by their expected value (contract scores and IMP differences).

Usage:
    python scripts/ev_analysis.py --oracle bba
    python scripts/ev_analysis.py --oracle bba --cache   # cache DD tables
"""

import argparse
import csv
import json
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from bridge_llm_bench.metrics.dd_scoring import (
    contract_score,
    format_contract,
    imp_diff,
    parse_final_contract,
)

try:
    from endplay.types import Deal, Denom, Player
    from endplay.dds import calc_dd_table
    HAS_ENDPLAY = True
except ImportError:
    HAS_ENDPLAY = False

_root = Path(__file__).resolve().parent.parent
DATA_CSV = _root / "data" / "ben_sayc_100.csv"
DD_CACHE = _root / "data" / "dd_tables.json"
LLM_CACHE_DIR = _root / "data" / "llm_cache"

# Auto-load .env
_env_file = _root / ".env"
if _env_file.exists():
    for line in _env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            key, val = line.split('=', 1)
            os.environ.setdefault(key.strip(), val.strip())

ORACLE_COLUMNS = {
    "ben": "ben_sayc_bid",
    "bba": "bba_bid",
    "wbridge5": "wbridge5_bid",
}

SEATS = ["N", "E", "S", "W"]

# Map from endplay Denom to our strain codes
DENOM_MAP = {
    Denom.clubs: "C",
    Denom.diamonds: "D",
    Denom.hearts: "H",
    Denom.spades: "S",
    Denom.nt: "NT",
} if HAS_ENDPLAY else {}

PLAYER_MAP = {
    Player.north: "N",
    Player.east: "E",
    Player.south: "S",
    Player.west: "W",
} if HAS_ENDPLAY else {}

STRAIN_TO_DENOM = {v: k for k, v in DENOM_MAP.items()} if HAS_ENDPLAY else {}
SEAT_TO_PLAYER = {v: k for k, v in PLAYER_MAP.items()} if HAS_ENDPLAY else {}


# ── Deal reconstruction ──────────────────────────────────────────────


def hand_str_to_pbn(hand: str) -> str:
    """
    Convert 'S:Q52 H:6543 D:K732 C:AJ' to PBN suit format 'Q52.6543.K732.AJ'.
    Handles void suits (empty string after colon).
    """
    suits = {}
    for part in hand.split():
        if ":" in part:
            suit, cards = part.split(":", 1)
            suits[suit] = cards if cards != "-" else ""
    # PBN order: spades.hearts.diamonds.clubs
    return ".".join(suits.get(s, "") for s in "SHDC")


def load_deals(csv_path: Path) -> Tuple[List[Dict], List[Dict]]:
    """
    Load CSV and reconstruct full deals.

    Returns
    -------
    deals : list of dict
        Each deal has: deal_id, hands (N/E/S/W pbn strings), positions (list of row indices)
    positions : list of dict
        Each position has: pos_id, deal_id, seat, hand, auction, wbridge5_bid, ben_sayc_bid, bba_bid
    """
    with open(csv_path) as f:
        rows = list(csv.DictReader(f))

    # Find deal boundaries: empty auction = start of new deal
    deal_starts = [0]
    for i in range(1, len(rows)):
        if rows[i]["auction"].strip() == "":
            deal_starts.append(i)

    deals = []
    positions = []

    for d_idx, start in enumerate(deal_starts):
        end = deal_starts[d_idx + 1] if d_idx + 1 < len(deal_starts) else len(rows)
        n_pos = end - start

        # First 4 positions give the 4 hands (cycling through seats)
        hands = {}
        for s in range(min(4, n_pos)):
            seat = SEATS[s]
            hands[seat] = hand_str_to_pbn(rows[start + s]["hand"])

        # Reconstruct WBridge5 auction from the longest position
        last_row = rows[end - 1]
        wb5_auction_str = last_row["auction"].strip()
        wb5_auction = wb5_auction_str.split() if wb5_auction_str else []
        # Append the WBridge5 bid at the last position
        wb5_last_bid = last_row["wbridge5_bid"].strip()
        if wb5_last_bid:
            wb5_auction.append(wb5_last_bid)

        deal = {
            "deal_id": d_idx,
            "hands": hands,
            "wb5_auction": wb5_auction,
            "n_positions": n_pos,
            "start_row": start,
        }
        deals.append(deal)

        # Build position records
        for s in range(n_pos):
            row = rows[start + s]
            seat = SEATS[s % 4]
            positions.append({
                "pos_id": start + s,
                "deal_id": d_idx,
                "seat": seat,
                "hand": row["hand"],
                "auction_str": row["auction"].strip(),
                "auction": row["auction"].strip().split() if row["auction"].strip() else [],
                "wbridge5_bid": row["wbridge5_bid"].strip(),
                "ben_sayc_bid": row["ben_sayc_bid"].strip(),
                "bba_bid": row["bba_bid"].strip(),
            })

    return deals, positions


# ── DD table computation ─────────────────────────────────────────────


def compute_dd_tables(deals: List[Dict], cache_path: Optional[Path] = None) -> List[Dict]:
    """
    Compute DD tables for all deals. Optionally cache to disk.

    Returns each deal's dd_table as dict: {(strain, seat): tricks}
    stored as {"S_N": tricks, "S_E": tricks, ...} for JSON compatibility.
    """
    # Try loading from cache
    if cache_path and cache_path.exists():
        with open(cache_path) as f:
            cached = json.load(f)
        if len(cached) == len(deals):
            print(f"  Loaded DD tables from cache ({cache_path})")
            for i, deal in enumerate(deals):
                deal["dd_table"] = cached[str(i)]
            return deals

    if not HAS_ENDPLAY:
        print("ERROR: endplay not installed. Run: pip install endplay")
        sys.exit(1)

    print(f"  Computing DD tables for {len(deals)} deals...")
    cache_data = {}

    for deal in deals:
        h = deal["hands"]
        if len(h) < 4:
            print(f"  WARNING: Deal {deal['deal_id']} has only {len(h)} hands, skipping DD")
            deal["dd_table"] = {}
            continue

        pbn = f"N:{h['N']} {h['E']} {h['S']} {h['W']}"
        d = Deal(pbn)
        table = calc_dd_table(d)

        dd = {}
        for denom, strain in DENOM_MAP.items():
            for player, seat in PLAYER_MAP.items():
                dd[f"{strain}_{seat}"] = table[denom, player]

        deal["dd_table"] = dd
        cache_data[str(deal["deal_id"])] = dd

    if cache_path:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        with open(cache_path, "w") as f:
            json.dump(cache_data, f, indent=2)
        print(f"  Cached DD tables to {cache_path}")

    return deals


def dd_tricks(deal: Dict, strain: str, declarer: str) -> int:
    """Look up DD tricks for a strain and declarer from the deal's DD table."""
    key = f"{strain}_{declarer}"
    return deal["dd_table"].get(key, 0)


def dd_best_contract(deal: Dict, side: str) -> Tuple[str, str, int, int]:
    """
    Find the DD-optimal contract for a side.

    Parameters
    ----------
    deal : dict with dd_table
    side : 'NS' or 'EW'

    Returns
    -------
    (strain, declarer, level, score) for the best DD contract
    """
    seats = ["N", "S"] if side == "NS" else ["E", "W"]
    best = ("Pass", seats[0], 0, 0)

    for strain in ["C", "D", "H", "S", "NT"]:
        for seat in seats:
            tricks = dd_tricks(deal, strain, seat)
            # Try all levels from 1 to 7
            for level in range(1, 8):
                needed = level + 6
                if tricks >= needed:
                    score = contract_score(level, strain, tricks)
                    if score > best[3]:
                        best = (strain, seat, level, score)

    return best


# ── Auction analysis ─────────────────────────────────────────────────


def get_declaring_side(auction: List[str], seat_offset: int = 0) -> str:
    """
    Determine which side declared the final contract.

    Parameters
    ----------
    auction : list of bid strings
    seat_offset : seat index of first bidder (0=N)

    Returns
    -------
    'NS' or 'EW'
    """
    contract = parse_final_contract(auction)
    if contract is None:
        return "NS"  # default
    _, _, declarer_seat, _ = contract
    actual_seat = (seat_offset + declarer_seat) % 4
    return "NS" if actual_seat in (0, 2) else "EW"


def bid_to_strain(bid: str) -> Optional[str]:
    """Extract strain from a bid like '3NT' -> 'NT', '2H' -> 'H'. None for Pass/X/XX."""
    bid = bid.upper().strip()
    if bid in ("PASS", "P", "X", "XX"):
        return None
    if len(bid) >= 2 and bid[0].isdigit():
        return bid[1:]
    return None


def bid_to_level(bid: str) -> Optional[int]:
    """Extract level from a bid like '3NT' -> 3. None for Pass/X/XX."""
    bid = bid.upper().strip()
    if bid in ("PASS", "P", "X", "XX"):
        return None
    if len(bid) >= 2 and bid[0].isdigit():
        return int(bid[0])
    return None


# ── Main analysis ────────────────────────────────────────────────────


def analyze_deals(deals: List[Dict], positions: List[Dict], oracle: str):
    """Print comprehensive DD analysis for all deals."""
    oracle_col = ORACLE_COLUMNS[oracle]

    print("\n" + "=" * 70)
    print("DEAL-BY-DEAL DD ANALYSIS")
    print("=" * 70)

    for deal in deals:
        dd = deal.get("dd_table", {})
        if not dd:
            continue

        print(f"\n{'─' * 70}")
        print(f"Deal {deal['deal_id'] + 1}  ({deal['n_positions']} positions)")
        print(f"{'─' * 70}")

        # Print hands
        for seat in SEATS:
            pbn = deal["hands"].get(seat, "?")
            suits = pbn.split(".")
            if len(suits) == 4:
                print(f"  {seat}: S:{suits[0] or '-'} H:{suits[1] or '-'} "
                      f"D:{suits[2] or '-'} C:{suits[3] or '-'}")

        # Print DD table
        print(f"\n  DD Table (tricks by declarer):")
        print(f"  {'':>4s}   N    E    S    W")
        for strain in ["C", "D", "H", "S", "NT"]:
            row = [str(dd_tricks(deal, strain, s)).rjust(3) for s in SEATS]
            print(f"  {strain:>4s}  {'  '.join(row)}")

        # DD-optimal contracts for each side
        ns_best = dd_best_contract(deal, "NS")
        ew_best = dd_best_contract(deal, "EW")

        def fmt_optimal(best, side):
            strain, decl, level, score = best
            if level == 0:
                return f"Pass (no making contract)"
            return f"{format_contract(level, strain)} by {decl} (score {score})"

        print(f"\n  DD-optimal: NS={fmt_optimal(ns_best, 'NS')}")
        print(f"              EW={fmt_optimal(ew_best, 'EW')}")

        # WBridge5 final contract
        wb5_contract = parse_final_contract(deal["wb5_auction"])
        if wb5_contract:
            level, strain, decl_seat, dbl = wb5_contract
            decl = SEATS[decl_seat]
            tricks = dd_tricks(deal, strain, decl)
            score = contract_score(level, strain, tricks, doubled=dbl)
            decl_side = "NS" if decl_seat in (0, 2) else "EW"
            # Score from NS perspective
            ns_score = score if decl_side == "NS" else -score
            print(f"\n  WBridge5 contract: {format_contract(level, strain, dbl)} by {decl} "
                  f"→ DD {tricks} tricks → score {ns_score:+d} (NS)")
        else:
            print(f"\n  WBridge5 contract: All Pass")


def contract_level_match(deals: List[Dict], positions: List[Dict], oracle: str):
    """
    Analyze contract-level match between different oracles.
    For each position, compare oracle's bid vs WBridge5 bid and the other oracle.
    """
    oracle_col = ORACLE_COLUMNS[oracle]
    other_oracle = "ben_sayc_bid" if oracle == "bba" else "bba_bid"

    print("\n" + "=" * 70)
    print("CONTRACT-LEVEL MATCH ANALYSIS")
    print("=" * 70)

    # Compare oracle bids vs WBridge5 bids
    same_contract = 0
    same_denom = 0
    diff_denom = 0
    pass_vs_bid = 0
    total_diff = 0

    for pos in positions:
        oracle_bid = pos[oracle_col]
        wb5_bid = pos["wbridge5_bid"]

        if oracle_bid.upper() == wb5_bid.upper():
            continue  # exact match, skip

        total_diff += 1
        o_strain = bid_to_strain(oracle_bid)
        w_strain = bid_to_strain(wb5_bid)
        o_level = bid_to_level(oracle_bid)
        w_level = bid_to_level(wb5_bid)

        if o_strain is None or w_strain is None:
            pass_vs_bid += 1
        elif o_strain == w_strain and o_level == w_level:
            same_contract += 1
        elif o_strain == w_strain:
            same_denom += 1
        else:
            diff_denom += 1

    total = len(positions)
    exact = total - total_diff
    print(f"\n  {oracle.upper()} vs WBridge5 (N={total}):")
    print(f"    Exact bid match:         {exact:3d}/{total} ({100*exact/total:.1f}%)")
    print(f"    Different bids:          {total_diff:3d}/{total} ({100*total_diff/total:.1f}%)")
    if total_diff > 0:
        print(f"      Same denomination:     {same_denom:3d}/{total_diff} ({100*same_denom/total_diff:.1f}%)")
        print(f"      Different denomination:{diff_denom:3d}/{total_diff} ({100*diff_denom/total_diff:.1f}%)")
        print(f"      Pass vs bid:           {pass_vs_bid:3d}/{total_diff} ({100*pass_vs_bid/total_diff:.1f}%)")

    # Compare oracle vs other oracle
    same_o = 0
    same_d_o = 0
    diff_d_o = 0
    pvb_o = 0
    total_diff_o = 0

    for pos in positions:
        o_bid = pos[oracle_col]
        other_bid = pos[other_oracle]

        if o_bid.upper() == other_bid.upper():
            continue

        total_diff_o += 1
        o_s = bid_to_strain(o_bid)
        ot_s = bid_to_strain(other_bid)

        if o_s is None or ot_s is None:
            pvb_o += 1
        elif o_s == ot_s and bid_to_level(o_bid) == bid_to_level(other_bid):
            same_o += 1
        elif o_s == ot_s:
            same_d_o += 1
        else:
            diff_d_o += 1

    other_name = "Ben" if other_oracle == "ben_sayc_bid" else "BBA"
    exact_o = total - total_diff_o
    print(f"\n  {oracle.upper()} vs {other_name} (N={total}):")
    print(f"    Exact bid match:         {exact_o:3d}/{total} ({100*exact_o/total:.1f}%)")
    print(f"    Different bids:          {total_diff_o:3d}/{total} ({100*total_diff_o/total:.1f}%)")
    if total_diff_o > 0:
        print(f"      Same denomination:     {same_d_o:3d}/{total_diff_o} ({100*same_d_o/total_diff_o:.1f}%)")
        print(f"      Different denomination:{diff_d_o:3d}/{total_diff_o} ({100*diff_d_o/total_diff_o:.1f}%)")
        print(f"      Pass vs bid:           {pvb_o:3d}/{total_diff_o} ({100*pvb_o/total_diff_o:.1f}%)")


def imp_analysis(deals: List[Dict], positions: List[Dict], oracle: str):
    """
    IMP-based EV analysis.

    For each position where oracles disagree, compute the DD-based IMP impact
    of choosing one bid over the other.
    """
    oracle_col = ORACLE_COLUMNS[oracle]
    other_oracle = "ben_sayc_bid" if oracle == "bba" else "bba_bid"
    other_name = "Ben" if other_oracle == "ben_sayc_bid" else "BBA"

    print("\n" + "=" * 70)
    print("IMP-BASED DD ANALYSIS")
    print("=" * 70)

    # For each deal, analyze oracle vs WBridge5 final contracts
    print(f"\n  WBridge5 vs DD-optimal contracts:")
    total_imp_loss = 0
    n_deals_scored = 0

    for deal in deals:
        dd = deal.get("dd_table", {})
        if not dd:
            continue

        wb5_contract = parse_final_contract(deal["wb5_auction"])
        if wb5_contract is None:
            print(f"  Deal {deal['deal_id']+1}: All Pass (no contract)")
            continue

        level, strain, decl_seat, dbl = wb5_contract
        decl = SEATS[decl_seat]
        tricks = dd_tricks(deal, strain, decl)
        wb5_score = contract_score(level, strain, tricks, doubled=dbl)
        decl_side = "NS" if decl_seat in (0, 2) else "EW"
        ns_wb5 = wb5_score if decl_side == "NS" else -wb5_score

        # DD-optimal for the declaring side
        optimal = dd_best_contract(deal, decl_side)
        opt_strain, opt_decl, opt_level, opt_score = optimal
        ns_opt = opt_score if decl_side == "NS" else -opt_score

        imp = imp_diff(ns_opt, ns_wb5)
        total_imp_loss += abs(imp)
        n_deals_scored += 1

        if imp != 0:
            print(f"  Deal {deal['deal_id']+1}: WB5={format_contract(level, strain, dbl)} by {decl} "
                  f"(DD {tricks}T, {ns_wb5:+d}) vs optimal "
                  f"{format_contract(opt_level, opt_strain)} by {opt_decl} ({ns_opt:+d}) "
                  f"→ {imp:+d} IMP")

    if n_deals_scored:
        print(f"\n  Mean IMP loss vs DD-optimal: {total_imp_loss/n_deals_scored:.1f} IMP/deal")

    # Per-position: compare oracle bid vs WBridge5 bid via DD
    print(f"\n  Per-position IMP analysis ({oracle.upper()} vs WBridge5):")
    imp_diffs = []
    big_swings = []

    for pos in positions:
        deal = deals[pos["deal_id"]]
        dd = deal.get("dd_table", {})
        if not dd:
            continue

        oracle_bid = pos[oracle_col]
        wb5_bid = pos["wbridge5_bid"]

        if oracle_bid.upper() == wb5_bid.upper():
            imp_diffs.append(0)
            continue

        # Determine which side is bidding at this position
        auction_len = len(pos["auction"])
        bidder_seat_idx = auction_len % 4
        bidder_side = "NS" if bidder_seat_idx in (0, 2) else "EW"

        # Evaluate each bid's strain via DD
        o_strain = bid_to_strain(oracle_bid)
        w_strain = bid_to_strain(wb5_bid)

        if o_strain is None and w_strain is None:
            imp_diffs.append(0)
            continue

        # For the bidder's side, find the best declarer
        side_seats = ["N", "S"] if bidder_side == "NS" else ["E", "W"]

        def best_dd_score(strain, level_hint=None):
            """Best DD score for the bidder's side in this strain."""
            if strain is None:
                return 0  # Pass
            best = 0
            for seat in side_seats:
                tricks = dd_tricks(deal, strain, seat)
                # Use level hint if available, otherwise find best level
                if level_hint:
                    score = contract_score(level_hint, strain, tricks)
                else:
                    for lv in range(1, 8):
                        s = contract_score(lv, strain, tricks)
                        if s > best:
                            best = s
                            break  # higher levels give less margin
                    continue
                if score > best:
                    best = score
            return best

        # Simple comparison: DD-optimal score in each bid's strain
        o_level = bid_to_level(oracle_bid)
        w_level = bid_to_level(wb5_bid)

        o_score = 0
        w_score = 0

        if o_strain:
            for seat in side_seats:
                tricks = dd_tricks(deal, o_strain, seat)
                if o_level:
                    s = contract_score(o_level, o_strain, tricks)
                    if s > o_score:
                        o_score = s
        if w_strain:
            for seat in side_seats:
                tricks = dd_tricks(deal, w_strain, seat)
                if w_level:
                    s = contract_score(w_level, w_strain, tricks)
                    if s > w_score:
                        w_score = s

        # IMP diff (positive = oracle bid better)
        imp_val = imp_diff(o_score, w_score)
        imp_diffs.append(imp_val)

        if abs(imp_val) >= 3:
            big_swings.append({
                "pos": pos["pos_id"] + 1,
                "deal": pos["deal_id"] + 1,
                "oracle_bid": oracle_bid,
                "wb5_bid": wb5_bid,
                "oracle_score": o_score,
                "wb5_score": w_score,
                "imp": imp_val,
                "hand": pos["hand"],
                "auction": pos["auction_str"],
            })

    if imp_diffs:
        n_diff = sum(1 for x in imp_diffs if x != 0)
        avg = sum(imp_diffs) / len(imp_diffs) if imp_diffs else 0
        avg_abs = sum(abs(x) for x in imp_diffs) / len(imp_diffs) if imp_diffs else 0
        better = sum(1 for x in imp_diffs if x > 0)
        worse = sum(1 for x in imp_diffs if x < 0)
        same = sum(1 for x in imp_diffs if x == 0)

        print(f"\n  Total positions:     {len(imp_diffs)}")
        print(f"  Same bid (IMP=0):    {same} ({100*same/len(imp_diffs):.1f}%)")
        print(f"  Oracle better:       {better} ({100*better/len(imp_diffs):.1f}%)")
        print(f"  WBridge5 better:     {worse} ({100*worse/len(imp_diffs):.1f}%)")
        print(f"  Mean IMP diff:       {avg:+.2f} (positive = {oracle.upper()} better)")
        print(f"  Mean |IMP| per pos:  {avg_abs:.2f}")

    if big_swings:
        print(f"\n  Big swings (|IMP| >= 3):")
        for s in sorted(big_swings, key=lambda x: -abs(x["imp"])):
            direction = "+" if s["imp"] > 0 else ""
            print(f"    #{s['pos']:3d} (Deal {s['deal']}): "
                  f"{oracle.upper()}={s['oracle_bid']} ({s['oracle_score']:+d}) "
                  f"vs WB5={s['wb5_bid']} ({s['wb5_score']:+d}) → {direction}{s['imp']} IMP"
                  f"  | {s['hand']} | {s['auction'] or '(opening)'}")


# ── DD-optimal comparison between oracles ─────────────────────────────


def oracle_comparison_dd(deals: List[Dict], positions: List[Dict]):
    """Compare all three oracles using DD scoring."""
    print("\n" + "=" * 70)
    print("ORACLE DD COMPARISON (bid-level DD evaluation)")
    print("=" * 70)

    oracles = ["bba_bid", "ben_sayc_bid", "wbridge5_bid"]
    names = ["BBA", "Ben", "WB5"]

    for i, (o1, n1) in enumerate(zip(oracles, names)):
        for j, (o2, n2) in enumerate(zip(oracles, names)):
            if i >= j:
                continue

            better_1 = 0
            better_2 = 0
            same = 0
            total_imp = 0

            for pos in positions:
                deal = deals[pos["deal_id"]]
                dd = deal.get("dd_table", {})
                if not dd:
                    continue

                bid1 = pos[o1]
                bid2 = pos[o2]

                if bid1.upper() == bid2.upper():
                    same += 1
                    continue

                # Score each bid
                auction_len = len(pos["auction"])
                bidder_side = "NS" if (auction_len % 4) in (0, 2) else "EW"
                side_seats = ["N", "S"] if bidder_side == "NS" else ["E", "W"]

                def score_bid(bid):
                    s = bid_to_strain(bid)
                    l = bid_to_level(bid)
                    if s is None or l is None:
                        return 0
                    best = 0
                    for seat in side_seats:
                        tricks = dd_tricks(deal, s, seat)
                        sc = contract_score(l, s, tricks)
                        if sc > best:
                            best = sc
                    return best

                s1 = score_bid(bid1)
                s2 = score_bid(bid2)
                imp = imp_diff(s1, s2)

                if imp > 0:
                    better_1 += 1
                elif imp < 0:
                    better_2 += 1
                else:
                    same += 1
                total_imp += imp

            total = len(positions)
            print(f"\n  {n1} vs {n2}:")
            print(f"    Same bid:        {same:3d}/{total}")
            print(f"    {n1} better (DD): {better_1:3d}/{total}")
            print(f"    {n2} better (DD): {better_2:3d}/{total}")
            if total > 0:
                print(f"    Net IMP:         {total_imp:+d} (positive = {n1} better)")
                print(f"    Mean IMP/pos:    {total_imp/total:+.2f}")


# ── LLM evaluation ───────────────────────────────────────────────────


def score_bid_dd(deal: Dict, bid: str, auction: List[str]) -> int:
    """
    Score a bid using DD analysis.

    Returns the DD-based contract score (from the bidder's perspective)
    for the contract implied by this bid.
    """
    dd = deal.get("dd_table", {})
    if not dd:
        return 0

    strain = bid_to_strain(bid)
    level = bid_to_level(bid)
    if strain is None or level is None:
        return 0

    # Determine which side is bidding
    auction_len = len(auction)
    bidder_seat_idx = auction_len % 4
    bidder_side = "NS" if bidder_seat_idx in (0, 2) else "EW"
    side_seats = ["N", "S"] if bidder_side == "NS" else ["E", "W"]

    best = 0
    for seat in side_seats:
        tricks = dd_tricks(deal, strain, seat)
        s = contract_score(level, strain, tricks)
        if s > best:
            best = s
    return best


def run_llm(positions: List[Dict], model_name: str, prompt_id: int,
            n: Optional[int] = None, conv: str = "SAYC") -> List[str]:
    """
    Run LLM on all positions and return predicted bids.
    Caches results to avoid re-running.
    """
    # Import prompt builder from optimize_prompt
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from optimize_prompt import PROMPTS, hand_info
    from bridge_llm_bench.parsers.bid_parser import parse_bid_from_response

    if prompt_id not in PROMPTS:
        print(f"  ERROR: prompt P{prompt_id} not found")
        sys.exit(1)

    # Check cache — include conv in cache key for non-SAYC systems
    conv_safe = conv.replace("/", "-")  # sanitize 2/1 → 2-1
    conv_suffix = f"_{conv_safe}" if conv != "SAYC" else ""
    cache_file = LLM_CACHE_DIR / f"{model_name}_P{prompt_id}{conv_suffix}_N{n or 'all'}.json"
    if cache_file.exists():
        with open(cache_file) as f:
            cached = json.load(f)
        if len(cached) >= len(positions[:n]):
            print(f"  Loaded LLM results from cache ({cache_file.name})")
            return cached

    import google.generativeai as genai
    api_key = os.environ.get("GOOGLE_API_KEY")
    genai.configure(api_key=api_key)
    model_ref = genai.GenerativeModel(model_name=model_name)

    prompt_fn = PROMPTS[prompt_id]
    safety = [
        {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
    ]
    cfg = genai.types.GenerationConfig(
        temperature=0.0, max_output_tokens=50, candidate_count=1)

    target = positions[:n] if n else positions
    bids = []
    for i, pos in enumerate(target):
        prompt = prompt_fn(pos["hand"], pos["auction_str"], conv)
        try:
            resp = model_ref.generate_content(prompt, generation_config=cfg,
                                               safety_settings=safety)
            text = resp.text.strip() if resp.text else "Pass"
            pred = parse_bid_from_response(text)
        except Exception as e:
            pred = "?"
        bids.append(pred)
        print(f"\r  LLM: {i+1}/{len(target)}", end="")

    print()

    # Save cache
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    with open(cache_file, "w") as f:
        json.dump(bids, f)
    print(f"  Cached LLM results to {cache_file.name}")

    return bids


def llm_vs_oracle_dd(deals: List[Dict], positions: List[Dict],
                     llm_bids: List[str], oracle: str, model_name: str):
    """
    Compare LLM bids vs oracle bids using DD scoring.
    Shows exact match, contract-level match, and IMP-based EV.
    """
    oracle_col = ORACLE_COLUMNS[oracle]

    print("\n" + "=" * 70)
    print(f"LLM vs {oracle.upper()} — DD/IMP ANALYSIS")
    print(f"Model: {model_name}")
    print("=" * 70)

    n = len(llm_bids)
    target = positions[:n]

    # ── Exact match + contract-level match ──
    exact = 0
    same_denom = 0
    diff_denom = 0
    pass_vs_bid = 0
    total_diff = 0

    for i, pos in enumerate(target):
        oracle_bid = pos[oracle_col]
        llm_bid = llm_bids[i]
        if llm_bid.upper() == oracle_bid.upper():
            exact += 1
        else:
            total_diff += 1
            ls = bid_to_strain(llm_bid)
            os_ = bid_to_strain(oracle_bid)
            ll = bid_to_level(llm_bid)
            ol = bid_to_level(oracle_bid)
            if ls is None or os_ is None:
                pass_vs_bid += 1
            elif ls == os_ and ll == ol:
                exact += 1  # same contract despite different text?
                total_diff -= 1
            elif ls == os_:
                same_denom += 1
            else:
                diff_denom += 1

    print(f"\n  Bid-level accuracy (N={n}):")
    print(f"    Exact match:             {exact:3d}/{n} ({100*exact/n:.1f}%)")
    print(f"    Different bids:          {total_diff:3d}/{n} ({100*total_diff/n:.1f}%)")
    if total_diff > 0:
        print(f"      Same denomination:     {same_denom:3d}/{total_diff}")
        print(f"      Different denomination:{diff_denom:3d}/{total_diff}")
        print(f"      Pass vs bid:           {pass_vs_bid:3d}/{total_diff}")

    # ── IMP-based DD comparison ──
    print(f"\n  IMP analysis (DD-based):")
    imp_diffs = []
    big_swings = []

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

        # Positive = LLM bid scores same or better than oracle
        imp_val = imp_diff(l_score, o_score)
        imp_diffs.append(imp_val)

        if abs(imp_val) >= 1:
            big_swings.append({
                "pos": pos["pos_id"] + 1,
                "deal": pos["deal_id"] + 1,
                "oracle_bid": oracle_bid,
                "llm_bid": llm_bid,
                "oracle_score": o_score,
                "llm_score": l_score,
                "imp": imp_val,
                "hand": pos["hand"],
                "auction": pos["auction_str"],
            })

    if imp_diffs:
        n_same = sum(1 for x in imp_diffs if x == 0)
        n_better = sum(1 for x in imp_diffs if x > 0)
        n_worse = sum(1 for x in imp_diffs if x < 0)
        mean_imp = sum(imp_diffs) / len(imp_diffs)
        mean_abs = sum(abs(x) for x in imp_diffs) / len(imp_diffs)
        total_imp = sum(imp_diffs)

        print(f"    Total positions:     {len(imp_diffs)}")
        print(f"    Same bid (0 IMP):    {n_same:3d} ({100*n_same/len(imp_diffs):.1f}%)")
        print(f"    LLM better (DD):     {n_better:3d} ({100*n_better/len(imp_diffs):.1f}%)")
        print(f"    Oracle better (DD):  {n_worse:3d} ({100*n_worse/len(imp_diffs):.1f}%)")
        print(f"    Net IMPs:            {total_imp:+d} (positive = LLM better)")
        print(f"    Mean IMP/position:   {mean_imp:+.2f}")
        print(f"    Mean |IMP|/position: {mean_abs:.2f}")

    # Show all swings
    if big_swings:
        print(f"\n  Position-by-position DD swings (|IMP| >= 1):")
        for s in sorted(big_swings, key=lambda x: x["imp"]):
            marker = "+" if s["imp"] > 0 else ""
            print(f"    #{s['pos']:3d} D{s['deal']:2d}: "
                  f"LLM={s['llm_bid']:5s} ({s['llm_score']:+5d}) "
                  f"vs {oracle.upper()}={s['oracle_bid']:5s} ({s['oracle_score']:+5d}) "
                  f"→ {marker}{s['imp']:+d} IMP"
                  f"  | {s['hand']}")

    # ── Per-deal summary ──
    print(f"\n  Per-deal summary:")
    for deal in deals:
        deal_positions = [i for i, p in enumerate(target) if p["deal_id"] == deal["deal_id"]]
        if not deal_positions:
            continue
        deal_imps = [imp_diffs[i] for i in deal_positions]
        deal_correct = sum(1 for i in deal_positions
                          if llm_bids[i].upper() == target[i][oracle_col].upper())
        total_d = len(deal_positions)
        net = sum(deal_imps)
        print(f"    Deal {deal['deal_id']+1:2d}: {deal_correct}/{total_d} exact, "
              f"net {net:+d} IMP "
              f"({'=' * min(abs(net), 20)}{'>' if net > 0 else '<' if net < 0 else ''})")


# ── Main ─────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(description="EV/IMP analysis with DD scoring")
    parser.add_argument("--oracle", choices=["ben", "bba", "wbridge5"], default="bba")
    parser.add_argument("--cache", action="store_true", help="Cache DD tables to disk")
    parser.add_argument("--deals-only", action="store_true", help="Only show deal DD analysis")
    parser.add_argument("--model", default=None,
                        help="LLM model to evaluate (e.g., gemini-2.0-flash-lite)")
    parser.add_argument("--prompt_id", type=int, default=20,
                        help="Prompt strategy ID (default: 20)")
    parser.add_argument("--n", type=int, default=None,
                        help="Number of positions to test (default: all)")
    parser.add_argument("--conv", default="SAYC",
                        choices=["SAYC", "2/1", "ACOL", "PRECISION", "SEF", "POLISH_CLUB"],
                        help="Bidding convention/system (default: SAYC)")
    args = parser.parse_args()

    print("=" * 70)
    print("EV/IMP ANALYSIS WITH DOUBLE-DUMMY SCORING")
    print("=" * 70)

    # Step 1: Load and reconstruct deals
    print(f"\n1. Loading dataset from {DATA_CSV}...")
    deals, positions = load_deals(DATA_CSV)
    print(f"   {len(deals)} deals, {len(positions)} positions")

    # Step 2: Compute DD tables
    print(f"\n2. Computing DD tables...")
    compute_dd_tables(deals, DD_CACHE)  # always cache

    if args.model:
        # LLM mode: run model and compare against oracle
        conv_label = f", conv={args.conv}" if args.conv != "SAYC" else ""
        print(f"\n3. Running LLM ({args.model}, P{args.prompt_id}{conv_label})...")
        llm_bids = run_llm(positions, args.model, args.prompt_id, args.n, conv=args.conv)

        llm_vs_oracle_dd(deals, positions, llm_bids, args.oracle, args.model)
    else:
        # Oracle comparison mode
        analyze_deals(deals, positions, args.oracle)

        if not args.deals_only:
            contract_level_match(deals, positions, args.oracle)
            imp_analysis(deals, positions, args.oracle)
            oracle_comparison_dd(deals, positions)

    print("\n" + "=" * 70)
    print("DONE")
    print("=" * 70)


if __name__ == "__main__":
    main()

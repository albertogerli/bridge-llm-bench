"""
Compare Ben SAYC and saycbridge bids against WBridge5 reference and LLM predictions.

Reads the benchmark records CSV, extracts unique (hand, auction) positions,
queries Ben (via REST API) and saycbridge (via subprocess) for SAYC bids,
and produces a comparison table.

Usage:
    python scripts/compare_oracles.py
"""

import csv
import subprocess
import sys
import json
import time
from pathlib import Path

import requests

# Paths
RECORDS_CSV = Path("results/bench_25_final_records.csv")
SAYCBRIDGE_DIR = Path("/Users/albertogiovannigerli/Desktop/Personale/Bridge/saycbridge")
BEN_URL = "http://localhost:8086"


def hand_to_ben_format(hand_str: str) -> str:
    """
    Convert 'S:AKT64 H:K D:984 C:QT76' to Ben's 'AKT64.K.984.QT76' (S.H.D.C)
    """
    suits = {}
    for part in hand_str.split():
        if ':' in part:
            suit_letter, cards = part.split(':', 1)
            suits[suit_letter] = cards if cards else ''
    # Ben uses S.H.D.C order (dots)
    return f"{suits.get('S','')}.{suits.get('H','')}.{suits.get('D','')}.{suits.get('C','')}"


def hand_to_saycbridge_format(hand_str: str) -> str:
    """
    Convert 'S:AKT64 H:K D:984 C:QT76' to saycbridge's 'QT76.984.K.AKT64' (C.D.H.S)
    """
    suits = {}
    for part in hand_str.split():
        if ':' in part:
            suit_letter, cards = part.split(':', 1)
            suits[suit_letter] = cards if cards else ''
    # saycbridge uses C.D.H.S order (dots)
    return f"{suits.get('C','')}.{suits.get('D','')}.{suits.get('H','')}.{suits.get('S','')}"


def auction_to_ben_ctx(auction_str: str) -> str:
    """
    Convert 'Pass Pass 1S 1NT' to Ben's context format '----1S1N'
    Pass = '--', X = 'Db', XX = 'Rd'
    """
    if not auction_str or auction_str.strip() == '':
        return ''

    bids = auction_str.strip().split()
    ctx = ''
    for bid in bids:
        bid_upper = bid.upper()
        if bid_upper == 'PASS':
            ctx += '--'
        elif bid_upper == 'X':
            ctx += 'Db'
        elif bid_upper == 'XX':
            ctx += 'Rd'
        elif bid_upper.endswith('NT'):
            # 1NT -> 1N, 2NT -> 2N, etc.
            ctx += bid[0] + 'N'
        else:
            ctx += bid[:2]
    return ctx


def auction_to_saycbridge_history(auction_str: str) -> str:
    """
    Convert 'Pass Pass 1S 1NT' to saycbridge's history format 'P,P,1S,1N'
    """
    if not auction_str or auction_str.strip() == '':
        return ''

    bids = auction_str.strip().split()
    parts = []
    for bid in bids:
        bid_upper = bid.upper()
        if bid_upper == 'PASS':
            parts.append('P')
        elif bid_upper == 'X':
            parts.append('X')
        elif bid_upper == 'XX':
            parts.append('XX')
        elif bid_upper.endswith('NT'):
            parts.append(bid[0] + 'N')
        else:
            parts.append(bid)
    return ','.join(parts)


def get_seat_from_auction(auction_str: str) -> str:
    """
    Determine which seat is to bid based on auction length.
    Assumes North is dealer (as in our benchmark data).
    For our data, the dealer varies per game, but looking at the records
    we need to figure out the actual positions.

    Simplification: count bids, seat = bid_count % 4 maps to N,E,S,W
    """
    if not auction_str or auction_str.strip() == '':
        return 'N'  # dealer opens
    bids = auction_str.strip().split()
    seat_idx = len(bids) % 4
    return ['N', 'E', 'S', 'W'][seat_idx]


def query_ben(hand: str, auction: str) -> str:
    """Query Ben SAYC API for a bid."""
    ben_hand = hand_to_ben_format(hand)
    ctx = auction_to_ben_ctx(auction)
    seat = get_seat_from_auction(auction)

    params = {
        'hand': ben_hand,
        'seat': seat,
        'dealer': 'N',  # assume N dealer (we'll refine)
        'vul': '',
        'ctx': ctx,
    }

    try:
        resp = requests.get(f"{BEN_URL}/bid", params=params, timeout=30)
        data = resp.json()
        bid = data.get('bid', '?')
        # Normalize
        if bid.upper() == 'PASS':
            return 'Pass'
        if bid.upper() == 'X' or bid.upper() == 'DB':
            return 'X'
        if bid.upper() == 'XX' or bid.upper() == 'RD':
            return 'XX'
        # Convert 1N -> 1NT
        if len(bid) == 2 and bid[1].upper() == 'N':
            return bid[0] + 'NT'
        return bid.upper()
    except Exception as e:
        return f"ERR:{e}"


def query_saycbridge(hand: str, auction: str) -> str:
    """Query saycbridge for a bid via test-hand script."""
    sayc_hand = hand_to_saycbridge_format(hand)
    history = auction_to_saycbridge_history(auction)

    cmd = ['python3', 'scripts/test-hand', sayc_hand]
    if history:
        cmd.append(history)

    try:
        result = subprocess.run(
            cmd,
            cwd=str(SAYCBRIDGE_DIR),
            capture_output=True,
            text=True,
            timeout=60
        )
        output = result.stdout.strip()
        # Output format is 2 lines:
        #   Line 1: hand pretty print  e.g. "AJ.K732.6543.Q52 (hcp: 10 lp: 10 sp: 10)"
        #   Line 2: the bid  e.g. "P" or "1H" or "2N"
        lines = [l.strip() for l in output.split('\n') if l.strip()]

        if len(lines) >= 2:
            bid = lines[-1]  # Last line is the bid
        elif len(lines) == 1:
            bid = lines[0]
        else:
            return '?'

        # Normalize bid
        bid = bid.strip()
        if bid.upper() in ('P', 'PASS'):
            return 'Pass'
        if bid.upper() == 'X':
            return 'X'
        if bid.upper() == 'XX':
            return 'XX'
        # Convert 1N -> 1NT
        if len(bid) == 2 and bid[1].upper() == 'N':
            return bid[0] + 'NT'
        return bid.upper()
    except subprocess.TimeoutExpired:
        return 'TIMEOUT'
    except Exception as e:
        return f"ERR:{e}"


def extract_unique_positions(csv_path: Path):
    """
    Extract unique (hand, auction, ref_bid) from the SAYC records of one model.
    We pick records from the first model (claude-opus-4-6, SAYC).
    """
    positions = []
    with open(csv_path) as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row['model'] == 'claude-opus-4-6' and row['convention'] == 'SAYC':
                positions.append({
                    'index': int(row['index']),
                    'hand': row['hand'],
                    'auction': row['auction'],
                    'ref_bid': row['reference_bid'],
                })
    return positions


def collect_llm_predictions(csv_path: Path, positions):
    """Collect all LLM predictions for our positions."""
    # Build lookup: (index) -> {model: predicted_bid}
    predictions = {p['index']: {} for p in positions}

    with open(csv_path) as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row['convention'] != 'SAYC':
                continue
            idx = int(row['index'])
            if idx in predictions:
                model = row['model']
                predictions[idx][model] = row['predicted_bid']

    return predictions


def main():
    print("=" * 90)
    print("ORACLE COMPARISON: Ben SAYC vs saycbridge vs WBridge5 reference vs LLM predictions")
    print("=" * 90)

    # Check Ben is running
    try:
        requests.get(f"{BEN_URL}/bid?hand=AKQ.KQJ.AT98.KQ2&seat=N&dealer=N&vul=&ctx=", timeout=5)
        print("[OK] Ben SAYC API is running")
    except:
        print("[ERROR] Ben API not responding on port 8085. Start it first:")
        print("  cd /Users/albertogiovannigerli/Desktop/Personale/Bridge/ben/src")
        print("  python3 gameapi.py --config config/BEN-Sayc.conf --port 8085")
        sys.exit(1)

    # Extract positions
    positions = extract_unique_positions(RECORDS_CSV)
    print(f"[INFO] Found {len(positions)} positions to test")

    # Collect LLM predictions
    llm_preds = collect_llm_predictions(RECORDS_CSV, positions)

    # Query oracles
    results = []
    for i, pos in enumerate(positions):
        print(f"\r  Querying oracles: {i+1}/{len(positions)}", end='')

        ben_bid = query_ben(pos['hand'], pos['auction'])
        sayc_bid = query_saycbridge(pos['hand'], pos['auction'])

        results.append({
            **pos,
            'ben_bid': ben_bid,
            'sayc_bid': sayc_bid,
        })

        time.sleep(0.1)  # Be gentle with APIs

    print()

    # Try to load BBA bids from dataset if available
    bba_dataset = Path("data/ben_sayc_100.csv")
    if bba_dataset.exists():
        bba_bids = {}
        with open(bba_dataset) as f:
            reader = csv.DictReader(f)
            if 'bba_bid' in (reader.fieldnames or []):
                for row in reader:
                    key = (row['hand'], row['auction'])
                    if row.get('bba_bid'):
                        bba_bids[key] = row['bba_bid']
        if bba_bids:
            matched = 0
            for r in results:
                key = (r['hand'], r['auction'])
                if key in bba_bids:
                    r['bba_bid'] = bba_bids[key]
                    matched += 1
            print(f"[INFO] Loaded {matched} BBA bids from {bba_dataset}")

    # Check if BBA data is available
    has_bba = any('bba_bid' in r and r.get('bba_bid', '') for r in results)

    # Print comparison table
    print()
    header = f"{'#':>3} {'Hand':<30} {'Auction':<35} {'WBridge5':>8} {'Ben':>8} {'SAYCBr':>8}"
    if has_bba:
        header += f" {'BBA':>8}"
    header += f" {'Match?':>7}"
    print(header)
    print("-" * (113 if has_bba else 105))

    wb5_ben_match = 0
    wb5_sayc_match = 0
    ben_sayc_match = 0
    wb5_bba_match = 0
    ben_bba_match = 0
    sayc_bba_match = 0
    all_match = 0
    bba_count = 0

    for r in results:
        wb = r['ref_bid']
        bn = r['ben_bid']
        sb = r['sayc_bid']
        bb = r.get('bba_bid', '')

        wb_bn = wb.upper() == bn.upper()
        wb_sb = wb.upper() == sb.upper()
        bn_sb = bn.upper() == sb.upper()

        if wb_bn: wb5_ben_match += 1
        if wb_sb: wb5_sayc_match += 1
        if bn_sb: ben_sayc_match += 1

        if bb:
            bba_count += 1
            if wb.upper() == bb.upper(): wb5_bba_match += 1
            if bn.upper() == bb.upper(): ben_bba_match += 1
            if sb.upper() == bb.upper(): sayc_bba_match += 1

        if wb_bn and wb_sb:
            all_match += 1
            match_str = 'ALL'
        elif wb_bn:
            match_str = 'WB=BN'
        elif wb_sb:
            match_str = 'WB=SC'
        elif bn_sb:
            match_str = 'BN=SC'
        else:
            match_str = 'NONE'

        auction_display = r['auction'] if r['auction'] else '(opening)'
        line = f"{r['index']:>3} {r['hand']:<30} {auction_display:<35} {wb:>8} {bn:>8} {sb:>8}"
        if has_bba:
            line += f" {bb:>8}"
        line += f" {match_str:>7}"
        print(line)

    n = len(results)
    print("-" * (113 if has_bba else 105))
    print(f"\nAgreement rates (N={n}):")
    print(f"  WBridge5 == Ben:       {wb5_ben_match}/{n} ({wb5_ben_match/n*100:.1f}%)")
    print(f"  WBridge5 == saycbridge:{wb5_sayc_match}/{n} ({wb5_sayc_match/n*100:.1f}%)")
    print(f"  Ben == saycbridge:     {ben_sayc_match}/{n} ({ben_sayc_match/n*100:.1f}%)")
    if bba_count > 0:
        print(f"  WBridge5 == BBA:       {wb5_bba_match}/{bba_count} ({wb5_bba_match/bba_count*100:.1f}%)")
        print(f"  Ben == BBA:            {ben_bba_match}/{bba_count} ({ben_bba_match/bba_count*100:.1f}%)")
        print(f"  saycbridge == BBA:     {sayc_bba_match}/{bba_count} ({sayc_bba_match/bba_count*100:.1f}%)")
    print(f"  All three agree:       {all_match}/{n} ({all_match/n*100:.1f}%)")

    # Now show LLM accuracy against each oracle
    models_in_data = set()
    for preds in llm_preds.values():
        models_in_data.update(preds.keys())

    header = f"\n{'Model':<35} {'vs WBridge5':>12} {'vs Ben':>12} {'vs SAYCBr':>12}"
    if has_bba:
        header += f" {'vs BBA':>12}"
    print(header)
    print("-" * (87 if has_bba else 75))

    for model in sorted(models_in_data):
        correct_wb = 0
        correct_ben = 0
        correct_sayc = 0
        correct_bba = 0
        total = 0

        for r in results:
            idx = r['index']
            if model in llm_preds[idx]:
                pred = llm_preds[idx][model]
                total += 1
                if pred.upper() == r['ref_bid'].upper():
                    correct_wb += 1
                if pred.upper() == r['ben_bid'].upper():
                    correct_ben += 1
                if pred.upper() == r['sayc_bid'].upper():
                    correct_sayc += 1
                bb = r.get('bba_bid', '')
                if bb and pred.upper() == bb.upper():
                    correct_bba += 1

        if total > 0:
            line = (f"{model:<35} {correct_wb:>3}/{total} ({correct_wb/total*100:4.0f}%) "
                    f"{correct_ben:>3}/{total} ({correct_ben/total*100:4.0f}%) "
                    f"{correct_sayc:>3}/{total} ({correct_sayc/total*100:4.0f}%)")
            if has_bba:
                line += f" {correct_bba:>3}/{total} ({correct_bba/total*100:4.0f}%)"
            print(line)

    # Save detailed results
    out_path = Path("results/oracle_comparison.csv")
    with open(out_path, 'w', newline='') as f:
        writer = csv.writer(f)
        header = ['index', 'hand', 'auction', 'wbridge5', 'ben_sayc', 'saycbridge']
        if has_bba:
            header.append('bba')
        writer.writerow(header)
        for r in results:
            row = [r['index'], r['hand'], r['auction'], r['ref_bid'], r['ben_bid'], r['sayc_bid']]
            if has_bba:
                row.append(r.get('bba_bid', ''))
            writer.writerow(row)

    print(f"\nDetailed results saved to {out_path}")


if __name__ == '__main__':
    main()

"""
Export test positions in PBN and plain text format for external oracle engines.

Reads positions from the benchmark dataset CSV, exports them so engines like
BBA (Bridge Bidding Analyser) can bid the same positions and return results.

Usage:
    python scripts/export_positions.py
    python scripts/export_positions.py --dataset data/ben_sayc_100.csv --output data/export
"""

import argparse
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

SEATS = ['N', 'E', 'S', 'W']


def get_seat(auction_str: str) -> str:
    """Determine which seat is to bid based on auction length (assumes N dealer)."""
    if not auction_str or auction_str.strip() == '':
        return 'N'
    return SEATS[len(auction_str.strip().split()) % 4]


def hand_to_pbn_partial(hand_str: str, seat: str) -> str:
    """
    Convert 'S:AKJ74 H:Q93 D:K84 C:T6' to PBN deal fragment for one player.
    PBN format: SHDC dot-separated. E.g. 'AKJ74.Q93.K84.T6'
    """
    suits = {}
    for part in hand_str.split():
        if ':' in part:
            s, c = part.split(':', 1)
            suits[s] = c if c else ''
    return f"{suits.get('S', '')}.{suits.get('H', '')}.{suits.get('D', '')}.{suits.get('C', '')}"


def auction_to_pbn(auction_str: str) -> str:
    """
    Convert auction string to PBN Auction format.
    'Pass Pass 1S 1NT' → 'Pass Pass 1S 1NT'
    PBN uses: Pass, 1C..7NT, X (double), XX (redouble)
    """
    if not auction_str or auction_str.strip() == '':
        return ''
    return auction_str.strip()


def export_pbn(records, output_path):
    """Export positions in PBN format."""
    with open(output_path, 'w') as f:
        f.write("% Bridge LLM Bench - Test Positions for Oracle Bidding\n")
        f.write("% Format: PBN (Portable Bridge Notation)\n")
        f.write("% Each board shows one player's hand and the auction up to their turn.\n")
        f.write("% The oracle should provide the next bid.\n\n")

        for i, row in enumerate(records):
            hand = row['hand']
            auction = row['auction']
            seat = get_seat(auction)
            pbn_hand = hand_to_pbn_partial(hand, seat)

            # Build a partial deal string - only the bidder's hand is known
            deal_parts = {s: '...' for s in SEATS}
            deal_parts[seat] = pbn_hand
            # PBN Deal tag starts from first seat listed
            deal_str = f"N:{deal_parts['N']} {deal_parts['E']} {deal_parts['S']} {deal_parts['W']}"

            f.write(f'[Board "{i+1}"]\n')
            f.write(f'[Dealer "N"]\n')
            f.write(f'[Vulnerable "None"]\n')
            f.write(f'[Deal "{deal_str}"]\n')

            # Auction section
            pbn_auction = auction_to_pbn(auction)
            f.write(f'[Auction "N"]\n')
            if pbn_auction:
                f.write(f'{pbn_auction} ')
            f.write('?\n')

            # Add reference bids as comments
            refs = []
            if row.get('wbridge5_bid'):
                refs.append(f"WBridge5={row['wbridge5_bid']}")
            if row.get('ben_sayc_bid') and not row['ben_sayc_bid'].startswith('ERR'):
                refs.append(f"BenSAYC={row['ben_sayc_bid']}")
            if row.get('bba_bid'):
                refs.append(f"BBA={row['bba_bid']}")
            if refs:
                f.write(f'{{Reference: {", ".join(refs)}}}\n')

            f.write('\n')

    print(f"  PBN export: {len(records)} positions → {output_path}")


def export_text(records, output_path):
    """Export positions in simple text format for easy human/tool reading."""
    with open(output_path, 'w') as f:
        f.write("# Bridge LLM Bench - Test Positions\n")
        f.write("# Format: position_id | hand | auction | seat | reference bids\n")
        f.write("# The oracle should provide the next bid for the given hand and auction.\n\n")

        for i, row in enumerate(records):
            hand = row['hand']
            auction = row['auction'] if row['auction'] else '(opening)'
            seat = get_seat(row['auction'])

            refs = []
            if row.get('wbridge5_bid'):
                refs.append(f"WB5={row['wbridge5_bid']}")
            if row.get('ben_sayc_bid') and not row['ben_sayc_bid'].startswith('ERR'):
                refs.append(f"Ben={row['ben_sayc_bid']}")

            ref_str = f" | Refs: {', '.join(refs)}" if refs else ""

            f.write(f"#{i+1:>3} | Seat: {seat} | Hand: {hand} | Auction: {auction}{ref_str}\n")

    print(f"  Text export: {len(records)} positions → {output_path}")


def export_csv(records, output_path):
    """Export positions in CSV format for easy import back."""
    with open(output_path, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['position_id', 'hand', 'auction', 'seat', 'wbridge5_bid', 'ben_sayc_bid', 'bba_bid'])
        for i, row in enumerate(records):
            seat = get_seat(row['auction'])
            writer.writerow([
                i + 1,
                row['hand'],
                row['auction'],
                seat,
                row.get('wbridge5_bid', ''),
                row.get('ben_sayc_bid', ''),
                row.get('bba_bid', ''),
            ])

    print(f"  CSV export: {len(records)} positions → {output_path}")


def main():
    parser = argparse.ArgumentParser(description='Export test positions for external oracles')
    parser.add_argument('--dataset', default='data/ben_sayc_100.csv')
    parser.add_argument('--output', default='data/export', help='Output directory')
    args = parser.parse_args()

    # Load dataset
    records = []
    with open(args.dataset) as f:
        reader = csv.DictReader(f)
        for row in reader:
            records.append(row)

    print(f"Loaded {len(records)} positions from {args.dataset}")

    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Export in all formats
    export_pbn(records, out_dir / 'positions.pbn')
    export_text(records, out_dir / 'positions.txt')
    export_csv(records, out_dir / 'positions_for_oracle.csv')

    print(f"\nDone. Send these files to the BBA author for bidding.")
    print(f"After receiving results, use: python scripts/import_bba_bids.py <results_file>")


if __name__ == '__main__':
    main()

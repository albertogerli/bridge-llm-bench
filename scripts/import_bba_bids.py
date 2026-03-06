"""
Import BBA (Bridge Bidding Analyser) bid results into the benchmark dataset.

Reads bid results from BBA and merges them with the existing dataset CSV,
adding a 'bba_bid' column.

Supported input formats:
  1. CSV with columns: position_id, bba_bid
  2. CSV with columns: hand, auction, bba_bid
  3. Simple text: one bid per line (matched by position order)

Usage:
    python scripts/import_bba_bids.py bba_results.csv
    python scripts/import_bba_bids.py bba_results.csv --dataset data/ben_sayc_100.csv
    python scripts/import_bba_bids.py bba_bids.txt --format text
"""

import argparse
import csv
import sys
from pathlib import Path


def normalize_bid(bid: str) -> str:
    """Normalize bid to standard format."""
    b = bid.strip().upper()
    if b in ('PASS', 'P', '--'):
        return 'Pass'
    if b in ('X', 'DB', 'DBL', 'DOUBLE'):
        return 'X'
    if b in ('XX', 'RD', 'RDBL', 'REDOUBLE'):
        return 'XX'
    if len(b) == 2 and b[1] == 'N':
        return b[0] + 'NT'
    return b


def load_bba_csv(filepath):
    """Load BBA results from CSV. Returns dict: position_id → bid or list of bids."""
    results = {}
    with open(filepath) as f:
        reader = csv.DictReader(f)
        fields = reader.fieldnames

        if 'position_id' in fields and 'bba_bid' in fields:
            # Format 1: position_id, bba_bid
            for row in reader:
                pid = int(row['position_id'])
                results[pid] = normalize_bid(row['bba_bid'])
        elif 'bba_bid' in fields:
            # Format 2: hand, auction, bba_bid (match by order)
            for i, row in enumerate(reader):
                results[i + 1] = normalize_bid(row['bba_bid'])
        else:
            # Try: first column is id, second is bid
            for row in reader:
                vals = list(row.values())
                if len(vals) >= 2:
                    try:
                        pid = int(vals[0])
                        results[pid] = normalize_bid(vals[1])
                    except ValueError:
                        pass

    return results


def load_bba_text(filepath):
    """Load BBA results from text file (one bid per line)."""
    results = {}
    with open(filepath) as f:
        for i, line in enumerate(f):
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            # Handle "1: Pass" or just "Pass" format
            if ':' in line and line.split(':')[0].strip().isdigit():
                pid, bid = line.split(':', 1)
                results[int(pid.strip())] = normalize_bid(bid)
            else:
                results[i + 1] = normalize_bid(line)

    return results


def merge_into_dataset(dataset_path, bba_results, output_path):
    """Merge BBA results into the dataset CSV."""
    rows = []
    with open(dataset_path) as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames)
        for row in reader:
            rows.append(row)

    # Add bba_bid column if not present
    if 'bba_bid' not in fieldnames:
        fieldnames.append('bba_bid')

    # Merge
    matched = 0
    for i, row in enumerate(rows):
        pid = i + 1  # 1-indexed
        if pid in bba_results:
            row['bba_bid'] = bba_results[pid]
            matched += 1
        elif 'bba_bid' not in row:
            row['bba_bid'] = ''

    # Write output
    with open(output_path, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Merged {matched}/{len(rows)} BBA bids into {output_path}")

    if matched < len(rows):
        missing = len(rows) - matched
        print(f"  Warning: {missing} positions have no BBA bid")

    return matched


def main():
    parser = argparse.ArgumentParser(description='Import BBA bid results')
    parser.add_argument('input', help='BBA results file (CSV or text)')
    parser.add_argument('--dataset', default='data/ben_sayc_100.csv',
                        help='Existing benchmark dataset to merge into')
    parser.add_argument('--output', default=None,
                        help='Output path (default: overwrite dataset)')
    parser.add_argument('--format', choices=['csv', 'text'], default='csv',
                        help='Input format: csv (default) or text (one bid per line)')
    args = parser.parse_args()

    # Load BBA results
    if args.format == 'text':
        bba_results = load_bba_text(args.input)
    else:
        bba_results = load_bba_csv(args.input)

    print(f"Loaded {len(bba_results)} BBA bids from {args.input}")

    # Merge
    output = args.output or args.dataset
    merge_into_dataset(args.dataset, bba_results, output)


if __name__ == '__main__':
    main()

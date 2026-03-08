"""
Load deals with full play sequences from OpenSpiel numeric format.

Reuses parsers/data_loader.py for deal parsing, adds play extraction
and DD table computation via endplay.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from ..parsers.data_loader import (
    _split_game_line,
    _parse_deal_interleaved,
    _detect_dealer,
    _find_declarer,
    _format_auction,
    _id2card,
    _decode_hand,
)
from ..parsers.bid_parser import get_bid_from_id
from ..metrics.dd_scoring import parse_final_contract

try:
    from endplay.types import Deal, Denom, Player
    from endplay.dds import calc_dd_table
    HAS_ENDPLAY = True
except ImportError:
    HAS_ENDPLAY = False

SEATS = ["N", "E", "S", "W"]
SEAT_NAMES = {0: "N", 1: "E", 2: "S", 3: "W"}

DENOM_MAP = {
    Denom.clubs: "C", Denom.diamonds: "D",
    Denom.hearts: "H", Denom.spades: "S", Denom.nt: "NT",
} if HAS_ENDPLAY else {}

PLAYER_MAP = {
    Player.north: "N", Player.east: "E",
    Player.south: "S", Player.west: "W",
} if HAS_ENDPLAY else {}


@dataclass
class PlayRecord:
    """A single deal with auction and full play sequence."""
    deal_id: int
    hands: Dict[str, List[str]]       # {'N': ['SA','SK',...], ...}
    hand_strings: Dict[str, str]      # {'N': 'S:AK... H:...', ...}
    hand_pbn: Dict[str, str]          # {'N': 'AK.QJ.T9.876', ...} (PBN per seat)
    dealer: int                        # 0-3
    auction: List[str]                 # ['Pass','1H','Pass',...]
    contract: Optional[Tuple]          # (level, strain, declarer_seat, doubled) or None
    vulnerability: Dict[str, bool]     # {'NS': False, 'EW': False}
    play_cards: List[str]              # ['H3','HA','H5','H2',...] (up to 52 cards)
    dd_table: Dict[str, int] = field(default_factory=dict)  # {'C_N': 7, 'H_S': 10, ...}

    @property
    def declarer_seat(self) -> Optional[str]:
        """Return declarer seat letter, or None if passed out."""
        if self.contract is None:
            return None
        _, _, seat_idx, _ = self.contract
        return SEATS[(self.dealer + seat_idx) % 4]

    @property
    def dummy_seat(self) -> Optional[str]:
        """Return dummy seat letter (declarer's partner)."""
        decl = self.declarer_seat
        if decl is None:
            return None
        idx = SEATS.index(decl)
        return SEATS[(idx + 2) % 4]

    @property
    def opening_leader(self) -> Optional[str]:
        """Return opening leader seat letter (left of declarer)."""
        decl = self.declarer_seat
        if decl is None:
            return None
        idx = SEATS.index(decl)
        return SEATS[(idx + 1) % 4]

    @property
    def contract_str(self) -> str:
        """Human-readable contract string like '4H by S'."""
        if self.contract is None:
            return "Passed Out"
        level, strain, _, doubled = self.contract
        suffix = ("", "X", "XX")[doubled]
        return f"{level}{strain}{suffix} by {self.declarer_seat}"

    def pbn_full(self) -> str:
        """Full PBN deal string for endplay: 'N:spades.hearts.diamonds.clubs ...'."""
        parts = []
        for seat in SEATS:
            parts.append(self.hand_pbn[seat])
        return f"N:{' '.join(parts)}"


def _hand_cards_to_pbn(cards: List[str]) -> str:
    """Convert ['SA','SK','HQ','HJ',...] to PBN format 'AK.QJ...'."""
    by_suit: Dict[str, List[str]] = {"S": [], "H": [], "D": [], "C": []}
    for card in cards:
        suit, rank = card[0], card[1]
        by_suit[suit].append(rank)
    rank_order = "23456789TJQKA"
    parts = []
    for s in "SHDC":
        ranks = sorted(by_suit[s], key=rank_order.index, reverse=True)
        parts.append("".join(ranks))
    return ".".join(parts)


def load_play_records(
    path: str,
    n_games: Optional[int] = None,
    compute_dd: bool = True,
    dd_cache_path: Optional[str] = None,
) -> List[PlayRecord]:
    """
    Load deals with play sequences from OpenSpiel numeric format.

    Parameters
    ----------
    path : str
        Path to test.txt or train.txt
    n_games : int, optional
        Max number of games to load
    compute_dd : bool
        Whether to compute DD tables (requires endplay)
    dd_cache_path : str, optional
        Path to cache DD tables as JSON

    Returns
    -------
    list of PlayRecord
    """
    records = []
    dd_cache = _load_dd_cache(dd_cache_path) if dd_cache_path else {}

    with open(path) as fh:
        for line_num, line in enumerate(fh):
            line = line.strip()
            if not line:
                continue

            try:
                numbers = list(map(int, line.split()))
            except ValueError:
                continue

            if len(numbers) < 56:
                continue

            deal_actions, auction_ids, play_ids = _split_game_line(numbers)
            if len(deal_actions) != 52 or not auction_ids:
                continue

            hands_by_idx = _parse_deal_interleaved(deal_actions)
            dealer = _detect_dealer(hands_by_idx, auction_ids, play_ids)

            # Check if all-pass
            declarer = _find_declarer(auction_ids, dealer)
            if declarer is None:
                continue  # Skip passed-out deals

            # Build hand data
            hands: Dict[str, List[str]] = {}
            hand_strings: Dict[str, str] = {}
            hand_pbn: Dict[str, str] = {}
            for idx in range(4):
                seat = SEATS[idx]
                card_strs = [_id2card(cid) for cid in hands_by_idx[idx]]
                hands[seat] = card_strs
                hand_strings[seat] = _decode_hand(hands_by_idx[idx])
                hand_pbn[seat] = _hand_cards_to_pbn(card_strs)

            # Build auction
            auction = [get_bid_from_id(bid_id) for bid_id in auction_ids]
            auction = [b for b in auction if not b.startswith("?")]

            # Parse contract
            contract = parse_final_contract(auction)
            if contract is None:
                continue

            # Build play sequence
            play_cards = [_id2card(cid) for cid in play_ids] if play_ids else []

            record = PlayRecord(
                deal_id=line_num,
                hands=hands,
                hand_strings=hand_strings,
                hand_pbn=hand_pbn,
                dealer=dealer,
                auction=auction,
                contract=contract,
                vulnerability={"NS": False, "EW": False},  # default nonvul
                play_cards=play_cards,
            )

            # DD table
            cache_key = str(line_num)
            if cache_key in dd_cache:
                record.dd_table = dd_cache[cache_key]
            elif compute_dd and HAS_ENDPLAY:
                record.dd_table = _compute_dd_table(record)
                dd_cache[cache_key] = record.dd_table

            records.append(record)
            if n_games and len(records) >= n_games:
                break

    # Save DD cache
    if dd_cache_path and dd_cache:
        _save_dd_cache(dd_cache_path, dd_cache)

    return records


def _compute_dd_table(record: PlayRecord) -> Dict[str, int]:
    """Compute DD table for a deal using endplay."""
    pbn = record.pbn_full()
    d = Deal(pbn)
    table = calc_dd_table(d)
    dd = {}
    for denom, strain in DENOM_MAP.items():
        for player, seat in PLAYER_MAP.items():
            dd[f"{strain}_{seat}"] = table[denom, player]
    return dd


def _load_dd_cache(path: str) -> Dict:
    """Load DD table cache from JSON."""
    p = Path(path)
    if p.exists():
        with open(p) as f:
            return json.load(f)
    return {}


def _save_dd_cache(path: str, cache: Dict) -> None:
    """Save DD table cache to JSON."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w") as f:
        json.dump(cache, f)

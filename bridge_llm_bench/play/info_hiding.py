"""
Information hiding for bridge card play.

Core safety module: ensures no player ever sees information they shouldn't.
All card play state MUST be built through visible_state() — never pass raw
hand data directly to players or prompts.

Rules:
- A player sees only their own hand (remaining cards)
- Dummy is visible to ALL players AFTER the opening lead
- Before the opening lead, nobody sees dummy
- All completed tricks are visible (cards face up on table)
- Current trick cards played so far are visible
- Defenders never see each other's hands
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

SEATS = ["N", "E", "S", "W"]


@dataclass
class Trick:
    """A completed trick."""
    lead_seat: str
    cards: List[Tuple[str, str]]  # [(seat, card_str), ...]
    winner: str


def visible_state(
    hands: Dict[str, List[str]],
    seat: str,
    declarer: str,
    dummy: str,
    contract: Tuple,
    auction: List[str],
    tricks_played: List[Trick],
    current_trick: List[Tuple[str, str]],
    opening_lead_made: bool,
    vulnerability: Dict[str, bool],
    played_cards: Optional[Dict[str, List[str]]] = None,
) -> dict:
    """
    Build the state visible to a specific seat at this point in play.

    Parameters
    ----------
    hands : dict
        Original full hands {'N': ['SA','SK',...], ...}
    seat : str
        The seat requesting the view ('N','E','S','W')
    declarer : str
        Declarer's seat
    dummy : str
        Dummy's seat
    contract : tuple
        (level, strain, declarer_seat_idx, doubled)
    auction : list of str
        The completed auction
    tricks_played : list of Trick
        Completed tricks
    current_trick : list of (seat, card)
        Cards played in current trick
    opening_lead_made : bool
        Whether the opening lead has been played
    vulnerability : dict
        {'NS': bool, 'EW': bool}
    played_cards : dict, optional
        Cards already played per seat (for computing remaining hand)

    Returns
    -------
    dict with keys:
        my_hand, dummy_hand, dummy_seat, contract, declarer,
        auction, tricks_so_far, current_trick, my_seat,
        is_declarer, is_dummy, partner_seat, vulnerability,
        tricks_won_by_us, tricks_won_by_them, trick_number
    """
    partner = _partner(seat)
    is_declarer = (seat == declarer)
    is_dummy = (seat == dummy)

    # Compute remaining cards in seat's hand
    my_remaining = _remaining_cards(hands[seat], played_cards.get(seat, []) if played_cards else [])

    # Dummy hand: visible only after opening lead
    dummy_remaining = None
    if opening_lead_made:
        dummy_remaining = _remaining_cards(
            hands[dummy],
            played_cards.get(dummy, []) if played_cards else []
        )

    # Count tricks won
    my_side = _side(seat)
    tricks_won_by_us = sum(1 for t in tricks_played if _side(t.winner) == my_side)
    tricks_won_by_them = len(tricks_played) - tricks_won_by_us

    level, strain, _, doubled = contract

    return {
        "my_hand": my_remaining,
        "dummy_hand": dummy_remaining,
        "dummy_seat": dummy,
        "contract": {"level": level, "strain": strain, "doubled": doubled},
        "declarer": declarer,
        "auction": auction,
        "tricks_so_far": [
            {
                "lead": t.lead_seat,
                "cards": [(s, c) for s, c in t.cards],
                "winner": t.winner,
            }
            for t in tricks_played
        ],
        "current_trick": current_trick,
        "my_seat": seat,
        "is_declarer": is_declarer,
        "is_dummy": is_dummy,
        "partner_seat": partner,
        "vulnerability": vulnerability,
        "tricks_won_by_us": tricks_won_by_us,
        "tricks_won_by_them": tricks_won_by_them,
        "trick_number": len(tricks_played) + 1,
    }


def _partner(seat: str) -> str:
    """Return the partner of a seat."""
    idx = SEATS.index(seat)
    return SEATS[(idx + 2) % 4]


def _side(seat: str) -> str:
    """Return 'NS' or 'EW' for a seat."""
    return "NS" if seat in ("N", "S") else "EW"


def _remaining_cards(full_hand: List[str], played: List[str]) -> List[str]:
    """Return cards still in hand (not yet played)."""
    played_set = set(played)
    return [c for c in full_hand if c not in played_set]

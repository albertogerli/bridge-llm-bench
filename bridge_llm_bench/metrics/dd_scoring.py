"""
Double-dummy scoring: IMP conversion, contract scoring, and auction parsing.

Provides bridge duplicate scoring (NS perspective), IMP table conversion,
and utilities to extract the final contract from an auction sequence.
"""

from typing import Tuple, Optional, List

# Standard WBF IMP table (absolute score difference → IMPs)
IMP_TABLE = [
    (20, 0), (50, 1), (90, 2), (130, 3), (170, 4),
    (220, 5), (270, 6), (320, 7), (370, 8), (430, 9),
    (500, 10), (600, 11), (750, 12), (900, 13), (1100, 14),
    (1300, 15), (1500, 16), (1750, 17), (2000, 18), (2250, 19),
    (2500, 20), (3000, 21), (3500, 22), (4000, 23),
]


def imp_diff(score_ns_1: int, score_ns_2: int) -> int:
    """
    Convert a score difference to IMPs using the WBF table.

    Parameters
    ----------
    score_ns_1 : int
        Score from NS perspective for result 1
    score_ns_2 : int
        Score from NS perspective for result 2

    Returns
    -------
    int
        IMP difference (positive = result 1 better for NS)
    """
    diff = score_ns_1 - score_ns_2
    abs_diff = abs(diff)
    sign = 1 if diff >= 0 else -1

    imps = 24  # max
    for threshold, imp_val in IMP_TABLE:
        if abs_diff < threshold:
            imps = imp_val
            break

    return sign * imps


def contract_score(level: int, strain: str, tricks_made: int,
                   vul: bool = False, doubled: int = 0) -> int:
    """
    Compute duplicate bridge score for a contract.

    Parameters
    ----------
    level : int
        Contract level (1-7)
    strain : str
        'C', 'D', 'H', 'S', or 'NT'
    tricks_made : int
        Total tricks won by declarer (0-13)
    vul : bool
        Whether declarer is vulnerable
    doubled : int
        0=undoubled, 1=doubled, 2=redoubled

    Returns
    -------
    int
        Score from declarer's perspective (positive = made, negative = down)
    """
    tricks_needed = level + 6
    overtricks = tricks_made - tricks_needed

    if overtricks < 0:
        # Down
        undertricks = -overtricks
        return _down_score(undertricks, vul, doubled)

    # Made the contract
    # Trick values
    if strain in ('C', 'D'):
        trick_value = 20
    elif strain in ('H', 'S'):
        trick_value = 30
    else:  # NT
        trick_value = 30  # per trick after first

    # Base trick score
    if strain == 'NT':
        base = 40 + (level - 1) * 30
    else:
        base = level * trick_value

    # Apply doubling to base
    base *= (1, 2, 4)[doubled]

    # Game/slam bonuses
    if base >= 100:
        game_bonus = 500 if vul else 300
    else:
        game_bonus = 50

    slam_bonus = 0
    if level == 6:
        slam_bonus = 750 if vul else 500
    elif level == 7:
        slam_bonus = 1500 if vul else 1000

    # Insult bonus for making doubled/redoubled
    insult = (0, 50, 100)[doubled]

    # Overtrick scoring
    if doubled == 0:
        ot_value = trick_value if strain != 'NT' else 30
        ot_score = overtricks * ot_value
    elif doubled == 1:
        ot_score = overtricks * (200 if vul else 100)
    else:  # redoubled
        ot_score = overtricks * (400 if vul else 200)

    return base + game_bonus + slam_bonus + insult + ot_score


def _down_score(undertricks: int, vul: bool, doubled: int) -> int:
    """Compute negative score for going down."""
    if doubled == 0:
        per_trick = 100 if vul else 50
        return -(undertricks * per_trick)

    # Doubled/redoubled
    mult = 2 if doubled == 2 else 1
    if vul:
        # First: 200, subsequent: 300 each
        score = 200 + max(0, undertricks - 1) * 300
    else:
        # First: 100, second+third: 200 each, subsequent: 300 each
        if undertricks == 1:
            score = 100
        elif undertricks <= 3:
            score = 100 + (undertricks - 1) * 200
        else:
            score = 100 + 2 * 200 + (undertricks - 3) * 300

    return -(score * mult)


STRAINS = ['C', 'D', 'H', 'S', 'NT']


def parse_final_contract(auction_bids: List[str]) -> Optional[Tuple[int, str, int, int]]:
    """
    Extract the final contract from an auction sequence.

    Parameters
    ----------
    auction_bids : list of str
        Auction as list of bids ['1S', 'Pass', '2H', 'Pass', 'Pass', 'Pass']

    Returns
    -------
    tuple (level, strain, declarer_seat, doubled) or None
        - level: 1-7
        - strain: 'C','D','H','S','NT'
        - declarer_seat: 0-3 (seat index from dealer)
        - doubled: 0, 1, or 2
        Returns None if auction is all-pass or invalid.
    """
    if not auction_bids:
        return None

    last_contract_bid = None
    last_contract_seat = None
    last_contract_idx = None
    doubled = 0

    for i, bid in enumerate(auction_bids):
        bid_upper = bid.upper().strip()
        if bid_upper in ('PASS', 'P'):
            continue
        if bid_upper == 'XX':
            doubled = 2
            continue
        if bid_upper == 'X':
            doubled = 1
            continue
        # Normal bid
        if len(bid_upper) >= 2 and bid_upper[0].isdigit():
            level = int(bid_upper[0])
            strain = bid_upper[1:]
            if strain in ('C', 'D', 'H', 'S', 'NT') and 1 <= level <= 7:
                last_contract_bid = (level, strain)
                last_contract_seat = i % 4  # seat within deal
                last_contract_idx = i
                doubled = 0  # reset doubling on new bid

    if last_contract_bid is None:
        return None

    level, strain = last_contract_bid

    # Find declarer: first player of the declaring SIDE to bid this strain
    declaring_side = last_contract_seat % 2  # 0=NS side, 1=EW side
    for i, bid in enumerate(auction_bids[:last_contract_idx + 1]):
        bid_upper = bid.upper().strip()
        if bid_upper in ('PASS', 'P', 'X', 'XX'):
            continue
        if len(bid_upper) >= 2 and bid_upper[0].isdigit():
            bid_strain = bid_upper[1:]
            if bid_strain == strain and (i % 4) % 2 == declaring_side:
                return (level, strain, i % 4, doubled)

    # Fallback: declarer is the last bidder
    return (level, strain, last_contract_seat, doubled)


def strain_name(strain: str) -> str:
    """Convert strain code to display name."""
    names = {'C': 'Clubs', 'D': 'Diamonds', 'H': 'Hearts', 'S': 'Spades', 'NT': 'No Trump'}
    return names.get(strain, strain)


def format_contract(level: int, strain: str, doubled: int = 0) -> str:
    """Format contract for display (e.g., '3NT', '4SX', '2HXX')."""
    suffix = ('', 'X', 'XX')[doubled]
    return f"{level}{strain}{suffix}"

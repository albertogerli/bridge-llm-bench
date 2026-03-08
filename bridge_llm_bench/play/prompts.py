"""
LLM prompts for bridge card play.

Three prompt types:
1. opening_lead_prompt — defender on lead, dummy NOT visible
2. declarer_prompt — declarer plays from own hand or dummy
3. defender_prompt — defender after opening lead, dummy visible

Each prompt receives ONLY a visible_state dict — never raw hand data.
This enforces information hiding at the prompt level.
"""

import re
from typing import Dict, List, Optional


def play_prompt(vs: dict, legal_moves: List[str], is_from_dummy: bool) -> str:
    """
    Build the appropriate prompt based on game state.

    Automatically selects opening_lead, declarer, or defender prompt.
    """
    if not vs.get("dummy_hand"):
        # Dummy not visible → opening lead
        return _opening_lead_prompt(vs, legal_moves)
    elif vs["is_declarer"] or is_from_dummy:
        return _declarer_prompt(vs, legal_moves, is_from_dummy)
    else:
        return _defender_prompt(vs, legal_moves)


def _opening_lead_prompt(vs: dict, legal_moves: List[str]) -> str:
    """Prompt for the opening lead. Dummy is NOT visible."""
    contract = vs["contract"]
    contract_str = f"{contract['level']}{contract['strain']}"
    if contract["doubled"] == 1:
        contract_str += "X"
    elif contract["doubled"] == 2:
        contract_str += "XX"

    hand_display = _format_hand(vs["my_hand"])
    auction_str = " ".join(vs["auction"]) if vs["auction"] else "N/A"

    return f"""You are playing bridge as {vs['my_seat']}. You are on opening lead.

Contract: {contract_str} by {vs['declarer']}
Auction: {auction_str}

Your hand:
{hand_display}

Legal cards to lead: {', '.join(legal_moves)}

Choose your opening lead. Consider:
- Lead partner's suit if they bid one
- Against NT: 4th best of your longest suit
- Against suits: top of sequence, or singleton
- Avoid leading declarer's strong suits

Reply with ONLY the card to play (e.g., "H4" for the 4 of hearts)."""


def _declarer_prompt(vs: dict, legal_moves: List[str], is_from_dummy: bool) -> str:
    """Prompt for declarer playing from own hand or dummy."""
    contract = vs["contract"]
    contract_str = f"{contract['level']}{contract['strain']}"

    hand_display = _format_hand(vs["my_hand"])
    dummy_display = _format_hand(vs["dummy_hand"]) if vs["dummy_hand"] else "Not visible"

    playing_from = "dummy" if is_from_dummy else "your hand"
    trick_info = _format_tricks(vs)

    return f"""You are declarer ({vs['my_seat']}) playing {contract_str}.
Dummy is {vs['dummy_seat']}.

Your hand:
{hand_display}

Dummy:
{dummy_display}

{trick_info}

You are playing from {playing_from}.
Legal cards: {', '.join(legal_moves)}

Choose the best card to play. Consider:
- Your contract and tricks needed
- Card combinations between hand and dummy
- Finessing opportunities
- Managing entries between hand and dummy

Reply with ONLY the card to play (e.g., "SA" for the ace of spades)."""


def _defender_prompt(vs: dict, legal_moves: List[str]) -> str:
    """Prompt for defender after opening lead. Dummy visible."""
    contract = vs["contract"]
    contract_str = f"{contract['level']}{contract['strain']}"

    hand_display = _format_hand(vs["my_hand"])
    dummy_display = _format_hand(vs["dummy_hand"]) if vs["dummy_hand"] else "Not visible"

    trick_info = _format_tricks(vs)

    return f"""You are defending as {vs['my_seat']} against {contract_str} by {vs['declarer']}.
Your partner is {vs['partner_seat']}. Dummy is {vs['dummy_seat']}.

Your hand:
{hand_display}

Dummy ({vs['dummy_seat']}):
{dummy_display}

{trick_info}

Legal cards: {', '.join(legal_moves)}

Choose the best card to play. Consider:
- Second hand low, third hand high (usually)
- Return partner's led suit
- Count declarer's winners and find the defense's tricks
- Signal to partner (attitude, count)

Reply with ONLY the card to play (e.g., "DK" for the king of diamonds)."""


def _format_hand(cards: Optional[List[str]]) -> str:
    """Format cards grouped by suit for display."""
    if not cards:
        return "  (empty)"
    by_suit: Dict[str, List[str]] = {"S": [], "H": [], "D": [], "C": []}
    suit_symbols = {"S": "Spades", "H": "Hearts", "D": "Diamonds", "C": "Clubs"}
    for c in cards:
        by_suit[c[0]].append(c[1])
    rank_order = "23456789TJQKA"
    lines = []
    for s in "SHDC":
        ranks = sorted(by_suit[s], key=rank_order.index, reverse=True)
        lines.append(f"  {suit_symbols[s]}: {''.join(ranks) if ranks else '-'}")
    return "\n".join(lines)


def _format_tricks(vs: dict) -> str:
    """Format trick history and current trick for display."""
    parts = []
    parts.append(f"Trick {vs['trick_number']} | Us: {vs['tricks_won_by_us']} tricks, "
                 f"Them: {vs['tricks_won_by_them']} tricks")

    if vs["current_trick"]:
        ct = " → ".join(f"{s}:{c}" for s, c in vs["current_trick"])
        parts.append(f"Current trick: {ct}")

    if vs["tricks_so_far"]:
        # Show last 3 tricks for context
        recent = vs["tricks_so_far"][-3:]
        parts.append("Recent tricks:")
        for t in recent:
            cards_str = " ".join(f"{s}:{c}" for s, c in t["cards"])
            parts.append(f"  Lead: {t['lead']} | {cards_str} | Won: {t['winner']}")

    return "\n".join(parts)


# ── Card parsing from LLM responses ─────────────────────────────────


def parse_card_from_response(response: str, legal_moves: List[str]) -> str:
    """
    Extract a card from LLM response text, validated against legal moves.

    Tries multiple patterns:
    1. Direct match: "SA", "H3"
    2. Written form: "ace of spades" → "SA"
    3. First card-like token in response
    4. Fallback: first legal move

    Parameters
    ----------
    response : str
        Raw LLM response
    legal_moves : list of str
        Legal cards like ['SA','SK','H3',...]

    Returns
    -------
    str
        A card string (guaranteed to be from legal_moves or first legal move)
    """
    if not response:
        return legal_moves[0] if legal_moves else "??"

    # Strip thinking tags
    text = re.sub(r'<think>.*?</think>', '', response, flags=re.DOTALL).strip()
    text_upper = text.upper().strip()

    # Direct match: exact card string
    for move in legal_moves:
        if move == text_upper:
            return move

    # Look for card patterns in text (2-char: suit+rank or rank+suit)
    card_pattern = re.compile(r'\b([SHDC][2-9TJQKA]|[2-9TJQKA][SHDC])\b')
    for match in card_pattern.finditer(text_upper):
        token = match.group(1)
        # Normalize to suit-first
        if token[0] in "23456789TJQKA":
            token = token[1] + token[0]
        if token in legal_moves:
            return token

    # Written form: "ace of spades", "king of hearts", etc.
    rank_words = {
        "ace": "A", "king": "K", "queen": "Q", "jack": "J", "ten": "T",
        "nine": "9", "eight": "8", "seven": "7", "six": "6", "five": "5",
        "four": "4", "three": "3", "two": "2", "deuce": "2",
    }
    suit_words = {
        "spade": "S", "spades": "S", "heart": "H", "hearts": "H",
        "diamond": "D", "diamonds": "D", "club": "C", "clubs": "C",
    }
    text_lower = text.lower()
    for rw, rank in rank_words.items():
        for sw, suit in suit_words.items():
            if rw in text_lower and sw in text_lower:
                card = suit + rank
                if card in legal_moves:
                    return card

    # Fallback
    return legal_moves[0] if legal_moves else "??"

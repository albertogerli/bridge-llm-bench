"""
Play engine: drive trick-by-trick card play with pluggable players.

Uses endplay for deal state management and DD evaluation.
All player interaction goes through info_hiding.visible_state() to ensure
no information leakage.
"""

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

from ..metrics.dd_scoring import contract_score, imp_diff

from .info_hiding import Trick, visible_state, _side

try:
    from endplay.types import Deal, Denom, Player, Card, Rank
    from endplay.dds import solve_board
    HAS_ENDPLAY = True
except ImportError:
    HAS_ENDPLAY = False

SEATS = ["N", "E", "S", "W"]

# Mapping between our string format and endplay enums
SUIT_TO_DENOM = {"C": Denom.clubs, "D": Denom.diamonds,
                 "H": Denom.hearts, "S": Denom.spades} if HAS_ENDPLAY else {}
STRAIN_TO_DENOM = {**SUIT_TO_DENOM, "NT": Denom.nt} if HAS_ENDPLAY else {}

RANK_TO_ENUM = {
    "2": Rank.R2, "3": Rank.R3, "4": Rank.R4, "5": Rank.R5, "6": Rank.R6,
    "7": Rank.R7, "8": Rank.R8, "9": Rank.R9, "T": Rank.RT, "J": Rank.RJ,
    "Q": Rank.RQ, "K": Rank.RK, "A": Rank.RA,
} if HAS_ENDPLAY else {}

DENOM_TO_SUIT = {v: k for k, v in SUIT_TO_DENOM.items()} if HAS_ENDPLAY else {}
ENUM_TO_RANK = {v: k for k, v in RANK_TO_ENUM.items()} if HAS_ENDPLAY else {}

PLAYER_TO_SEAT = {Player.north: "N", Player.east: "E",
                  Player.south: "S", Player.west: "W"} if HAS_ENDPLAY else {}
SEAT_TO_PLAYER = {v: k for k, v in PLAYER_TO_SEAT.items()} if HAS_ENDPLAY else {}


def card_str(card: "Card") -> str:
    """Convert endplay Card to string like 'SA', 'H3'."""
    return DENOM_TO_SUIT[card.suit] + ENUM_TO_RANK[card.rank]


def str_to_card(s: str) -> "Card":
    """Convert string like 'SA' to endplay Card."""
    suit_ch, rank_ch = s[0], s[1]
    return Card(suit=SUIT_TO_DENOM[suit_ch], rank=RANK_TO_ENUM[rank_ch])


@dataclass
class CardPlay:
    """A single card played, with DD evaluation."""
    seat: str
    card: str
    dd_optimal: str          # DD best card at this position
    dd_tricks_after: int     # total declarer tricks expected after this play
    is_mistake: bool         # played card loses tricks vs DD optimal
    from_dummy: bool = False # whether this card was played from dummy


@dataclass
class TrickResult:
    """A completed trick."""
    lead_seat: str
    cards: List[CardPlay]
    winner: str


@dataclass
class PlayResult:
    """Complete result of playing a deal."""
    deal_id: int
    contract_str: str
    declarer: str
    tricks_won_ns: int
    tricks_won_ew: int
    contract_score_actual: int   # actual score
    contract_score_dd: int       # DD optimal score
    imp_diff_vs_dd: int
    tricks: List[TrickResult]
    lead_card: str
    lead_dd_optimal: str
    lead_is_mistake: bool
    n_declarer_mistakes: int
    n_defense_mistakes: int
    total_cards: int


class PlayEngine:
    """
    Engine for playing a bridge deal trick by trick.

    Parameters
    ----------
    record : PlayRecord
        The deal to play
    """

    def __init__(self, record):
        from .data import PlayRecord  # avoid circular
        self.record = record
        self.deal = Deal(record.pbn_full())
        level, strain, _, doubled = record.contract
        self.deal.trump = STRAIN_TO_DENOM[strain]
        # Opening leader is left of declarer
        leader_seat = record.opening_leader
        self.deal.first = SEAT_TO_PLAYER[leader_seat]

        self.declarer = record.declarer_seat
        self.dummy = record.dummy_seat
        self.level = level
        self.strain = strain
        self.doubled = doubled
        self.vul_declarer = record.vulnerability.get(
            "NS" if self.declarer in ("N", "S") else "EW", False
        )

        # Track played cards per seat
        self.played_cards: Dict[str, List[str]] = {s: [] for s in SEATS}
        self.completed_tricks: List[TrickResult] = []
        self.current_trick_cards: List[Tuple[str, str]] = []
        self.current_lead_seat: str = leader_seat
        self.opening_lead_made = False

    def play_deal(self, get_card_fn: Callable) -> PlayResult:
        """
        Play all 13 tricks.

        Parameters
        ----------
        get_card_fn : callable
            Function(seat, visible_state, legal_moves, is_from_dummy) -> card_str.
            Called for each card to play. The engine decides WHICH seat
            to query (skipping dummy — declarer plays for dummy).

        Returns
        -------
        PlayResult
        """
        all_card_plays: List[CardPlay] = []

        for trick_num in range(13):
            trick_cards: List[CardPlay] = []
            lead_seat = self.current_lead_seat

            for card_in_trick in range(4):
                cur_player = PLAYER_TO_SEAT[self.deal.curplayer]
                is_from_dummy = (cur_player == self.dummy)

                # Determine who makes the decision
                deciding_seat = self.declarer if is_from_dummy else cur_player

                # Build visible state
                hand_to_show = cur_player  # show dummy's or own hand
                vs = visible_state(
                    hands=self.record.hands,
                    seat=deciding_seat,
                    declarer=self.declarer,
                    dummy=self.dummy,
                    contract=self.record.contract,
                    auction=self.record.auction,
                    tricks_played=[
                        Trick(t.lead_seat, [(cp.seat, cp.card) for cp in t.cards], t.winner)
                        for t in self.completed_tricks
                    ],
                    current_trick=self.current_trick_cards,
                    opening_lead_made=self.opening_lead_made,
                    vulnerability=self.record.vulnerability,
                    played_cards=self.played_cards,
                )

                # Get legal moves
                legal = self._legal_moves_str()

                # Get DD optimal
                dd_best, dd_tricks = self._dd_optimal()

                # Get the card from the player function
                chosen = get_card_fn(deciding_seat, vs, legal, is_from_dummy)

                # Validate — DD sentinel or illegal card → use DD optimal
                if chosen == DD_SENTINEL or chosen not in legal:
                    chosen = dd_best

                # Compute DD tricks after this play
                self.deal.play(str_to_card(chosen))
                self.played_cards[cur_player].append(chosen)
                self.current_trick_cards.append((cur_player, chosen))

                if not self.opening_lead_made:
                    self.opening_lead_made = True

                # DD tricks for declarer after this play
                # On last card of last trick, no solve needed
                cards_remaining = 52 - sum(len(v) for v in self.played_cards.values())
                if cards_remaining == 0:
                    # All cards played — compute actual result
                    dd_after = dd_tricks  # no mistake possible on forced last card
                else:
                    dd_after = self._dd_declarer_tricks()

                is_mistake = (chosen != dd_best) and (dd_after < dd_tricks)

                cp = CardPlay(
                    seat=cur_player,
                    card=chosen,
                    dd_optimal=dd_best,
                    dd_tricks_after=dd_after,
                    is_mistake=is_mistake,
                    from_dummy=is_from_dummy,
                )
                trick_cards.append(cp)
                all_card_plays.append(cp)

            # Trick complete — determine winner
            winner = PLAYER_TO_SEAT[self.deal.curplayer]
            # After playing 4 cards, curplayer is set to trick winner by endplay

            trick_result = TrickResult(
                lead_seat=lead_seat,
                cards=trick_cards,
                winner=winner,
            )
            self.completed_tricks.append(trick_result)
            self.current_trick_cards = []
            self.current_lead_seat = winner

        # Compute final scores
        tricks_ns = sum(1 for t in self.completed_tricks if t.winner in ("N", "S"))
        tricks_ew = 13 - tricks_ns

        decl_tricks = tricks_ns if self.declarer in ("N", "S") else tricks_ew

        actual_score = contract_score(
            self.level, self.strain, decl_tricks, self.vul_declarer, self.doubled
        )

        # DD optimal tricks for declarer
        dd_key = f"{self.strain}_{self.declarer}"
        dd_tricks_optimal = self.record.dd_table.get(dd_key, decl_tricks)
        dd_score = contract_score(
            self.level, self.strain, dd_tricks_optimal, self.vul_declarer, self.doubled
        )

        # IMP diff (positive = LLM did better than DD, shouldn't happen often)
        # We score from declarer perspective
        imp = imp_diff(actual_score, dd_score)

        # Count mistakes
        lead_play = all_card_plays[0]
        n_decl = sum(1 for cp in all_card_plays
                     if cp.is_mistake and _is_declarer_side(cp.seat, self.declarer))
        n_def = sum(1 for cp in all_card_plays
                    if cp.is_mistake and not _is_declarer_side(cp.seat, self.declarer))

        return PlayResult(
            deal_id=self.record.deal_id,
            contract_str=self.record.contract_str,
            declarer=self.declarer,
            tricks_won_ns=tricks_ns,
            tricks_won_ew=tricks_ew,
            contract_score_actual=actual_score,
            contract_score_dd=dd_score,
            imp_diff_vs_dd=imp,
            tricks=self.completed_tricks,
            lead_card=lead_play.card,
            lead_dd_optimal=lead_play.dd_optimal,
            lead_is_mistake=lead_play.is_mistake,
            n_declarer_mistakes=n_decl,
            n_defense_mistakes=n_def,
            total_cards=len(all_card_plays),
        )

    def _legal_moves_str(self) -> List[str]:
        """Get legal moves as string list."""
        return [card_str(c) for c in self.deal.legal_moves()]

    def _dd_optimal(self) -> Tuple[str, int]:
        """
        Get DD optimal card and expected tricks for declarer's side.

        Returns (best_card_str, declarer_total_tricks)
        """
        result = solve_board(self.deal)
        cards_and_tricks = list(result)
        if not cards_and_tricks:
            legal = self._legal_moves_str()
            return (legal[0] if legal else "??", 0)

        best_card_ep, best_tricks_for_side = cards_and_tricks[0]
        best_card = card_str(best_card_ep)

        # Convert to declarer tricks
        cur_seat = PLAYER_TO_SEAT[self.deal.curplayer]
        completed = len(self.completed_tricks)
        decl_already = sum(1 for t in self.completed_tricks if _is_declarer_side(t.winner, self.declarer))

        if _is_declarer_side(cur_seat, self.declarer):
            decl_total = decl_already + best_tricks_for_side
        else:
            remaining = 13 - completed
            decl_remaining = remaining - best_tricks_for_side
            decl_total = decl_already + decl_remaining

        return best_card, decl_total

    def _dd_declarer_tricks(self) -> int:
        """Get expected DD tricks for declarer from current position."""
        cur_seat = PLAYER_TO_SEAT[self.deal.curplayer]
        completed = len(self.completed_tricks)

        # Check if all tricks are done
        if completed == 13:
            return sum(1 for t in self.completed_tricks if _is_declarer_side(t.winner, self.declarer))

        # Check if mid-trick or start of new trick
        in_trick = len(self.current_trick_cards) > 0 and len(self.current_trick_cards) < 4

        result = solve_board(self.deal)
        cards_and_tricks = list(result)
        if not cards_and_tricks:
            return sum(1 for t in self.completed_tricks if _is_declarer_side(t.winner, self.declarer))

        best_tricks_for_side = cards_and_tricks[0][1]
        decl_already = sum(1 for t in self.completed_tricks if _is_declarer_side(t.winner, self.declarer))

        if _is_declarer_side(cur_seat, self.declarer):
            return decl_already + best_tricks_for_side
        else:
            remaining = 13 - completed
            return decl_already + (remaining - best_tricks_for_side)


def _is_declarer_side(seat: str, declarer: str) -> bool:
    """Check if seat is on declarer's side."""
    return _side(seat) == _side(declarer)


# ── Pluggable player functions ─────────────────────────────────────


DD_SENTINEL = "__DD_OPTIMAL__"


def make_dd_player() -> Callable:
    """Player that always plays DD optimal. Returns sentinel for engine."""
    def dd_player(seat, vs, legal_moves, is_from_dummy):
        return DD_SENTINEL
    return dd_player


def make_reference_player(play_cards: List[str]) -> Callable:
    """Player that replays a recorded play sequence."""
    idx = [0]  # mutable counter

    def reference_player(seat, vs, legal_moves, is_from_dummy):
        if idx[0] < len(play_cards):
            card = play_cards[idx[0]]
            idx[0] += 1
            return card
        return legal_moves[0]
    return reference_player


def make_llm_player(client, model: str, prompt_fn: Callable, parse_fn: Callable) -> Callable:
    """
    Player that queries an LLM for each card.

    Parameters
    ----------
    client : BaseClient
        LLM client
    model : str
        Model name
    prompt_fn : callable
        Function(visible_state, legal_moves, is_from_dummy) -> prompt_str
    parse_fn : callable
        Function(response_text, legal_moves) -> card_str
    """
    def llm_player(seat, vs, legal_moves, is_from_dummy):
        prompt = prompt_fn(vs, legal_moves, is_from_dummy)
        response_text, _ = client.get_completion(prompt)
        card = parse_fn(response_text, legal_moves)
        if card not in legal_moves:
            # Retry with explicit legal move list
            retry_prompt = (
                f"{prompt}\n\nYour previous answer was invalid. "
                f"You MUST play one of: {', '.join(legal_moves)}"
            )
            response_text, _ = client.get_completion(retry_prompt)
            card = parse_fn(response_text, legal_moves)
        return card
    return llm_player


def make_human_player() -> Callable:
    """Player that prompts for input in terminal."""
    def human_player(seat, vs, legal_moves, is_from_dummy):
        _display_state_terminal(vs, is_from_dummy)
        while True:
            raw = input(f"  Your card ({', '.join(legal_moves)}): ").strip().upper()
            if raw in legal_moves:
                return raw
            # Try matching partial (e.g., "3" when only one 3 exists)
            matches = [m for m in legal_moves if raw in m]
            if len(matches) == 1:
                return matches[0]
            print(f"  Invalid. Choose from: {', '.join(legal_moves)}")
    return human_player


def _display_state_terminal(vs: dict, is_from_dummy: bool):
    """Print visible state for terminal interactive mode."""
    contract = vs["contract"]
    print(f"\n{'='*50}")
    print(f"Contract: {contract['level']}{contract['strain']} | "
          f"Declarer: {vs['declarer']} | Trick {vs['trick_number']}")
    print(f"Score: Us {vs['tricks_won_by_us']} - Them {vs['tricks_won_by_them']}")
    print(f"{'='*50}")

    if vs["current_trick"]:
        print("Current trick:", " ".join(f"{s}:{c}" for s, c in vs["current_trick"]))

    hand_label = "Dummy" if is_from_dummy else "Your hand"
    hand = vs["dummy_hand"] if is_from_dummy else vs["my_hand"]
    if hand:
        print(f"{hand_label}: {_format_hand_display(hand)}")

    if vs["dummy_hand"] and not is_from_dummy:
        print(f"Dummy ({vs['dummy_seat']}): {_format_hand_display(vs['dummy_hand'])}")


def _format_hand_display(cards: List[str]) -> str:
    """Format card list for display, grouped by suit."""
    by_suit: Dict[str, List[str]] = {"S": [], "H": [], "D": [], "C": []}
    for c in cards:
        by_suit[c[0]].append(c[1])
    rank_order = "23456789TJQKA"
    parts = []
    for s in "SHDC":
        ranks = sorted(by_suit[s], key=rank_order.index, reverse=True)
        if ranks:
            parts.append(f"{s}:{''.join(ranks)}")
    return " ".join(parts)

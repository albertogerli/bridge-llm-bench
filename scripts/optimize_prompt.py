"""
Rapid prompt optimization for Gemini Flash Lite against Ben SAYC reference.

Reads positions from data/ben_sayc_100.csv, tests different prompt strategies,
reports accuracy against Ben SAYC bids.

Usage:
    python scripts/optimize_prompt.py --prompt_id 0 --n 50
"""

import argparse
import csv
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
from bridge_llm_bench.clients import get_client
from bridge_llm_bench.parsers.bid_parser import parse_bid_from_response
from bridge_llm_bench.utils.config import CONVENTIONS, SAYC_KNOWLEDGE, SYSTEM_KNOWLEDGE


# ── Prompt strategies ────────────────────────────────────────────────

_HCP = {'A': 4, 'K': 3, 'Q': 2, 'J': 1}


def hand_info(hand: str) -> str:
    suits = []
    hcp = 0
    for part in hand.split():
        cards = part.split(':')[1] if ':' in part else part
        suits.append(len(cards))
        hcp += sum(_HCP.get(c, 0) for c in cards)
    dist = '='.join(str(n) for n in suits)
    return f"{hcp} HCP, {dist}"


PROMPTS = {}

# P0: Current knowledge v2 (baseline - 56%)
PROMPTS[0] = lambda hand, auction, conv: (
    f"You are an expert contract bridge player. {CONVENTIONS[conv]}\n"
    f"{SAYC_KNOWLEDGE}\n"
    f"Your hand: {hand}\n"
    f"Auction so far: {auction if auction else 'None'}\n"
    "Your call? Respond with EXACTLY one bid: "
    "Pass, X, XX, 1C, 1D, 1H, 1S, 1NT, 2C, 2D, 2H, 2S, 2NT, "
    "3C, 3D, 3H, 3S, 3NT, 4C, 4D, 4H, 4S, 4NT, 5C, 5D, 5H, 5S, 5NT, "
    "6C, 6D, 6H, 6S, 6NT, 7C, 7D, 7H, 7S, 7NT.\n"
    "Output ONLY the bid, nothing else."
)

# P1: Knowledge + HCP pre-computed + explicit reasoning hints
PROMPTS[1] = lambda hand, auction, conv: (
    f"You are an expert contract bridge player. {CONVENTIONS[conv]}\n"
    f"{SAYC_KNOWLEDGE}\n"
    f"Your hand: {hand} ({hand_info(hand)})\n"
    f"Auction so far: {auction if auction else 'None (you are the opener)'}\n"
    "Analyze: count your HCP, check suit lengths, consider the auction context.\n"
    "Your call? Respond with EXACTLY one bid: "
    "Pass, X, XX, 1C, 1D, 1H, 1S, 1NT, 2C, 2D, 2H, 2S, 2NT, "
    "3C, 3D, 3H, 3S, 3NT, 4C, 4D, 4H, 4S, 4NT, 5C, 5D, 5H, 5S, 5NT, "
    "6C, 6D, 6H, 6S, 6NT, 7C, 7D, 7H, 7S, 7NT.\n"
    "Output ONLY the bid, nothing else."
)

# P2: Structured decision + compact knowledge + competitive emphasis
PROMPTS[2] = lambda hand, auction, conv: (
    f"You are an expert SAYC bridge bidder.\n"
    "SAYC RULES:\n"
    "OPENINGS: 12+ HCP to open. 5+ card major→open 1H/1S. No 5-card major→open longest minor "
    "(1C with 3-3, 1D with 4-4). 15-17 balanced→1NT. 20-21→2NT. 22+→2C. "
    "Weak 2 (2D/2H/2S)=6-10 HCP+good 6-card suit. Preempt 3-level=7-card suit.\n"
    "RESPONSES to 1M: 3+ trump: 6-9→simple raise, 10-12→jump raise, 13+→2NT(Jacoby). "
    "New suit at 1-level=4+ cards(forcing). 1NT=6-10(not forcing).\n"
    "RESPONSES to 1m: bid 4-card majors up the line. Raise minor with 5+ support.\n"
    "RESPONSES to 1NT: Stayman 2C(8+ with 4M), transfers 2D→H 2H→S.\n"
    "COMPETITIVE: Overcall=8-16 HCP+5 cards. 1NT overcall=15-18+stopper. "
    "Takeout X=12+ support for unbid suits. Negative X thru 3S.\n"
    "IMPORTANT: In competitive auctions, DO NOT pass with 8+ HCP unless you have no good bid. "
    "With a fit for partner's suit, compete to the appropriate level.\n"
    f"\nYour hand: {hand} ({hand_info(hand)})\n"
    f"Auction: {auction if auction else 'None (you open)'}\n"
    "What is your ONE bid? Answer with just the bid."
)

# P3: Few-shot examples + knowledge
PROMPTS[3] = lambda hand, auction, conv: (
    f"You are an expert SAYC bridge bidder. {CONVENTIONS[conv]}\n"
    f"{SAYC_KNOWLEDGE}\n"
    "\nExamples:\n"
    "Hand: S:AKJ74 H:Q93 D:K84 C:T6 (15 HCP, 5=3=3=2) | Auction: None → 1S (5-card major)\n"
    "Hand: S:Q84 H:K72 D:AJ65 C:K93 (14 HCP, 3=3=4=3) | Auction: None → 1D (no 5M, longest minor)\n"
    "Hand: S:KJ5 H:AQ4 D:KT93 C:Q72 (16 HCP, 3=3=4=3) | Auction: None → 1NT (15-17 balanced)\n"
    "Hand: S:97 H:KJ984 D:T5 C:QJ32 (8 HCP, 2=5=2=4) | Auction: None → Pass (<12 HCP)\n"
    "Hand: S:J8742 H:3 D:K5 C:AQT96 (11 HCP, 5=1=2=5) | Auction: 1H → 1S (overcall, 5+ suit 8-16 HCP)\n"
    "Hand: S:AK4 H:AQT3 D:5 C:J8742 (16 HCP, 3=4=1=5) | Auction: None → 1C (5 clubs, open longest minor)\n"
    f"\nYour hand: {hand}\n"
    f"Auction so far: {auction if auction else 'None'}\n"
    "Your bid? Output ONLY the bid."
)

# P4: Ultra-concise + key rules only + decision tree hints
PROMPTS[4] = lambda hand, auction, conv: (
    "Expert SAYC bridge bidder. Rules:\n"
    "- Open 12+ HCP: 5+M→1H/1S, else longest minor, 15-17 bal→1NT, 20-21→2NT, 22+→2C\n"
    "- Weak 2=6-10 HCP+6-card suit. Preempt 3x=7-card suit\n"
    "- Respond to 1M: raise w/3+trump, new suit forcing, 1NT=6-10\n"
    "- Respond to 1NT: 2C=Stayman(8+,4M), 2D/2H=transfer, 0-7→pass\n"
    "- Overcall=8-16+5cards, 1NT overcall=15-18+stopper, TakeoutX=12+\n"
    "- With fit for partner, compete! Don't sell out cheaply\n"
    f"\nHand: {hand} ({hand_info(hand)})\n"
    f"Auction: {auction if auction else '(opening)'}\n"
    "Bid:"
)

# P5: Knowledge v2 + competitive emphasis + "do not pass" heuristic
PROMPTS[5] = lambda hand, auction, conv: (
    f"You are an expert contract bridge player. {CONVENTIONS[conv]}\n"
    f"{SAYC_KNOWLEDGE}\n"
    "CRITICAL COMPETITIVE GUIDELINES:\n"
    "- With 8+ HCP and a 5+ card suit, prefer bidding over passing in competitive auctions.\n"
    "- With support for partner's suit (3+ cards), compete to the level of your fit.\n"
    "- Open the LONGEST minor (not a 4-card major) when you have no 5-card major.\n"
    "- With a void or singleton and distributional hand, be aggressive.\n"
    "- In balancing seat (two passes to you), bid with 2-3 fewer HCP than normal.\n"
    f"\nYour hand: {hand}\n"
    f"Auction so far: {auction if auction else 'None'}\n"
    "Your call? Respond with EXACTLY one bid: "
    "Pass, X, XX, 1C, 1D, 1H, 1S, 1NT, 2C, 2D, 2H, 2S, 2NT, "
    "3C, 3D, 3H, 3S, 3NT, 4C, 4D, 4H, 4S, 4NT, 5C, 5D, 5H, 5S, 5NT, "
    "6C, 6D, 6H, 6S, 6NT, 7C, 7D, 7H, 7S, 7NT.\n"
    "Output ONLY the bid, nothing else."
)

# P6: Few-shot with competitive examples + knowledge
PROMPTS[6] = lambda hand, auction, conv: (
    "You are an expert SAYC bridge bidder.\n"
    "SAYC KEY RULES:\n"
    "OPEN: 12+HCP. 5+card major→1H/1S. No 5M→longest minor(1C w/3-3, 1D w/4-4). "
    "15-17 bal→1NT. 20-21→2NT. 22+→2C. Weak2=6-10+good 6-card. 3x preempt=7-card.\n"
    "RESPOND 1M: 6-9+3trump→raise. 10-12→jump raise. 13+→2NT Jacoby. New suit 1-level=forcing.\n"
    "RESPOND 1m: 4-card majors up the line. 1NT=6-10 no 4M.\n"
    "RESPOND 1NT: 2C Stayman(8+,4M). 2D=transfer H. 2H=transfer S. 0-7→pass.\n"
    "COMPETITIVE: Overcall=8-16+5cards. 1NT over=15-18+stopper. TakeoutX=12+unbid suits. "
    "NegativeX thru 3S. With fit, compete to your level. Balance with 2-3 fewer HCP.\n"
    "\nExamples:\n"
    "S:AKJ74 H:Q93 D:K84 C:T6 | Auction: None → 1S\n"
    "S:KJ5 H:AQ4 D:KT93 C:Q72 | Auction: None → 1NT\n"
    "S:97 H:KJ984 D:T5 C:QJ32 | Auction: None → Pass\n"
    "S:AK4 H:AQT3 D:5 C:J8742 | Auction: None → 1C\n"
    "S:J8742 H:3 D:K5 C:AQT96 | Auction: 1H → 1S\n"
    "S:KQ84 H:65 D:AJ93 C:Q72 | Auction: 1C Pass → 1S\n"
    "S:T3 H:84 D:KQJ982 C:KQT | Auction: 1H → 2D\n"
    f"\nYour hand: {hand}\n"
    f"Auction: {auction if auction else 'None'}\n"
    "Your bid:"
)


# P7: Chain-of-thought with more tokens - reason then bid
PROMPTS[7] = lambda hand, auction, conv: (
    "You are an expert SAYC bridge bidder. Think step by step.\n"
    f"{SAYC_KNOWLEDGE}\n"
    f"\nHand: {hand} ({hand_info(hand)})\n"
    f"Auction: {auction if auction else 'None (you open)'}\n"
    "\nStep 1: Count HCP and note suit lengths.\n"
    "Step 2: Determine your position (opener/responder/overcaller/competitive).\n"
    "Step 3: Apply SAYC rules for this situation.\n"
    "Step 4: State your bid.\n"
    "\nYour analysis and bid:"
)

# P8: Massive few-shot covering all error categories
PROMPTS[8] = lambda hand, auction, conv: (
    "You are an expert SAYC bridge bidder.\n"
    f"{SAYC_KNOWLEDGE}\n"
    "\nExamples of correct SAYC bidding:\n"
    "OPENING BIDS:\n"
    "S:AKJ74 H:Q93 D:K84 C:T6 (14 HCP, 5=3=3=2) | Auction: None → 1S (5-card major)\n"
    "S:AK4 H:AQT3 D:5 C:J8742 (16 HCP, 3=4=1=5) | Auction: None → 1C (5 clubs, no 5-card major→longest minor)\n"
    "S:Q84 H:K72 D:AJ65 C:K93 (14 HCP, 3=3=4=3) | Auction: None → 1D (no 5M→longest minor, 4D>3C)\n"
    "S:KJ5 H:AQ4 D:KT93 C:Q72 (16 HCP, 3=3=4=3) | Auction: None → 1NT (15-17 balanced)\n"
    "S:97 H:KJ984 D:T5 C:QJ32 (8 HCP) | Auction: None → Pass (under 12 HCP)\n"
    "S:9862 H:KJ9652 D:74 C:3 (5 HCP, 6 hearts) | Auction: None → Pass (too weak for weak 2, only 5 HCP)\n"
    "S:54 H: D:AQ953 C:AKQJT6 (16 HCP, void H, 6C+5D) | Auction: None → 1C (longest suit)\n"
    "\nRESPONSES:\n"
    "S:KQ84 H:65 D:AJ93 C:Q72 (12 HCP, 4S) | Auction: 1C Pass → 1S (new suit forcing, bid 4-card majors up)\n"
    "S:J9742 H:83 D:QT5 C:K62 (6 HCP, 5S) | Auction: 1S Pass → 2S (simple raise with 3+ trump, 6-9 HCP)\n"
    "S:K84 H:A3 D:QJ972 C:T63 (10 HCP) | Auction: 1S Pass → 3S (limit raise, 10-12 with 3+ trump)\n"
    "\nCOMPETITIVE:\n"
    "S:J8742 H:3 D:K5 C:AQT96 (11 HCP, 5S) | Auction: 1H → 1S (overcall with 5+ suit, 8-16 HCP)\n"
    "S:T3 H:84 D:KQJ982 C:KQT (10 HCP, 6D) | Auction: 1H → Pass (10 HCP enough but at 2-level need good suit AND values)\n"
    "S:QJ75 H:7 D:AT63 C:A965 (11 HCP) | Auction: 1H Pass → X (takeout double=support for unbid suits)\n"
    "S:AK4 H:AQT3 D:5 C:J8742 (16 HCP) | Auction: Pass 1H Pass 2C X → 3C (show club support over double)\n"
    f"\nYour hand: {hand}\n"
    f"Auction: {auction if auction else 'None'}\n"
    "Your bid? Output ONLY the bid."
)

# P9: P3 base + position-aware + seat info
PROMPTS[9] = lambda hand, auction, conv: (
    f"You are an expert SAYC bridge bidder. {CONVENTIONS[conv]}\n"
    f"{SAYC_KNOWLEDGE}\n"
    "\nExamples:\n"
    "S:AKJ74 H:Q93 D:K84 C:T6 | Auction: None → 1S\n"
    "S:AK4 H:AQT3 D:5 C:J8742 | Auction: None → 1C\n"
    "S:KJ5 H:AQ4 D:KT93 C:Q72 | Auction: None → 1NT\n"
    "S:97 H:KJ984 D:T5 C:QJ32 | Auction: None → Pass\n"
    "S:J8742 H:3 D:K5 C:AQT96 | Auction: 1H → 1S\n"
    "S:KQ84 H:65 D:AJ93 C:Q72 | Auction: 1C Pass → 1S\n"
    f"\nPosition: You are {'opener' if not auction else 'seat ' + str(len(auction.split())+1) + ' to bid'}. "
    f"{'You have already heard ' + str(len(auction.split())) + ' bids.' if auction else 'You bid first.'}\n"
    f"Your hand: {hand} ({hand_info(hand)})\n"
    f"Auction so far: {auction if auction else 'None'}\n"
    "Your bid? Output ONLY the bid."
)

# P10: Focused on fixing passivity - stronger competitive instruct
PROMPTS[10] = lambda hand, auction, conv: (
    f"You are an expert SAYC bridge bidder. {CONVENTIONS[conv]}\n"
    f"{SAYC_KNOWLEDGE}\n"
    "\nCRITICAL BIDDING PRINCIPLES:\n"
    "1. OPEN longest minor when no 5-card major (1C with 3-3, 1D with 4-4, NEVER open a 4-card major)\n"
    "2. In COMPETITIVE auctions: with 8+ HCP and a 5+ card suit, PREFER BIDDING over passing\n"
    "3. With support for partner (3+ cards), raise to the level of your combined trumps\n"
    "4. After partner opens and you have 6+ HCP: you MUST respond (do NOT pass)\n"
    "5. With distributional hands (void/singleton), be MORE aggressive\n"
    "6. In BALANCING position (it would be passed out): bid with 2-3 fewer HCP than normal\n"
    "7. Weak 2 requires good 6-card suit AND 6-10 HCP. Do NOT open weak 2 with 5 HCP\n"
    "\nExamples:\n"
    "S:AKJ74 H:Q93 D:K84 C:T6 | None → 1S\n"
    "S:AK4 H:AQT3 D:5 C:J8742 | None → 1C (longest minor, NOT 1H)\n"
    "S:KJ5 H:AQ4 D:KT93 C:Q72 | None → 1NT\n"
    "S:97 H:KJ984 D:T5 C:QJ32 | None → Pass\n"
    "S:J8742 H:3 D:K5 C:AQT96 | 1H → 1S\n"
    "S:AK4 H:AQT3 D:5 C:J8742 | P 1H P 2C X → 3C\n"
    "S:T3 H:84 D:KQJ982 C:KQT | P 1H P 2C X P 2S X P P → 3D\n"
    f"\nYour hand: {hand}\n"
    f"Auction: {auction if auction else 'None'}\n"
    "Your bid:"
)


# P14: LOTT (Law of Total Tricks) + vulnerability + competitive guidance
PROMPTS[14] = lambda hand, auction, conv: (
    f"You are an expert SAYC bridge bidder. {CONVENTIONS[conv]}\n"
    f"{SAYC_KNOWLEDGE}\n"
    "\nLAW OF TOTAL TRICKS (LOTT) - KEY COMPETITIVE PRINCIPLE:\n"
    "In competitive auctions, bid to the level of your side's total trumps:\n"
    "- 8 combined trumps → compete to the 2-level (8 tricks)\n"
    "- 9 combined trumps → compete to the 3-level (9 tricks)\n"
    "- 10 combined trumps → compete to the 4-level (10 tricks)\n"
    "How to count: your trumps + partner's likely trumps (from their bid).\n"
    "Partner opened 1M = 5+ trumps. Partner raised = 3+ trumps.\n"
    "With extra shape (void/singleton), add 1 level.\n"
    "\nVULNERABILITY: Neither side vulnerable (standard risk).\n"
    "- Non-vul: can compete more freely (down 1 costs only 50)\n"
    "- The cost of letting opponents play at a low level undoubled is often higher\n"
    "  than going down 1 non-vulnerable\n"
    "\nCOMPETITIVE DECISION GUIDE:\n"
    "- Partner opened, opponents overcall: with 8+ HCP and fit, COMPETE (raise/double)\n"
    "- Opponents bid, you have a good suit: OVERCALL if you can at the 1-level,\n"
    "  need more (10+ HCP + good suit) at the 2-level\n"
    "- In balancing seat (two passes): bid with 2-3 fewer HCP than normal\n"
    "- NEVER sell out at the 1 or 2 level when you have a fit for partner\n"
    "\nExamples:\n"
    "S:AKJ74 H:Q93 D:K84 C:T6 (14 HCP) | None → 1S\n"
    "S:AK4 H:AQT3 D:5 C:J8742 (16 HCP) | None → 1C (longest minor, not 4-card H)\n"
    "S:KJ5 H:AQ4 D:KT93 C:Q72 (16 HCP) | None → 1NT\n"
    "S:97 H:KJ984 D:T5 C:QJ32 (8 HCP) | None → Pass\n"
    "S:Q52 H:6543 D:K732 C:AJ (10 HCP, 3 spades) | P P 1S 1NT → X "
    "(competitive X: 10 HCP + 3-card support for partner's S, LOTT says 8+ trumps)\n"
    "S:97 H:A9872 D:AJ65 C:43 (9 HCP) | P P 1S 1NT P → 2D "
    "(compete with 5-card suit, don't let them play 1NT)\n"
    "S:J8742 H:3 D:K5 C:AQT96 (11 HCP) | 1H → 1S\n"
    "S:QJ75 H:7 D:AT63 C:A965 (11 HCP) | 1H P → 1S (show spades, new suit forcing)\n"
    "S:AK4 H:AQT3 D:5 C:J8742 (16 HCP) | P 1H P 2C X → 3C (support partner's C)\n"
    f"\nYour hand: {hand} ({hand_info(hand)})\n"
    f"Auction: {auction if auction else 'None'}\n"
    "Your bid:"
)

# P15: LOTT + P9 position-aware + voting-optimized (shorter for speed)
PROMPTS[15] = lambda hand, auction, conv: (
    f"Expert SAYC bidder. {CONVENTIONS[conv]}\n"
    "RULES: Open 12+: 5+M→1H/1S, no 5M→longest minor, 15-17bal→1NT, 20-21→2NT, 22+→2C. "
    "Weak2=6-10+good 6-card. Respond 1M: raise w/3+trump, new suit forcing. "
    "Respond 1NT: 2C Stayman, 2D/2H transfers. "
    "Overcall=8-16+5card. TakeoutX=12+.\n"
    "\nLAW OF TOTAL TRICKS:\n"
    "Compete to the level of your combined trumps:\n"
    "8 trumps→2-level, 9→3-level, 10→4-level.\n"
    "Partner's 1M=5+ trumps. Your 3-card support=8 total→compete to 2.\n"
    "Your 4-card support=9 total→compete to 3. Void/singleton→add 1.\n"
    "NON-VUL: compete freely, down 1=only 50 points.\n"
    "\nExamples:\n"
    "S:AKJ74 H:Q93 D:K84 C:T6|→1S. "
    "S:AK4 H:AQT3 D:5 C:J8742|→1C. "
    "S:KJ5 H:AQ4 D:KT93 C:Q72|→1NT. "
    "S:97 H:KJ984 D:T5 C:QJ32|→Pass. "
    "S:Q52 H:6543 D:K732 C:AJ|P P 1S 1NT→X(3S support, compete). "
    "S:97 H:A9872 D:AJ65 C:43|P P 1S 1NT P→2D. "
    "S:QJ75 H:7 D:AT63 C:A965|1H P→1S. "
    "S:AK4 H:AQT3 D:5 C:J8742|P 1H P 2C X→3C\n"
    f"\n{hand} ({hand_info(hand)})"
    f"|{auction if auction else ''}→"
    "Your bid:"
)

# P11: Best-of-breed - P9 structure + P8 examples + error-targeted examples
PROMPTS[11] = lambda hand, auction, conv: (
    f"You are an expert SAYC bridge bidder. {CONVENTIONS[conv]}\n"
    f"{SAYC_KNOWLEDGE}\n"
    "\nKey examples:\n"
    "S:AKJ74 H:Q93 D:K84 C:T6 (14 HCP) | None → 1S (5-card major)\n"
    "S:AK4 H:AQT3 D:5 C:J8742 (16 HCP) | None → 1C (5C, no 5M→longest minor NOT 4-card H)\n"
    "S:KJ5 H:AQ4 D:KT93 C:Q72 (16 HCP) | None → 1NT (15-17 balanced)\n"
    "S:97 H:KJ984 D:T5 C:QJ32 (8 HCP) | None → Pass\n"
    "S:9862 H:KJ9652 D:74 C:3 (5 HCP) | None → Pass (too weak even for weak 2)\n"
    "S:54 H: D:AQ953 C:AKQJT6 (16 HCP) | None → 1C\n"
    "S:J8742 H:3 D:K5 C:AQT96 (11 HCP) | 1H → 1S (overcall)\n"
    "S:T3 H:84 D:KQJ982 C:KQT (10 HCP) | 1H → Pass (2-level overcall risky)\n"
    "S:QJ75 H:7 D:AT63 C:A965 (11 HCP) | 1H P → 1S (new suit forcing, show spades)\n"
    "S:AK4 H:AQT3 D:5 C:J8742 (16 HCP) | P 1H P 2C X → 3C (show club support)\n"
    "S:Q862 H:AJT9875 D:86 C: (8 HCP) | P 1D X → 1H (cheapest bid, don't jump)\n"
    f"\n{'Opener' if not auction else 'Seat ' + str(len(auction.split())+1)}: "
    f"{hand} ({hand_info(hand)})\n"
    f"Auction: {auction if auction else 'None'}\n"
    "Bid:"
)

# P16: P9 position-aware + moderate LOTT (counting only, no aggressive advice)
PROMPTS[16] = lambda hand, auction, conv: (
    f"You are an expert SAYC bridge bidder. {CONVENTIONS[conv]}\n"
    f"{SAYC_KNOWLEDGE}\n"
    "\nCOMPETITIVE TRUMP COUNTING (Law of Total Tricks):\n"
    "Count your side's combined trumps to decide how high to compete:\n"
    "- Partner opens 1M = 5+ trumps. You have 3 = 8 total → safe to compete at 2-level.\n"
    "- You have 4-card support = 9 total → consider competing at 3-level.\n"
    "- With void/singleton in side suit, you can compete one level higher.\n"
    "- BUT: only compete when you have a fit AND minimum values. Pass with misfit.\n"
    "- In balancing seat (pass-out position), bid with 2-3 fewer HCP than normal.\n"
    "\nExamples:\n"
    "S:AKJ74 H:Q93 D:K84 C:T6 | Auction: None → 1S\n"
    "S:AK4 H:AQT3 D:5 C:J8742 | Auction: None → 1C\n"
    "S:KJ5 H:AQ4 D:KT93 C:Q72 | Auction: None → 1NT\n"
    "S:97 H:KJ984 D:T5 C:QJ32 | Auction: None → Pass\n"
    "S:J8742 H:3 D:K5 C:AQT96 | Auction: 1H → 1S\n"
    "S:T3 H:84 D:KQJ982 C:KQT | Auction: 1H → Pass (2-level overcall needs good suit+values)\n"
    "S:Q862 H:AJT9875 D:86 C: | Auction: P 1D X → 1H (cheapest bid, NOT jump)\n"
    "S:QJ75 H:7 D:AT63 C:A965 | Auction: 1H P → 1S\n"
    "S:AK4 H:AQT3 D:5 C:J8742 | Auction: P 1H P 2C X → 3C\n"
    f"\nPosition: You are {'opener' if not auction else 'seat ' + str(len(auction.split())+1) + ' to bid'}. "
    f"{'You have already heard ' + str(len(auction.split())) + ' bids.' if auction else 'You bid first.'}\n"
    f"Your hand: {hand} ({hand_info(hand)})\n"
    f"Auction so far: {auction if auction else 'None'}\n"
    "Your bid? Output ONLY the bid."
)

# P17: P14 LOTT with error-targeted corrections (anti-aggressiveness when Ben=Pass)
PROMPTS[17] = lambda hand, auction, conv: (
    f"You are an expert SAYC bridge bidder. {CONVENTIONS[conv]}\n"
    f"{SAYC_KNOWLEDGE}\n"
    "\nLAW OF TOTAL TRICKS - COMPETITIVE BIDDING:\n"
    "Count combined trumps: partner's 1M=5+, your support: 3=8 total(2-level), 4=9(3-level).\n"
    "With void/singleton, add 1 level. In balancing seat, bid with 2-3 fewer HCP.\n"
    "\nCRITICAL: When NOT to compete:\n"
    "- With a MISFIT (no support for partner), prefer Pass even with values\n"
    "- After opponents' auction is completed (Pass Pass), do NOT re-enter with minimum\n"
    "- With only 3-card support and minimum HCP (6-8), a simple raise is enough, don't jump\n"
    "- Passed hand: your initial Pass limited your hand. Don't suddenly bid aggressively\n"
    "- At the 2-level: need 5+ card suit AND 10+ HCP to overcall\n"
    "\nExamples:\n"
    "S:AKJ74 H:Q93 D:K84 C:T6 (14 HCP) | None → 1S\n"
    "S:AK4 H:AQT3 D:5 C:J8742 (16 HCP) | None → 1C\n"
    "S:KJ5 H:AQ4 D:KT93 C:Q72 (16 HCP) | None → 1NT\n"
    "S:97 H:KJ984 D:T5 C:QJ32 (8 HCP) | None → Pass\n"
    "S:T3 H:84 D:KQJ982 C:KQT (10 HCP) | P 1H → Pass (only 7 HCP, 2-level overcall needs more)\n"
    "S:9862 H:KJ9652 D:74 C:3 (5 HCP) | P 1H P 2C → Pass (too weak to compete)\n"
    "S:Q862 H:AJT9875 D:86 C: (8 HCP) | P 1D X → 1H (cheapest level, NOT 2H)\n"
    "S:54 H: D:AQ953 C:AKQJT6 (16 HCP) | P 1D X 1S → 5C (big hand, jump to game)\n"
    "S:J8742 H:3 D:K5 C:AQT96 (11 HCP) | 1H → 1S\n"
    "S:QJ75 H:7 D:AT63 C:A965 (11 HCP) | 1H P → 1S (new suit forcing)\n"
    "S:AK4 H:AQT3 D:5 C:J8742 (16 HCP) | P 1H P 2C X → 3C\n"
    f"\nPosition: {'Opener' if not auction else 'Seat ' + str(len(auction.split())+1)}. "
    f"Your hand: {hand} ({hand_info(hand)})\n"
    f"Auction: {auction if auction else 'None'}\n"
    "Your bid:"
)

# P18: P17 base + targeted examples for persistent error positions
PROMPTS[18] = lambda hand, auction, conv: (
    f"You are an expert SAYC bridge bidder. {CONVENTIONS[conv]}\n"
    f"{SAYC_KNOWLEDGE}\n"
    "\nCOMPETITIVE BIDDING RULES:\n"
    "After opponents overcall your partner's opening:\n"
    "- With 3+ card support for partner's major + 8+ HCP → DOUBLE (support/competitive X)\n"
    "- With 5+ card side suit → bid your suit (even with minimum values)\n"
    "- In competitive auctions, DON'T just pass with a fit. Compete!\n"
    "\nAfter a takeout double of partner's bid:\n"
    "- With a good 6+ card suit, JUMP in your suit (preemptive/competitive)\n"
    "- Don't just bid at the cheapest level with a long strong suit\n"
    "\nWhen NOT to compete:\n"
    "- With a MISFIT (no support, no good suit) → Pass\n"
    "- Too weak for 2-level overcall (need 10+ HCP + 5+ card suit)\n"
    "- After your initial Pass limited your hand, don't jump aggressively\n"
    "\nExamples (study carefully):\n"
    "S:AKJ74 H:Q93 D:K84 C:T6 (14 HCP) | None → 1S\n"
    "S:AK4 H:AQT3 D:5 C:J8742 (16 HCP) | None → 1C\n"
    "S:KJ5 H:AQ4 D:KT93 C:Q72 (16 HCP) | None → 1NT\n"
    "S:97 H:KJ984 D:T5 C:QJ32 (8 HCP) | None → Pass\n"
    # Targeted examples for persistent errors:
    "S:Q52 H:6543 D:K732 C:AJ (10 HCP, 3S) | P P 1S 1NT → X "
    "(COMPETITIVE DOUBLE: 10 HCP + 3-card S support for partner's 1S. Do NOT pass!)\n"
    "S:97 H:A9872 D:AJ65 C:43 (9 HCP, 5H 4D) | P P 1S 1NT P → 2D "
    "(compete with 5-card D suit. Do NOT let them play 1NT unopposed!)\n"
    "S:T3 H:84 D:KQJ982 C:KQT (10 HCP, 6D) | P 1H P 2C X P → 3D "
    "(JUMP to 3D with strong 6-card suit KQJ982. Don't bid only 2D!)\n"
    "S:Q862 H:AJT9875 D:86 C: (8 HCP, 7H) | P 1D X → 1H "
    "(bid at cheapest level first, NOT 2H. Show your suit economically)\n"
    "S:54 H: D:AQ953 C:AKQJT6 (16 HCP, 6C 5D) | P 1D X 1S → 5C "
    "(huge hand with 11-card minor suits - jump to game in C!)\n"
    "S:J8742 H:3 D:K5 C:AQT96 (11 HCP) | 1H → 1S (overcall with 5-card suit)\n"
    "S:T3 H:84 D:KQJ982 C:KQT (10 HCP) | 1H → Pass (2-level overcall needs more values)\n"
    "S:QJ75 H:7 D:AT63 C:A965 (11 HCP) | 1H P → 1S (new suit forcing)\n"
    "S:AK4 H:AQT3 D:5 C:J8742 (16 HCP) | P 1H P 2C X → 3C (support partner's clubs)\n"
    f"\nPosition: {'Opener' if not auction else 'Seat ' + str(len(auction.split())+1)}. "
    f"Your hand: {hand} ({hand_info(hand)})\n"
    f"Auction: {auction if auction else 'None'}\n"
    "Your bid:"
)

# P19: P18 but with competitive-focused system message
PROMPTS[19] = lambda hand, auction, conv: (
    f"You are a COMPETITIVE SAYC bridge bidder. You compete aggressively with fits. {CONVENTIONS[conv]}\n"
    f"{SAYC_KNOWLEDGE}\n"
    "\nYOUR COMPETITIVE STYLE:\n"
    "You NEVER sell out cheaply. With any fit + values:\n"
    "- 3+ card support for partner's major + 8+ HCP → competitive X or raise\n"
    "- 5+ card suit → bid it, even at unfavorable level\n"
    "- Strong 6+ card suit after takeout X → JUMP (3-level, not 2)\n"
    "- Big minor-suit hand (10+ cards in minors) → jump to game\n"
    "BUT: Pass with misfit, and don't overcall at 2-level with <10 HCP\n"
    "\nExamples:\n"
    "S:AKJ74 H:Q93 D:K84 C:T6 | None → 1S\n"
    "S:AK4 H:AQT3 D:5 C:J8742 | None → 1C\n"
    "S:KJ5 H:AQ4 D:KT93 C:Q72 | None → 1NT\n"
    "S:97 H:KJ984 D:T5 C:QJ32 | None → Pass\n"
    "S:Q52 H:6543 D:K732 C:AJ | P P 1S 1NT → X (3S support + 10 HCP: compete!)\n"
    "S:97 H:A9872 D:AJ65 C:43 | P P 1S 1NT P → 2D (5-card suit, don't sell out)\n"
    "S:T3 H:84 D:KQJ982 C:KQT | P 1H P 2C X P → 3D (JUMP with KQJ982!)\n"
    "S:Q862 H:AJT9875 D:86 C: | P 1D X → 1H (cheapest, not 2H)\n"
    "S:54 H: D:AQ953 C:AKQJT6 | P 1D X 1S → 5C (jump to game!)\n"
    "S:T3 H:84 D:KQJ982 C:KQT | 1H → Pass (2-level overcall too risky)\n"
    "S:AK4 H:AQT3 D:5 C:J8742 | P 1H P 2C X → 3C\n"
    f"\n{'Opener' if not auction else 'Seat ' + str(len(auction.split())+1)}: "
    f"{hand} ({hand_info(hand)})\n"
    f"Auction: {auction if auction else 'None'}\n"
    "Bid:"
)

# P20: P18 + targeted patches for remaining error patterns
# Fixes: penalty double pass, 5-level stop, 3NT over overcall, weak2 suit quality,
#        competitive raises, response to 1m (bid majors up the line)
PROMPTS[20] = lambda hand, auction, conv: (
    f"You are an expert SAYC bridge bidder. {CONVENTIONS[conv]}\n"
    f"{SAYC_KNOWLEDGE}\n"
    "\nCOMPETITIVE BIDDING RULES:\n"
    "After opponents overcall your partner's opening:\n"
    "- With 3+ card support for partner's major + 8+ HCP → DOUBLE (support/competitive X)\n"
    "- With 5+ card side suit → bid your suit (even with minimum values)\n"
    "- With 13-15 HCP balanced + stopper in opponent's suit → bid 3NT directly\n"
    "- In competitive auctions, DON'T just pass with a fit. Compete!\n"
    "\nAfter a takeout double of partner's bid:\n"
    "- With a good 6+ card suit, JUMP in your suit (preemptive/competitive)\n"
    "- Don't just bid at the cheapest level with a long strong suit\n"
    "\nPENALTY DOUBLES:\n"
    "- When partner makes a PENALTY double (double of a suit at 2+ level), PASS to defend\n"
    "- Do NOT pull partner's penalty double unless you have extreme distribution (void in their suit)\n"
    "- If you have trump honors (A, K, Q) in the doubled suit → definitely pass\n"
    "\n5-LEVEL DECISIONS:\n"
    "- 'The 5-level belongs to the opponents' — do NOT compete to 5-minor unless forced\n"
    "- If opponents bid 5 of their suit, Pass is usually right unless you have extreme shape\n"
    "- Once the auction has reached the 5-level, STOP competing\n"
    "\nWhen NOT to compete:\n"
    "- With a MISFIT (no support, no good suit) → Pass\n"
    "- Too weak for 2-level overcall (need 10+ HCP + 5+ card suit)\n"
    "- After your initial Pass, don't JUMP aggressively — but still bid with a good long suit\n"
    "- If partner PASSED your bid, don't bid again without extra shape/strength\n"
    "\nOPENING SUIT CHOICE:\n"
    "- With 6-5 in two suits, open the LONGER suit (6C+5D = open 1C, not 1D)\n"
    "- With 5-5, open the HIGHER-ranking suit (5H+5S = open 1S)\n"
    "\nRESPONSES TO 1-MINOR:\n"
    "- With a 4-card major, ALWAYS bid it (bid 4-card suits UP THE LINE: 1D then 1H then 1S)\n"
    "- 1S over partner's 1H opening with 4 spades is ALWAYS correct\n"
    "\nWEAK 2 OPENINGS:\n"
    "- Need a GOOD 6-card suit (2+ honors like KQxxxx, QJTxxx, AJTxxx)\n"
    "- Do NOT open weak 2 with Axxxxx (only 1 honor) — suit too weak\n"
    "- Do NOT open weak 2 with a side Ace — hand is too strong-looking\n"
    "\nExamples (study carefully):\n"
    "S:AKJ74 H:Q93 D:K84 C:T6 (14 HCP) | None → 1S\n"
    "S:AK4 H:AQT3 D:5 C:J8742 (16 HCP) | None → 1C\n"
    "S:KJ5 H:AQ4 D:KT93 C:Q72 (16 HCP) | None → 1NT\n"
    "S:97 H:KJ984 D:T5 C:QJ32 (8 HCP) | None → Pass\n"
    "S:QT7 H:A86542 D:764 C:A (10 HCP, 6H) | None → Pass "
    "(6H suit has only Ace — too weak for weak 2. Side Ace also wrong. Pass!)\n"
    # Competitive examples:
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
    # Response / suit choice:
    "S:QJ75 H:7 D:AT63 C:A965 (11 HCP) | 1H P → 1S (new suit forcing, bid 4-card major)\n"
    "S:J8742 H:3 D:K5 C:AQT96 (11 HCP) | 1H → 1S (overcall with 5-card suit)\n"
    "S:T3 H:84 D:KQJ982 C:KQT (10 HCP) | 1H → Pass (2-level overcall too risky)\n"
    # 3NT over overcall:
    "S:J32 H:KT3 D:AKJT C:Q65 (14 HCP, bal) | 1D 1H → 3NT "
    "(14 HCP + heart stopper KT3 = jump to 3NT over overcall)\n"
    # Penalty double:
    "S:AK4 H:AQT3 D:5 C:J8742 (16 HCP) | P 1H P 2C X → 3C (support partner's clubs)\n"
    "S:AK4 H:AQT3 D:5 C:J8742 | P 1H P 2C X P 2S X P → Pass "
    "(partner's X of 2S is PENALTY. We have AK of spades. PASS and defend!)\n"
    # Competitive raise:
    "S:KJ93 H:KQ64 D:T74 C:73 (9 HCP, 4S) | P 1D X 1S P 2C P 4D P → 4S "
    "(4-card support for partner's 1S + opponents at 4D = compete to 4S)\n"
    # 5-level stop:
    "S:54 H: D:AQ953 C:AKQJT6 | P 1D X 1S P 2C P 4D P 4H P 5D → Pass "
    "(STOP at 5-level! Do NOT bid 5C or higher. The 5-level belongs to opponents.)\n"
    f"\nPosition: {'Opener' if not auction else 'Seat ' + str(len(auction.split())+1)}. "
    f"Your hand: {hand} ({hand_info(hand)})\n"
    f"Auction: {auction if auction else 'None'}\n"
    "Your bid:"
)

# P22: Simplified P20 — ablation-tested. Removed harmful rules A (competitive), B (takeout X), E (not compete).
# Kept: D (5-level), F (suit choice) + all examples. Rules C, G, H dropped as neutral noise.
# Ablation showed: rules barely help (-0.7% when ALL removed), examples are critical (-29.3% when removed)
PROMPTS[22] = lambda hand, auction, conv: (
    f"You are an expert SAYC bridge bidder. {CONVENTIONS[conv]}\n"
    f"{SAYC_KNOWLEDGE}\n"
    "\nPENALTY DOUBLES:\n"
    "- When partner makes a PENALTY double (double of a suit at 2+ level), PASS to defend\n"
    "- Do NOT pull partner's penalty double unless you have extreme distribution (void in their suit)\n"
    "\n5-LEVEL DECISIONS:\n"
    "- 'The 5-level belongs to the opponents' — do NOT compete to 5-minor unless forced\n"
    "- Once the auction has reached the 5-level, STOP competing\n"
    "\nOPENING SUIT CHOICE:\n"
    "- With 6-5 in two suits, open the LONGER suit (6C+5D = open 1C, not 1D)\n"
    "- With 5-5, open the HIGHER-ranking suit (5H+5S = open 1S)\n"
    "\nExamples (study carefully):\n"
    "S:AKJ74 H:Q93 D:K84 C:T6 (14 HCP) | None → 1S\n"
    "S:AK4 H:AQT3 D:5 C:J8742 (16 HCP) | None → 1C\n"
    "S:KJ5 H:AQ4 D:KT93 C:Q72 (16 HCP) | None → 1NT\n"
    "S:97 H:KJ984 D:T5 C:QJ32 (8 HCP) | None → Pass\n"
    "S:QT7 H:A86542 D:764 C:A (10 HCP, 6H) | None → Pass "
    "(6H suit has only Ace — too weak for weak 2. Side Ace also wrong. Pass!)\n"
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
    "S:QJ75 H:7 D:AT63 C:A965 (11 HCP) | 1H P → 1S (new suit forcing, bid 4-card major)\n"
    "S:J8742 H:3 D:K5 C:AQT96 (11 HCP) | 1H → 1S (overcall with 5-card suit)\n"
    "S:T3 H:84 D:KQJ982 C:KQT (10 HCP) | 1H → Pass (2-level overcall too risky)\n"
    "S:J32 H:KT3 D:AKJT C:Q65 (14 HCP, bal) | 1D 1H → 3NT "
    "(14 HCP + heart stopper KT3 = jump to 3NT over overcall)\n"
    "S:AK4 H:AQT3 D:5 C:J8742 (16 HCP) | P 1H P 2C X → 3C (support partner's clubs)\n"
    "S:AK4 H:AQT3 D:5 C:J8742 | P 1H P 2C X P 2S X P → Pass "
    "(partner's X of 2S is PENALTY. We have AK of spades. PASS and defend!)\n"
    "S:KJ93 H:KQ64 D:T74 C:73 (9 HCP, 4S) | P 1D X 1S P 2C P 4D P → 4S "
    "(4-card support for partner's 1S + opponents at 4D = compete to 4S)\n"
    "S:54 H: D:AQ953 C:AKQJT6 | P 1D X 1S P 2C P 4D P 4H P 5D → Pass "
    "(STOP at 5-level! Do NOT bid 5C or higher. The 5-level belongs to opponents.)\n"
    f"\nPosition: {'Opener' if not auction else 'Seat ' + str(len(auction.split())+1)}. "
    f"Your hand: {hand} ({hand_info(hand)})\n"
    f"Auction: {auction if auction else 'None'}\n"
    "Your bid:"
)

# P21: P20 + splinter recognition, cuebids/control bids, competitive raising
# Generic examples only — NO test-set hands
PROMPTS[21] = lambda hand, auction, conv: (
    f"You are an expert SAYC bridge bidder. {CONVENTIONS[conv]}\n"
    f"{SAYC_KNOWLEDGE}\n"
    "\nSPLINTER BIDS:\n"
    "- A JUMP to 4 of a NEW SUIT in response to partner's 1H/1S = SPLINTER\n"
    "- Splinter = shortness (singleton/void) in bid suit + 4+ trump support + game-forcing values (13+ support pts)\n"
    "- 1S - 4C = short clubs + 4+ spades + game force. 1S - 4D = short diamonds. 1H - 4C/4D = short in bid suit.\n"
    "- RESPONDING to partner's splinter: with minimum (12-15), sign off in 4M. With extras + good controls, cuebid.\n"
    "- A splinter is NEVER a natural bid. 4C over 1S is NOT clubs — it's a spade raise!\n"
    "- After a splinter, you MUST bid at least 4M. NEVER pass below game in a game-forcing auction!\n"
    "\nCONTROL BIDS (CUEBIDS):\n"
    "- After trump is agreed in a game-forcing auction, a new suit = control (Ace, King, or void)\n"
    "- Cuebids go UP THE LINE: bid cheapest control first\n"
    "- After partner cuebids, cuebid YOUR cheapest control or sign off in the agreed trump suit\n"
    "- With minimum and no slam interest → just sign off in the agreed major\n"
    "\nCOMPETITIVE BIDDING RULES:\n"
    "After opponents overcall your partner's opening:\n"
    "- With 3+ card support for partner's major + 8+ HCP → DOUBLE (support/competitive X)\n"
    "- With 5+ card side suit → bid your suit (even with minimum values)\n"
    "- With 13-15 HCP balanced + stopper in opponent's suit → bid 3NT directly\n"
    "- In competitive auctions, DON'T just pass with a fit. Compete!\n"
    "\nRAISING PARTNER IN COMPETITION:\n"
    "- When opponents preempt over partner's major opening and you have 4+ trump support → raise to game!\n"
    "- Don't let opponents steal the contract when you have a known fit\n"
    "\nAfter a takeout double of partner's bid:\n"
    "- With a good 6+ card suit, JUMP in your suit (preemptive/competitive)\n"
    "- Don't just bid at the cheapest level with a long strong suit\n"
    "\nAFTER OPPONENT'S TAKEOUT DOUBLE:\n"
    "- When partner opens and opponent doubles, with 6+ HCP and a 4+ card suit: BID your suit\n"
    "- Do NOT pass with 8+ HCP just because opponent doubled\n"
    "\nPENALTY DOUBLES:\n"
    "- When partner makes a PENALTY double (double of a suit at 2+ level), PASS to defend\n"
    "- Do NOT pull partner's penalty double unless you have extreme distribution (void in their suit)\n"
    "- If you have trump honors (A, K, Q) in the doubled suit → definitely pass\n"
    "\n5-LEVEL DECISIONS:\n"
    "- 'The 5-level belongs to the opponents' — do NOT compete to 5-minor unless forced\n"
    "- If opponents bid 5 of their suit, Pass is usually right unless you have extreme shape\n"
    "- Once the auction has reached the 5-level, STOP competing\n"
    "\nWhen NOT to compete:\n"
    "- With a MISFIT (no support, no good suit) → Pass\n"
    "- Too weak for 2-level overcall (need 10+ HCP + 5+ card suit)\n"
    "- After your initial Pass, don't JUMP aggressively — but still bid with a good long suit\n"
    "- If partner PASSED your bid, don't bid again without extra shape/strength\n"
    "\nOPENING SUIT CHOICE:\n"
    "- With 6-5 in two suits, open the LONGER suit (6C+5D = open 1C, not 1D)\n"
    "- With 5-5, open the HIGHER-ranking suit (5H+5S = open 1S)\n"
    "\nRESPONSES TO 1-MINOR:\n"
    "- With a 4-card major, ALWAYS bid it (bid 4-card suits UP THE LINE: 1D then 1H then 1S)\n"
    "- 1S over partner's 1H opening with 4 spades is ALWAYS correct\n"
    "\nWEAK 2 OPENINGS:\n"
    "- Need a GOOD 6-card suit (2+ honors like KQxxxx, QJTxxx, AJTxxx)\n"
    "- Do NOT open weak 2 with Axxxxx (only 1 honor) — suit too weak\n"
    "- Do NOT open weak 2 with a side Ace — hand is too strong-looking\n"
    "\nExamples (study carefully):\n"
    "S:AKJ74 H:Q93 D:K84 C:T6 (14 HCP) | None → 1S\n"
    "S:AK4 H:AQT3 D:5 C:J8742 (16 HCP) | None → 1C\n"
    "S:KJ5 H:AQ4 D:KT93 C:Q72 (16 HCP) | None → 1NT\n"
    "S:97 H:KJ984 D:T5 C:QJ32 (8 HCP) | None → Pass\n"
    "S:QT7 H:A86542 D:764 C:A (10 HCP, 6H) | None → Pass "
    "(6H suit has only Ace — too weak for weak 2. Side Ace also wrong. Pass!)\n"
    # Splinter examples (generic hands, NOT from test set):
    "S:KT83 H:A95 D:QJ74 C:62 (11 HCP, 4S) | 1S Pass 4C Pass → 4S "
    "(Partner's 4C over your 1S = SPLINTER: short clubs, 4+ spades, game force. Bid 4S with minimum!)\n"
    "S:AQJ65 H:K82 D:A93 C:74 (15 HCP, 5S) | 1S Pass 4D Pass → 4S "
    "(4D = splinter (short diamonds, 4+ spades). Sign off in 4S — no slam interest with 15 HCP.)\n"
    # Competitive raise over preempt (generic):
    "S:K953 H:J64 D:Q83 C:T72 (7 HCP, 4S) | 1S 4H → 4S "
    "(4-card spade support + partner opened → bid 4S over opponent's 4H preempt!)\n"
    # Competitive examples:
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
    # Response / suit choice:
    "S:QJ75 H:7 D:AT63 C:A965 (11 HCP) | 1H P → 1S (new suit forcing, bid 4-card major)\n"
    "S:J8742 H:3 D:K5 C:AQT96 (11 HCP) | 1H → 1S (overcall with 5-card suit)\n"
    "S:T3 H:84 D:KQJ982 C:KQT (10 HCP) | 1H → Pass (2-level overcall too risky)\n"
    # 3NT over overcall:
    "S:J32 H:KT3 D:AKJT C:Q65 (14 HCP, bal) | 1D 1H → 3NT "
    "(14 HCP + heart stopper KT3 = jump to 3NT over overcall)\n"
    # Penalty double:
    "S:AK4 H:AQT3 D:5 C:J8742 (16 HCP) | P 1H P 2C X → 3C (support partner's clubs)\n"
    "S:AK4 H:AQT3 D:5 C:J8742 | P 1H P 2C X P 2S X P → Pass "
    "(partner's X of 2S is PENALTY. We have AK of spades. PASS and defend!)\n"
    # Competitive raise:
    "S:KJ93 H:KQ64 D:T74 C:73 (9 HCP, 4S) | P 1D X 1S P 2C P 4D P → 4S "
    "(4-card support for partner's 1S + opponents at 4D = compete to 4S)\n"
    # 5-level stop:
    "S:54 H: D:AQ953 C:AKQJT6 | P 1D X 1S P 2C P 4D P 4H P 5D → Pass "
    "(STOP at 5-level! Do NOT bid 5C or higher. The 5-level belongs to opponents.)\n"
    f"\nPosition: {'Opener' if not auction else 'Seat ' + str(len(auction.split())+1)}. "
    f"Your hand: {hand} ({hand_info(hand)})\n"
    f"Auction: {auction if auction else 'None'}\n"
    "Your bid:"
)

# P30: System-adaptive P22 — uses SYSTEM_KNOWLEDGE[conv] instead of SAYC_KNOWLEDGE.
# For testing different bidding systems (2/1, ACOL, PRECISION, SEF, POLISH_CLUB) against DD/IMP.
PROMPTS[30] = lambda hand, auction, conv: (
    f"You are an expert bridge bidder. {CONVENTIONS[conv]}\n"
    f"{SYSTEM_KNOWLEDGE.get(conv, SAYC_KNOWLEDGE)}\n"
    "\nPENALTY DOUBLES:\n"
    "- When partner makes a PENALTY double (double of a suit at 2+ level), PASS to defend\n"
    "- Do NOT pull partner's penalty double unless you have extreme distribution (void in their suit)\n"
    "\n5-LEVEL DECISIONS:\n"
    "- 'The 5-level belongs to the opponents' — do NOT compete to 5-minor unless forced\n"
    "- Once the auction has reached the 5-level, STOP competing\n"
    "\nOPENING SUIT CHOICE:\n"
    "- With 6-5 in two suits, open the LONGER suit (6C+5D = open 1C, not 1D)\n"
    "- With 5-5, open the HIGHER-ranking suit (5H+5S = open 1S)\n"
    "\nExamples (study carefully):\n"
    "S:AKJ74 H:Q93 D:K84 C:T6 (14 HCP) | None → 1S\n"
    "S:AK4 H:AQT3 D:5 C:J8742 (16 HCP) | None → 1C\n"
    "S:KJ5 H:AQ4 D:KT93 C:Q72 (16 HCP) | None → 1NT\n"
    "S:97 H:KJ984 D:T5 C:QJ32 (8 HCP) | None → Pass\n"
    "S:QT7 H:A86542 D:764 C:A (10 HCP, 6H) | None → Pass "
    "(6H suit has only Ace — too weak for weak 2. Side Ace also wrong. Pass!)\n"
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
    "S:QJ75 H:7 D:AT63 C:A965 (11 HCP) | 1H P → 1S (new suit forcing, bid 4-card major)\n"
    "S:J8742 H:3 D:K5 C:AQT96 (11 HCP) | 1H → 1S (overcall with 5-card suit)\n"
    "S:T3 H:84 D:KQJ982 C:KQT (10 HCP) | 1H → Pass (2-level overcall too risky)\n"
    "S:J32 H:KT3 D:AKJT C:Q65 (14 HCP, bal) | 1D 1H → 3NT "
    "(14 HCP + heart stopper KT3 = jump to 3NT over overcall)\n"
    "S:AK4 H:AQT3 D:5 C:J8742 (16 HCP) | P 1H P 2C X → 3C (support partner's clubs)\n"
    "S:AK4 H:AQT3 D:5 C:J8742 | P 1H P 2C X P 2S X P → Pass "
    "(partner's X of 2S is PENALTY. We have AK of spades. PASS and defend!)\n"
    "S:KJ93 H:KQ64 D:T74 C:73 (9 HCP, 4S) | P 1D X 1S P 2C P 4D P → 4S "
    "(4-card support for partner's 1S + opponents at 4D = compete to 4S)\n"
    "S:54 H: D:AQ953 C:AKQJT6 | P 1D X 1S P 2C P 4D P 4H P 5D → Pass "
    "(STOP at 5-level! Do NOT bid 5C or higher. The 5-level belongs to opponents.)\n"
    f"\nPosition: {'Opener' if not auction else 'Seat ' + str(len(auction.split())+1)}. "
    f"Your hand: {hand} ({hand_info(hand)})\n"
    f"Auction: {auction if auction else 'None'}\n"
    "Your bid:"
)

# P12: Minimal but effective - just rules and examples, no fluff
PROMPTS[12] = lambda hand, auction, conv: (
    "SAYC bidder.\n"
    "Open 12+: 5+M→1H/1S, no 5M→longest minor, 15-17bal→1NT, 20-21→2NT, 22+→2C, weak2=6-10+6card\n"
    "Respond 1M: 6-9+3trump→raise, 10-12→jump, 13+→2NT. New suit 1-level=forcing\n"
    "Respond 1m: 4M up the line. 1NT=6-10\n"
    "Respond 1NT: 2C=Stayman(8+4M), 2D→H, 2H→S\n"
    "Compete: overcall=8-16+5card, 1NTover=15-18+stop, X=12+unbid. Balance -3HCP\n"
    "\n"
    "S:AKJ74 H:Q93 D:K84 C:T6|→1S. "
    "S:AK4 H:AQT3 D:5 C:J8742|→1C. "
    "S:KJ5 H:AQ4 D:KT93 C:Q72|→1NT. "
    "S:97 H:KJ984 D:T5 C:QJ32|→P. "
    "S:J8742 H:3 D:K5 C:AQT96|1H→1S. "
    "S:QJ75 H:7 D:AT63 C:A965|1H P→1S. "
    "S:AK4 H:AQT3 D:5 C:J8742|P 1H P 2C X→3C\n"
    f"\n{hand} ({hand_info(hand)})|{auction if auction else ''}→"
)


ORACLE_COLUMNS = {
    'ben': 'ben_sayc_bid',
    'bba': 'bba_bid',
    'wbridge5': 'wbridge5_bid',
}


def test_prompt(prompt_id, model_name, dataset_path, n, conv="SAYC",
                temperature=0.0, max_tokens=None, vote_k=1, oracle='ben'):
    """Test a prompt strategy and return accuracy."""
    import google.generativeai as genai

    api_key = os.environ.get("GOOGLE_API_KEY")
    genai.configure(api_key=api_key)
    model_ref = genai.GenerativeModel(model_name=model_name)

    oracle_col = ORACLE_COLUMNS.get(oracle, 'ben_sayc_bid')

    records = []
    with open(dataset_path) as f:
        reader = csv.DictReader(f)
        for row in reader:
            ref = row.get(oracle_col, '')
            if not ref or ref.startswith('ERR'):
                continue
            records.append(row)
            if len(records) >= n:
                break

    prompt_fn = PROMPTS[prompt_id]
    correct = 0
    errors = []

    safety = [
        {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
    ]

    tok_limit = max_tokens if max_tokens else 50

    for i, row in enumerate(records):
        hand = row['hand']
        auction = row['auction']
        ben_bid = row[oracle_col]

        prompt = prompt_fn(hand, auction, conv)

        if vote_k > 1:
            # Majority voting
            from collections import Counter
            votes = []
            for _ in range(vote_k):
                cfg = genai.types.GenerationConfig(
                    temperature=temperature, max_output_tokens=tok_limit, candidate_count=1)
                try:
                    resp = model_ref.generate_content(prompt, generation_config=cfg,
                                                      safety_settings=safety)
                    text = resp.text.strip() if resp.text else "Pass"
                    votes.append(parse_bid_from_response(text).upper())
                except:
                    votes.append("PASS")
            pred = Counter(votes).most_common(1)[0][0]
        else:
            cfg = genai.types.GenerationConfig(
                temperature=temperature, max_output_tokens=tok_limit, candidate_count=1)
            try:
                resp = model_ref.generate_content(prompt, generation_config=cfg,
                                                  safety_settings=safety)
                text = resp.text.strip() if resp.text else "Pass"
                pred = parse_bid_from_response(text)
            except Exception as e:
                pred = '?'

        is_correct = pred.upper() == ben_bid.upper()
        if is_correct:
            correct += 1
        else:
            errors.append((i, hand, auction, ben_bid, pred))

        print(f"\r  P{prompt_id}: {i+1}/{len(records)} acc={correct}/{i+1} ({correct/(i+1)*100:.0f}%)", end='')

    accuracy = correct / len(records) if records else 0
    print(f"\n  → P{prompt_id} FINAL: {correct}/{len(records)} = {accuracy*100:.1f}%")

    if errors:
        print(f"  Errors ({len(errors)} total):")
        for idx, hand, auc, ben, pred in errors[:10]:
            auc_display = auc if auc else '(open)'
            print(f"    #{idx}: {hand[:25]:<25} {auc_display[:30]:<30} Ben={ben:<6} Got={pred}")

    return accuracy, errors


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--prompt_id', type=int, default=None,
                        help='Test specific prompt (0-10). None=test all')
    parser.add_argument('--model', default='gemini-3.1-flash-lite-preview')
    parser.add_argument('--n', type=int, default=50)
    parser.add_argument('--dataset', default='data/ben_sayc_100.csv')
    parser.add_argument('--temperature', type=float, default=0.0)
    parser.add_argument('--max_tokens', type=int, default=None)
    parser.add_argument('--vote_k', type=int, default=1,
                        help='Majority voting with K calls (requires temp>0)')
    parser.add_argument('--oracle', default='ben', choices=['ben', 'bba', 'wbridge5'],
                        help='Reference oracle: ben (default), bba, or wbridge5')
    args = parser.parse_args()

    if args.prompt_id is not None:
        test_prompt(args.prompt_id, args.model, args.dataset, args.n,
                    temperature=args.temperature, max_tokens=args.max_tokens,
                    vote_k=args.vote_k, oracle=args.oracle)
    else:
        results = {}
        for pid in sorted(PROMPTS.keys()):
            print(f"\n{'='*60}")
            print(f"Testing prompt P{pid}")
            print(f"{'='*60}")
            acc, _ = test_prompt(pid, args.model, args.dataset, args.n,
                                 temperature=args.temperature,
                                 max_tokens=args.max_tokens,
                                 vote_k=args.vote_k, oracle=args.oracle)
            results[pid] = acc

        print(f"\n{'='*60}")
        print("SUMMARY")
        print(f"{'='*60}")
        for pid, acc in sorted(results.items(), key=lambda x: -x[1]):
            bar = '█' * int(acc * 40)
            print(f"  P{pid}: {acc*100:5.1f}% {bar}")


if __name__ == '__main__':
    main()

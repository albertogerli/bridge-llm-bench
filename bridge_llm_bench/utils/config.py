"""
Configuration constants and settings for Bridge LLM Benchmarking System.
"""

from pathlib import Path

# ── System Configuration ─────────────────────────────────────────────

MAX_OUTPUT_TOKENS = 50
MAX_OUTPUT_TOKENS_REASONING = 2000
DEFAULT_DATASET_PATH = Path("data/open_spiel/test.txt")
DEFAULT_DATASET_URL = "https://storage.googleapis.com/openspiel-data/bridge/test.txt"

# Large training set (1M games, ~400MB)
TRAIN_DATASET_PATH = Path("data/open_spiel/train.txt")
TRAIN_DATASET_URL = "https://storage.googleapis.com/openspiel-data/bridge/train.txt"

# Models that use chain-of-thought / internal reasoning and need more output tokens.
# Checked: these models allocate reasoning_tokens from the completion budget.
REASONING_MODELS = {
    "o3",
    "gpt-5",
    "deepseek-r1", "deepseek-R1", "deepseek-R1-0528", "deepseek-r1-0528",
    "kimi-k2.5-thinking",
    "grok-4.1-thinking", "grok-4.20-beta1",
    "glm-5", "glm-4.7", "glm-4.6", "glm-4.5",
    "mimo-v2-flash",
}

# ── Pricing (USD per 1K tokens) ──────────────────────────────────────

PRICE_USD_PER_1K = {
    # OpenAI
    "gpt-5.2": {"input": 0.003, "output": 0.012},
    "gpt-5-nano": {"input": 0.0001, "output": 0.0004},
    "gpt-5.1": {"input": 0.002, "output": 0.008},
    "o3": {"input": 0.002, "output": 0.008},
    "gpt-4.1": {"input": 0.002, "output": 0.008},
    "gpt-4o": {"input": 0.0025, "output": 0.01},
    # Anthropic
    "claude-opus-4-6": {"input": 0.015, "output": 0.075},
    "claude-haiku-4-5": {"input": 0.0008, "output": 0.004},
    "claude-sonnet-4": {"input": 0.003, "output": 0.015},
    "claude-opus-4": {"input": 0.015, "output": 0.075},
    # Google
    "gemini-3.1-flash-lite": {"input": 0.000025, "output": 0.0003},
    "gemini-3.1": {"input": 0.00125, "output": 0.01},
    "gemini-3": {"input": 0.00125, "output": 0.01},
    "gemini-2.5-pro": {"input": 0.00125, "output": 0.01},
    "gemini-2.5-flash": {"input": 0.000075, "output": 0.0003},
    # DeepSeek
    "deepseek-r1": {"input": 0.00055, "output": 0.00219},
    "deepseek-R1": {"input": 0.00055, "output": 0.00219},
    "deepseek-v3": {"input": 0.00027, "output": 0.0011},
    "deepseek-V3": {"input": 0.00027, "output": 0.0011},
    # Qwen / Alibaba
    "qwen3": {"input": 0.0004, "output": 0.0012},
    # xAI
    "grok-4.20": {"input": 0.003, "output": 0.015},
    "grok-4-1-fast": {"input": 0.0002, "output": 0.0005},
    "grok-4": {"input": 0.003, "output": 0.015},
    "grok-3": {"input": 0.003, "output": 0.015},
    # Z.ai / Zhipu
    "glm-5": {"input": 0.001, "output": 0.004},
    "glm-4.7": {"input": 0.0005, "output": 0.002},
    "glm": {"input": 0.001, "output": 0.004},
    # Baidu
    "ernie-5": {"input": 0.001, "output": 0.004},
    "ernie-4": {"input": 0.0005, "output": 0.002},
    "ernie": {"input": 0.001, "output": 0.004},
    # Moonshot
    "kimi-k2.5-thinking": {"input": 0.001, "output": 0.004},
    "kimi-k2.5-instant": {"input": 0.0005, "output": 0.002},
    "kimi": {"input": 0.001, "output": 0.004},
    # MiniMax
    "minimax-m2.5": {"input": 0.0004, "output": 0.0016},
    "minimax": {"input": 0.0004, "output": 0.0016},
    # Xiaomi
    "mimo": {"input": 0.0001, "output": 0.0003},
}

# ── Arena Leaderboard Models (March 2026) ────────────────────────────
# Strategy: top-of-line + fastest per provider

ARENA_LEADERBOARD_MODELS = [
    # Anthropic — top + fast
    "claude-opus-4-6",
    "claude-haiku-4-5-20251001",
    # Google — top + fast
    "gemini-3.1-pro-preview",
    "gemini-3.1-flash-lite-preview",
    # xAI — top + fast
    "grok-4.20-beta1",
    "grok-4-1-fast-non-reasoning",
    # OpenAI — top + fast
    "gpt-5.2-chat-latest",
    "gpt-5-nano",
    # Z.ai — top + fast
    "glm-5",
    "glm-4.7",
    # Baidu — top + fast
    "ernie-5.0",
    "ernie-4.0-turbo",
    # Moonshot — top + fast
    "kimi-k2.5-thinking",
    "kimi-k2.5-instant",
    # Qwen — top + fast
    "qwen3.5-397b-a17b",
    "qwen3-235b-a22b-instruct",
    # DeepSeek — top + fast
    "deepseek-r1-0528",
    "deepseek-v3.2",
    # MiniMax — top + fast
    "MiniMax-M2.5",
    "MiniMax-M2.5-highspeed",
    # Xiaomi
    "mimo-v2-flash",
]

# ── Bridge Conventions ───────────────────────────────────────────────

CONVENTIONS = {
    "SAYC": (
        "You are playing Standard American Yellow Card (SAYC): "
        "5-card majors, 15-17 NT, Stayman/Transfers, limit raises."
    ),
    "2/1": (
        "You are playing Two-over-One Game-Forcing: "
        "5-card majors, 14-16 NT, Jacoby 2NT; "
        "2/1 responses are game-forcing."
    ),
    "ACOL": (
        "You are playing Standard Acol: "
        "4-card majors, weak NT (12-14), strong 2C, limit raises. "
        "Light opening bids (11+ HCP). Stayman and transfers over 1NT."
    ),
    "PRECISION": (
        "You are playing Precision Club: "
        "1C = 16+ HCP (artificial, forcing). 1D = 11-15 HCP (may be short). "
        "1H/1S = 11-15 HCP, 5+ cards. 1NT = 13-15 balanced. 2C = 11-15, 6+ clubs."
    ),
    "SEF": (
        "You are playing Standard European Francaise (SEF): "
        "5-card majors, 15-17 NT, 2C strong artificial, 2D/2H/2S weak. "
        "Checkback Stayman, Roudi over 1NT rebid."
    ),
    "POLISH_CLUB": (
        "You are playing Polish Club: "
        "1C = 12-14 balanced OR 18+ any. 1D = 12-17 unbalanced, 4+D. "
        "1H/1S = 12-17, 5+ cards. 1NT = 15-17 balanced."
    ),
}

# ── SAYC Knowledge Reference ────────────────────────────────────────

SAYC_KNOWLEDGE = """\
SAYC Complete Reference:
OPENING BIDS: 12-21 HCP required. 5+ card major open 1H/1S (higher first with 5-5). \
No 5-card major: open longest minor (1C with 3-3, 1D with 4-4). \
15-17 balanced open 1NT (may have 5-card suit). 20-21 balanced open 2NT. \
22+ HCP open 2C (strong artificial, 2D=waiting). \
Weak 2 (2D/2H/2S) = 5-11 HCP + good 6-card suit, no void, no outside 4-card major. \
3-level preempt = 7-card suit too weak to open at 1. Pass with <12 HCP and no preempt shape.
RESPONSES TO 1H/1S: 6-9 raise with 3+ trump or bid 1NT (non-forcing); \
10-12 jump raise (limit raise, 3+ trump) or new suit; \
13+ Jacoby 2NT (4+ trump, game-forcing) or new suit forcing; \
jump to 4M with 5+ trump and <10 HCP (preemptive). New suit at 1-level=4+ cards, forcing.
RESPONSES TO 1C/1D: New suit at 1-level (4+ cards, bid up the line) preferred; \
raise minor with 5+ support; 1NT=6-10 no 4-card major; \
2NT=11-12 balanced no major; 3NT=13-15 balanced no major.
RESPONSES TO 1NT: 2C=Stayman (need 4-card major, 8+ HCP); \
2D=transfer to 2H, 2H=transfer to 2S (5+ cards); 2S=puppet to 3C; \
2NT=invitational; 4C=Gerber (ace-ask); 4NT=quantitative. 0-7 HCP Pass or transfer+pass.
RESPONSES TO 2C: 2D=artificial waiting; 2H/2S/3C/3D=natural GF 5+ cards with 2 of top 3; \
2NT=8+ balanced.
RESPONSES TO WEAK 2: 2NT=forcing (opener shows feature or rebids suit); \
raise=to play; new suit=5+ forcing one round.
OPENER REBIDS: Min(13-15) cheapest NT/raise/rebid suit; Med(16-18) jump raise/jump rebid/reverse; \
Max(19-21) jump NT/double-jump raise/jump shift. Reverse=new suit above 2 of opened suit, 16+ HCP.
COMPETITIVE: Overcall 1-level=8-16 HCP 5+ cards; 1NT overcall=15-18 balanced with stopper; \
Takeout X=support for unbid suits 12+ or 17+ any; X of game-level=penalty. \
Unusual 2NT=5-5+ two lowest unbid suits; Michaels cuebid=over minor 5-5 majors, over major 5-5 other major+minor. \
Jump overcall=preemptive. Negative X thru 3S=values in unbid suits.
AFTER OPP TAKEOUT X: Redouble=10+ tends to deny fit; 2NT Jordan=limit raise+; \
jump raise=preemptive; new suit at 1-level=forcing; jump shift=preemptive.
SLAM: Blackwood 4NT=ace ask (5C=0/4, 5D=1, 5H=2, 5S=3); Gerber 4C over NT=ace ask; \
Grand Slam Force 5NT=bid 7 with 2 of top 3 honors. Cue-bid controls once trump agreed.
PASSED HAND: may open lighter in 3rd/4th seat (10-11 HCP ok). \
Passed hand responses are non-forcing (no longer unlimited).\
"""

# ── System-Specific Knowledge References ──────────────────────────────

TWO_OVER_ONE_KNOWLEDGE = """\
2/1 Game-Forcing Complete Reference:
OPENING BIDS: 12-21 HCP required. 5+ card major open 1H/1S (higher first with 5-5). \
No 5-card major: open longest minor (1C with 3-3, 1D with 4-4). \
14-16 balanced open 1NT (some play 15-17). 20-21 balanced open 2NT. \
22+ HCP open 2C (strong artificial, 2D=waiting). \
Weak 2 (2D/2H/2S) = 5-11 HCP + good 6-card suit. \
3-level preempt = 7-card suit too weak to open at 1. Pass with <12 HCP and no preempt shape.
KEY DIFFERENCE: A 2/1 response (2C, 2D, 2H over 1S) by unpassed hand = GAME FORCING. \
No need for jump shifts to show strength — a simple 2-level new suit commits to game. \
1NT response to 1H/1S by unpassed hand is SEMI-FORCING (opener must bid with unbalanced hand).
RESPONSES TO 1H/1S: 6-9 raise with 3+ trump; 10-12 limit raise via 1NT then raise; \
13+ 2/1 response (game forcing) or Jacoby 2NT (4+ trump, game forcing); \
jump to 4M with 5+ trump and <10 HCP (preemptive). New suit at 1-level=4+ cards, forcing.
RESPONSES TO 1C/1D: New suit at 1-level (4+ cards, bid up the line) preferred; \
1NT=6-10; 2/1 in new suit=game forcing by unpassed hand.
RESPONSES TO 1NT: 2C=Stayman; 2D=transfer to 2H, 2H=transfer to 2S (5+ cards); \
2NT=invitational; 4C=Gerber; 4NT=quantitative. 0-7 HCP Pass or transfer+pass.
OPENER REBIDS: After 2/1 GF response, all bids are natural and forcing until game. \
Min(12-14) rebid suit/cheapest NT; Med(15-17) jump; Max(18+) new suits/jumps.
COMPETITIVE: Overcall 1-level=8-16 HCP 5+ cards; 1NT overcall=15-18 balanced with stopper; \
Takeout X=support for unbid suits 12+. Negative X thru 3S. \
Unusual 2NT=5-5+ two lowest unbid; Michaels cuebid=5-5 majors or major+minor.
SLAM: RKCB 4NT=ace ask (1430 responses); Gerber 4C over NT.
PASSED HAND: 2/1 response by passed hand is NOT game forcing — just a good hand.\
"""

ACOL_KNOWLEDGE = """\
Standard Acol Complete Reference:
OPENING BIDS: 11-19 HCP. 4+ card major open 1H/1S (with two 4-card majors, open 1H). \
4-card suits: open longest. 12-14 balanced open 1NT (weak NT). \
20-22 balanced open 2NT. 23+ or game-forcing open 2C (2D=negative). \
Strong twos: 2H/2S = 8 playing tricks, 16-22 HCP (one-round force). \
Weak 3-level preempts = 7-card suit. Pass with <11 HCP and no preempt shape.
KEY DIFFERENCE: 4-CARD MAJORS. Open 1H with AKxx Qxxx xx Axx (only 4 hearts). \
Weak NT (12-14) instead of strong (15-17). Strong 2-bids at 2H/2S level.
RESPONSES TO 1H/1S: 6-9 raise with 4+ trump (need 4 since opener may have only 4); \
10-12 limit raise (3-card ok if strong); 13+ game force new suit or jump raise; \
1NT=6-10 (may have 4 cards in unbid major). New suit at 1-level=4+ cards, forcing.
RESPONSES TO 1C/1D: New suit at 1-level preferred; 1NT=6-10; raise=4+ support.
RESPONSES TO 1NT (12-14): 2C=Stayman (need 4-card major, 11+ HCP); \
2D=transfer to 2H, 2H=transfer to 2S; 2NT=invitational (11-12); \
3NT=13-19. 0-10 HCP with no fit: Pass.
OPENER REBIDS: After 1-level response, bid naturally. Reverse=16+. \
After 2-level response: min rebid suit, raise, or 2NT.
COMPETITIVE: Overcall 1-level=8-16 HCP 5+ cards; 1NT overcall=15-18 balanced with stopper; \
Takeout X=support for unbid suits 12+. Negative X. \
Unusual 2NT, Michaels cuebids same as Standard American.
SLAM: Blackwood 4NT=ace ask (0-1-2-3-4); Gerber 4C over NT. Cue-bid controls.
PASSED HAND: may open lighter in 3rd/4th seat. Responses non-forcing.\
"""

PRECISION_KNOWLEDGE = """\
Precision Club Complete Reference:
OPENING BIDS: 1C = 16+ HCP, ARTIFICIAL AND FORCING (any shape). \
1D = 11-15 HCP, may be short (could be 0-1 diamonds with no 5-card suit). \
1H = 11-15 HCP, 5+ hearts. 1S = 11-15 HCP, 5+ spades. \
1NT = 13-15 balanced. 2C = 11-15 HCP, 6+ clubs (natural, NOT strong). \
2D = 11-15 HCP, 4-4-1-4 or 4-4-0-5 (short diamond convention) or 6+ diamonds. \
2H/2S = weak, 5-10 HCP + 6-card suit. 2NT = unusual (minors). \
3-level = preemptive. Pass with <11 HCP and no preempt shape.
KEY DIFFERENCE: 1C is ARTIFICIAL (16+), NOT clubs. 2C is NATURAL (6+ clubs, 11-15). \
All openings except 1C are LIMITED (11-15), making bidding easier after they open.
RESPONSES TO 1C (16+): 1D = 0-7 HCP (negative/waiting); \
1H/1S = 8+ HCP, 5+ cards (positive, game force); \
1NT = 8-13 balanced; 2C/2D = 8+ HCP, 5+ cards (game force); \
2NT = 14+ balanced.
RESPONSES TO 1D (11-15, may be short): 1H/1S = 4+ cards, forcing; \
1NT = 8-10 balanced; 2C = 10+ natural; 2D = 10+ 4+ support; \
3NT = 14-15 balanced, no major.
RESPONSES TO 1H/1S (11-15, 5+): raise with 3+ support; new suit forcing; \
1NT = 6-10; jump raise = limit (10-12).
RESPONSES TO 1NT (13-15): 2C = Stayman; transfers; 2NT = invitational.
COMPETITIVE: Same as standard — overcalls, takeout X, negative X. \
Unusual 2NT, Michaels. Against opponents' 1C (if natural), X = 16+.
SLAM: RKCB 4NT after trump agreed. Cue-bid controls.\
"""

SEF_KNOWLEDGE = """\
Standard European Française (SEF) Complete Reference:
OPENING BIDS: 12-21 HCP. 5+ card major open 1H/1S (higher with 5-5). \
No 5-card major: open 1m (1D with 4+, 1C with 3-3 minors). \
15-17 balanced open 1NT. 20-21 balanced open 2NT. \
2C = STRONG ARTIFICIAL (22+ or game force), 2D=waiting. \
2D/2H/2S = weak, 5-11 HCP + good 6-card suit. \
3-level preempt = 7-card suit. Pass with <12 HCP and no preempt shape.
KEY DIFFERENCE FROM SAYC: Checkback Stayman (Roudi) — after opener rebids 1NT, \
responder's 2C is ARTIFICIAL asking opener to clarify (like New Minor Forcing). \
Opener rebids: 2D = minimum without 3-card major support; 2H = minimum with 3H; \
2S = minimum with 3S; 2NT = maximum without support; 3H/3S = maximum with support.
RESPONSES TO 1H/1S: 6-9 raise with 3+ trump or 1NT (non-forcing); \
10-12 limit raise or 2NT (Jacoby); 13+ 2/1 game force or Jacoby 2NT; \
jump to 4M = preemptive raise. New suit 1-level = forcing.
RESPONSES TO 1C/1D: New suit at 1-level (4+ cards, up the line); 1NT=6-10; \
raise = 5+ support.
RESPONSES TO 1NT (15-17): 2C=Stayman; 2D/2H=transfers; 2NT=invitational; \
4C=Gerber.
OPENER REBIDS: After new suit, rebid naturally. 1NT = 12-14 (then Roudi applies). \
Reverse = 16+. Jump rebid = 16-18.
COMPETITIVE: Overcall = 8-16 + 5+ cards; 1NT overcall = 15-18 + stopper; \
Takeout X = 12+ support for unbid suits. Negative X standard. \
Unusual 2NT, Michaels cuebids.
SLAM: Blackwood 4NT. Cue-bid controls. Grand Slam Force.\
"""

POLISH_CLUB_KNOWLEDGE = """\
Polish Club Complete Reference:
OPENING BIDS: 1C = 12-14 balanced OR 18+ any shape (DUAL MEANING, forcing). \
1D = 12-17 HCP, unbalanced, 4+ diamonds (natural). \
1H = 12-17 HCP, 5+ hearts. 1S = 12-17 HCP, 5+ spades. \
1NT = 15-17 balanced. 2C = 12-17 HCP, 6+ clubs (natural, strong suit). \
2D = weak, 5-10 HCP + 6+ diamonds. 2H/2S = weak, 5-10 + 6-card suit. \
2NT = 20-21 balanced. 3-level = preemptive. Pass with <12 HCP.
KEY DIFFERENCE: 1C is DUAL — either weak balanced (12-14) or very strong (18+). \
Responder must bid to clarify. If opener rebids naturally at low level = weak balanced. \
If opener makes a strong rebid (reverse, jump) = 18+.
RESPONSES TO 1C: 1D = 0-7 any (negative/waiting); \
1H/1S = 8+ HCP, 4+ cards (natural, forcing); \
1NT = 8-11 balanced (no 4-card major); \
2C = 12+ natural or relay; 2D = 8+ 5+ diamonds.
RESPONSES TO 1D (12-17, 4+D): 1H/1S = 4+ cards, forcing; \
1NT = 6-10; 2D = 6-10 with 4+ support; 3D = limit raise.
RESPONSES TO 1H/1S (12-17, 5+): raise with 3+ support; new suit forcing; \
1NT = 6-10; jump raise = limit (10-12).
RESPONSES TO 1NT (15-17): 2C=Stayman; 2D/2H=transfers; 2NT=invitational.
COMPETITIVE: Overcall = 8-16 + 5+ cards; Takeout X = 12+ unbid suits; \
1NT overcall = 15-18 + stopper. Against opponents' 1C, \
X = strong (16+). Unusual 2NT, Michaels.
SLAM: RKCB 4NT. Cue-bid controls once trump agreed.\
"""

SYSTEM_KNOWLEDGE = {
    "SAYC": SAYC_KNOWLEDGE,
    "2/1": TWO_OVER_ONE_KNOWLEDGE,
    "ACOL": ACOL_KNOWLEDGE,
    "PRECISION": PRECISION_KNOWLEDGE,
    "SEF": SEF_KNOWLEDGE,
    "POLISH_CLUB": POLISH_CLUB_KNOWLEDGE,
}

# ── Prompt Templates ─────────────────────────────────────────────────
# "standard" = baseline (identical for all models)
# "knowledge" = includes SAYC reference guide

PROMPT_TEMPLATE = (
    "You are an expert contract bridge player. {convention_details}\n"
    "Your hand: {hand}\n"
    "Auction so far: {auction}\n"
    "Your call? Respond with EXACTLY one bid: "
    "Pass, X, XX, 1C, 1D, 1H, 1S, 1NT, 2C, 2D, 2H, 2S, 2NT, "
    "3C, 3D, 3H, 3S, 3NT, 4C, 4D, 4H, 4S, 4NT, 5C, 5D, 5H, 5S, 5NT, "
    "6C, 6D, 6H, 6S, 6NT, 7C, 7D, 7H, 7S, 7NT.\n"
    "Output ONLY the bid, nothing else."
)

PROMPT_TEMPLATE_KNOWLEDGE = (
    "You are an expert contract bridge player. {convention_details}\n"
    "{knowledge}\n"
    "Your hand: {hand}\n"
    "Auction so far: {auction}\n"
    "Your call? Respond with EXACTLY one bid: "
    "Pass, X, XX, 1C, 1D, 1H, 1S, 1NT, 2C, 2D, 2H, 2S, 2NT, "
    "3C, 3D, 3H, 3S, 3NT, 4C, 4D, 4H, 4S, 4NT, 5C, 5D, 5H, 5S, 5NT, "
    "6C, 6D, 6H, 6S, 6NT, 7C, 7D, 7H, 7S, 7NT.\n"
    "Output ONLY the bid, nothing else."
)

PROMPT_TEMPLATES = {
    "standard": PROMPT_TEMPLATE,
    "knowledge": PROMPT_TEMPLATE_KNOWLEDGE,
}

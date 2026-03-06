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

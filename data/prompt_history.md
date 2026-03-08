# Prompt History & Results

Model: `gemini-3.1-flash-lite-preview` | Oracle: `bba` | Dataset: `ben_sayc_100.csv` (150 pos, 14 deals)

## Results Table

| Prompt | N=50 | N=150 | Net IMPs | Notes |
|--------|------|-------|----------|-------|
| P12 (minimal rules) | - | - | - | Compressed SAYC rules, no examples |
| P18 (base + examples) | 74% | 63.3% | - | First prompt with competitive examples |
| P18 + vote k=9 t=0.5 | 80% | - | - | Voting helped noisy errors |
| P20 (P18 + patches) | **84%** | **70.7%** | +8 | +penalty X, +5-level, +3NT, +weak2, +suit choice |
| P20 + vote k=5 | 84% | - | - | Voting adds no improvement on P20 |
| P21 (P20 + splinters, hardcoded) | - | 65.3% | - | INVALID — hardcoded test hands |
| P21 (generic splinters) | - | 66.7% | +10 | Fixed 7, broke 13 → net regression |
| P22 (P20 simplified) | 86% | 68.7% | -11 | Dropped harmful rules per ablation |

**Note**: ~2% run-to-run variance even at temp=0. Differences < 3% are within noise.

## Ablation Study (P20 decomposition)

Ran `scripts/ablation_test.py` — removes one component at a time to measure contribution.

### Rules Ablation (baseline 68.7%)

| Rule block removed | Acc | Delta | Verdict |
|-------------------|-----|-------|---------|
| F: opening suit choice | 68.7% | +0.0% | neutral |
| D: 5-level decisions | 69.3% | +0.7% | neutral |
| C: penalty doubles | 70.0% | +1.3% | neutral |
| G: responses to 1-minor | 70.0% | +1.3% | neutral |
| H: weak 2 openings | 70.0% | +1.3% | neutral |
| **E: when NOT to compete** | **70.7%** | **+2.0%** | **harmful** |
| **A: competitive bidding rules** | **71.3%** | **+2.7%** | **harmful** |
| **B: takeout double response** | **71.3%** | **+2.7%** | **harmful** |

### Examples Ablation (baseline 68.7%)

| Example group removed | Acc | Delta | Verdict |
|----------------------|-----|-------|---------|
| **competitive examples** | **66.0%** | **-2.7%** | **essential** |
| penalty examples | 68.0% | -0.7% | keep |
| comp_raise example | 68.0% | -0.7% | keep |
| response examples | 69.3% | +0.7% | neutral |
| 3NT example | 69.3% | +0.7% | neutral |
| 5-level example | 69.3% | +0.7% | neutral |
| opening examples | 70.0% | +1.3% | neutral |

### Big Ablations

| Variant | Acc | Delta | Verdict |
|---------|-----|-------|---------|
| Drop ALL examples | 39.3% | **-29.3%** | Examples are CRITICAL |
| Drop ALL rules | 68.0% | -0.7% | Rules nearly useless |
| **Drop A+B+E (3 harmful rules)** | **73.3%** | **+4.7%** | **Best variant** |
| Drop A+B+C+E+G+H (6 rules) | 71.3% | +2.7% | Good but less |

### Key Conclusions

1. **Examples drive accuracy** — removing all examples drops 29%. Removing all rules drops 0.7%.
2. **Some rules actively hurt** — competitive rules (A), takeout X (B), "don't compete" (E) confuse flash-lite.
3. **Competitive examples are the most valuable** single component (-2.7% when removed).
4. **Flash-lite is too small** for complex rules. It can pattern-match from examples but can't reliably apply abstract rules in context.
5. **The optimal prompt for flash-lite**: SAYC_KNOWLEDGE + few essential rules (penalty X, 5-level) + ALL examples.

## DD/IMP Analysis

| Prompt | Accuracy | Zero IMP | LLM better | BBA better | Net IMPs | Mean IMP/pos |
|--------|----------|----------|-----------|-----------|----------|-------------|
| P20 | 70.7% | 75.3% | 10.0% | 14.7% | **-13** | -0.09 |
| P21 (generic) | 66.7% | 86.7% | 7.3% | 6.0% | +10 | +0.07 |
| **P22 (simplified)** | 68.7% | 73.3% | **14.0%** | **12.7%** | **+13** | **+0.09** |

**Key**: P22 has lower bid accuracy but **better IMP performance** (+13 vs -13).
P20's extra rules cause overbidding that costs IMPs. P22 is more conservative and cost-effective.

**IMP findings**: Most bid "errors" are bridge-inconsequential (86-88% zero IMP impact). The 30% error rate overstates actual cost at the table.

## P20 vs P21: Splinter Analysis

P21 added splinter/cuebid rules to fix specific errors:

| What | Fixed | Broken |
|------|-------|--------|
| Splinter recognition (#61) | Pass → 4S | - |
| Preempt raise (#72) | Pass → 4S | - |
| Bid after opp X (#121) | Pass → 1H | - |
| Over-aggressive 4S (#60, #62) | - | Pass → 4S (wrong hand!) |
| Too-quick signoff (#63) | - | 4NT → 4H |
| Opening too light (#76, #83, #95) | - | Pass → 1S/1D |

Net: fixed 7, broke 13. The model over-generalizes: sees "splinter" rules → bids 4S in ANY auction with 4C, regardless of seat.

## Bidding System Comparison (P30, N=150, vs BBA)

Tested 6 bidding systems using P30 (system-adaptive P22). Each system gets its own
knowledge reference block + the P22 examples. DD/IMP analysis only (final contract quality).

| System | Accuracy | Net IMPs | IMP/pos | LLM+ | Oracle+ | Same |
|--------|----------|----------|---------|------|---------|------|
| **ACOL** | 66.0% | **+15** | **+0.10** | 15 | 9 | 126 |
| SAYC | 70.7% | +1 | +0.01 | 11 | 10 | 129 |
| PRECISION | 67.3% | -1 | -0.01 | 11 | 10 | 129 |
| 2/1 | 66.7% | -9 | -0.06 | 12 | 13 | 125 |
| POLISH_CLUB | 71.3% | -9 | -0.06 | 8 | 10 | 132 |
| SEF | 69.3% | -16 | -0.11 | 10 | 12 | 128 |

### Key Findings

1. **ACOL wins on DD/IMP** (+15) despite lowest bid accuracy (66.0%). 4-card majors + weak NT
   make major fits easier to find → better contracts.
2. **Polish Club highest bid accuracy** (71.3%) but negative IMPs (-9). Conservative = matches
   oracle bids but doesn't optimize contracts.
3. **SEF is worst** (-16 IMPs). Roudi/Checkback complexity confuses flash-lite.
4. **Accuracy ≠ contract quality**: the best system by IMP (ACOL) has the worst accuracy.
   This mirrors P22 vs P20 (lower accuracy, better IMPs).
5. **SAYC and SEF are closest** (11 different bids). Precision diverges most from all others (29-36 diffs).
6. Script: `scripts/system_comparison.py`, results: `data/system_comparison.json`

## Cost Estimates (per 150-position run)

| Model | Input tokens/pos | Cost/run |
|-------|-----------------|----------|
| gemini-3.1-flash-lite | ~1570 (P20) / ~1300 (P22) | ~$0.006 |
| gemini-3.1-flash | ~1570 | ~$0.024 |
| gemini-3.1-pro | ~1570 | ~$0.30 |
| gpt-4o-mini | ~1570 | ~$0.04 |

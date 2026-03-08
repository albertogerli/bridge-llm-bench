# What Happens When You Teach an LLM Six Different Bidding Systems — And Why Acol Wins

I've been running an experiment that I think raises some provocative questions about how we evaluate bidding — both for AI and perhaps for ourselves.

The setup: I took Google's smallest, cheapest model (Gemini Flash Lite — costs about $0.006 per 150 hands) and systematically optimized its bidding prompt against 150 positions from 14 deals, with BBA as the SAYC oracle. Then I ran the same hands through six different bidding systems — SAYC, 2/1 GF, Acol, Precision, SEF, and Polish Club — and scored them not by bid accuracy, but by **double-dummy IMP outcome** of the implied contract.

The results surprised me.

## Part 1: Teaching a Small Model to Bid

The journey from "barely functional" to "respectable club player" was instructive. The model started at ~55% accuracy with a basic SAYC prompt. I went through roughly a dozen iterations (P12 through P22), and here's what I learned:

**Rules are nearly useless. Examples are everything.**

I ran a systematic ablation study — removing one component at a time to measure its contribution. The results were stark:

- Remove **all examples**: accuracy drops 29 percentage points (from 69% to 39%)
- Remove **all rules**: accuracy drops 0.7 percentage points

Think about that. Every carefully crafted rule about competitive bidding, penalty doubles, suit choice — the model barely noticed when I deleted them all. But take away the worked examples and it collapses.

Even more interesting: **three rules actively hurt accuracy** by 2-3% each. Competitive bidding rules, takeout double responses, and "when NOT to compete" guidelines all confused the model into making worse decisions. The small model can pattern-match from examples but can't reliably apply abstract logic in context.

The single most valuable prompt component? Competitive bidding examples. One example alone was worth 2.7% accuracy:

```
You hold: Q52  6543  K732  AJ  (10 HCP)

Partner opened 1S in 3rd seat. RHO overcalls 1NT.

The model's instinct: Pass.
After seeing the example: Double (competitive, showing 3-card spade support + values).
```

Another instructive case was this monster hand, appearing repeatedly through a wild competitive auction:

```
You hold: 54  void  AQ953  AKQJT6  (16 HCP, 11 cards in the minors)

After P-1D-X-1S, every oracle agrees: 5C. Jump to game.
You have 11 cards in the minors and a void. Don't mess around.
```

The simplified prompt (P22) bid only 2C here — the 5-level "stop" rule had been over-internalized, making the model timid even when leaping to game was clearly right. Teaching a small model *both* halves of the judgment — "bid 5C with 11-card minors" AND "pass when opponents push to 5D later in the same auction" — turned out to be one of the hardest prompt engineering problems. The model that learned to stop competing also lost the courage to bid game.

## Part 2: The System Experiment

Once I had a solid prompt (P22 — simplified based on the ablation), I asked a different question: **what if we change the bidding system itself?**

I wrote detailed knowledge references for all six systems, kept the same examples, and ran each system on the same 150 positions. I measured **only final contract quality** using double-dummy analysis and IMP scoring.

| System | Bid Accuracy | Net IMPs vs BBA | IMP/hand |
|--------|-------------|-----------------|----------|
| **Acol** | **66.0%** | **+15** | **+0.10** |
| SAYC | 70.7% | +1 | +0.01 |
| Precision | 67.3% | -1 | -0.01 |
| 2/1 GF | 66.7% | -9 | -0.06 |
| Polish Club | 71.3% | -9 | -0.06 |
| SEF | 69.3% | -16 | -0.11 |

Read that table carefully. **The system with the lowest bid accuracy produced the best contracts.** Acol matched the SAYC oracle's bids only 66% of the time, but when you actually scored the contracts double-dummy, it gained 15 IMPs over BBA.

## Why Acol?

My working theory: **4-card majors + light openings make it easier for a weak model to find major-suit fits.**

Consider this hand in 3rd seat after two passes:

```
You hold: J83  QJT  QT  K9852  (10 HCP)

SAYC model: Pass. Textbook — no 5-card suit, only 10 HCP.
Acol model: 1C. Light opening, weak NT range — perfectly standard Acol.
```

The Acol model opened light — "wrong" by SAYC standards, but the 1C opening gives partner information. A pass gives them nothing. In Acol, you can open this hand without apology. The resulting auction might well reach a better spot precisely because someone opened the bidding.

Or take this passout seat decision:

```
You hold: 2  T95  K74  AT9876

Auction: P-1S-4H-4S-P-?

The SAYC model bid 5H. Disaster — we have no heart fit,
partner bid spades, and we're at the 5-level with a misfit.

The Acol model passed. So did BBA.
```

The SAYC model, primed by competitive rules, talked itself into a 5-level adventure. The Acol model — perhaps because its "keep it simple, bid what you've got" philosophy discouraged heroics — found the right pass.

## The Other Systems

- **Polish Club** had the **highest accuracy** (71.3%) but negative IMPs. Ultra-conservative: matched the oracle's bids beautifully but never found the creative contracts.
- **SEF was worst** (-16 IMPs). The Roudi/Checkback Stayman convention adds complexity that Flash Lite simply can't handle. It's a great convention for humans who've discussed it — terrible for a model that half-remembers the rules.
- **2/1 GF** performed poorly (-9 IMPs). The game-forcing 2/1 structure requires accurate hand evaluation over multiple rounds — exactly what a small model struggles with.
- **Precision** was neutral (-1 IMP). The strong 1C / limited other openings structure is clean and logical, but the artificial 1C response structure didn't translate well.

## The Meta-Lesson

There are two findings here that I think matter beyond AI:

**1. Accuracy is not quality.** A model (or a player) can match the "book bid" more often and still produce worse contracts. Polish Club matched BBA 71% of the time and lost IMPs. Acol matched 66% of the time and gained IMPs. The bids that "look wrong" by SAYC standards sometimes find better contracts.

**2. Simpler systems may be better for weaker bidders.** Acol's 4-card majors and light openings require less judgment to get right. You hold four spades and 11 points? Open 1S. In SAYC you pass, and now you need to find a way back in during competitive bidding — which is where errors multiply.

This is a sample of 14 deals, and Flash Lite is far from a strong model. The ~2% run-to-run variance at temperature 0 means differences under 5 IMPs are noise. But the +15 for Acol and -16 for SEF feel real, and the direction is consistent with what we know about system complexity and player strength.

I'd love to see this replicated with larger samples and stronger models. Does Acol's advantage disappear when the model is smart enough to handle 5-card major sequences correctly? Or is there something fundamentally more forgiving about 4-card major systems?

---

*Technical details: 150 positions from 14 deals, BBA oracle (SAYC), Gemini Flash Lite (temp=0), double-dummy scoring via endplay library, all code open-source. The ablation study decomposed the prompt into 8 rule blocks and 7 example groups, testing each removal independently.*

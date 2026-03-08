# Update 2: Beyond Accuracy — Evaluating LLM Bids by Double-Dummy Outcome

*Follow-up to [Can LLMs Play SAYC?](link-to-original-post) and [Update 1: Oracle Validation](link-to-update-1)*

Hi everyone,

Several commenters on my original post made a point that stuck with me: **exact-match accuracy against an oracle is the wrong metric.** If the oracle bids 2H and the LLM bids 3H, that's a "miss" in my benchmark — but it might lead to the exact same contract. Conversely, if the LLM bids 1NT instead of 1H, that's also a "miss" but could be catastrophic.

So I built a double-dummy evaluation layer on top of the benchmark. Here's what it reveals.

## The Method

For each of the 150 test positions:

1. **Reconstruct the full deal** (all four hands) from the dataset — 14 deals total
2. **Compute a double-dummy table** for each deal using [endplay](https://github.com/dominicprice/endplay) (5 strains x 4 declarers = 20 trick counts per deal)
3. **Score each bid by its DD outcome**: if the LLM bids 3H, compute how many tricks 3H makes and what the duplicate score would be. Same for the oracle's bid.
4. **Convert the score difference to IMPs** using the standard WBF table

This gives us not just "did the LLM match the oracle?" but "**how much does the difference cost (or gain) at the table?**"

## The Headline

| Metric | Value |
|--------|-------|
| Bid-level accuracy (P20 vs BBA) | **70.7%** (106/150) |
| Positions with zero IMP impact | **88.0%** (132/150) |
| LLM better than oracle (DD) | 6.7% (10/150) |
| Oracle better than LLM (DD) | 5.3% (8/150) |
| Net IMPs | **+8** (LLM better) |
| Mean IMP/position | +0.05 |

Read that again: **the LLM matches the oracle on 70.7% of bids, but 88% of all positions produce the exact same IMP result.** The 30% "error rate" mostly consists of bids that don't actually matter at the table — same strain at a different level, competitive raises that don't change the final contract, or Pass vs. a partscore bid in a hand where both sides have limited values.

And when bids *do* differ in outcome, the LLM and the oracle roughly break even. The LLM occasionally finds contracts the oracle misses, and occasionally drops ones the oracle finds. Net result: essentially zero.

## Hand 1: The LLM Finds a Game (+10 IMPs)

The LLM's best result came on this deal:

```
                North
                S  KQT4
                H  AQ96542
                D  -
                C  32
West                            East
S  A76                          S  985
H  J                            H  87
D  Q983                         D  76542
C  AKJT9                        C  874
                South
                S  J32
                H  KT3
                D  AKJT
                C  Q65
```

The (WBridge5) auction reached `1D - 1H - Pass - 2S - Pass - Pass` and South held:

**S: J32 &nbsp; H: KT3 &nbsp; D: AKJT &nbsp; C: Q65** &nbsp; (14 HCP, balanced)

The oracle (BBA) passed. The LLM bid **3NT**.

This is a terrific balancing bid. South has 14 HCP, a diamond suit that's going to run (AKJT), a heart stopper (KT3), and the opponents have stopped low — there's clearly game somewhere. Double-dummy, 3NT by South makes 10 tricks for **+430**.

What I love about this bid is that it shows genuine bridge judgment: South didn't just pattern-match to "I have 14 points, I bid 3NT." It recognized a balancing opportunity in a competitive sequence. The opponents stopped at the 2-level, partner has values (opened and bid again), and South's hand is perfectly suited for notrump. An experienced tournament player would make the same bid — and collect 10 tricks on the diamond suit.

**Result: LLM +430, Oracle 0. Swing: +10 IMPs.**

## Hand 2: The LLM Misses a Game (-9 IMPs)

The LLM's worst result — twice on the same deal, in fact:

```
                North
                S  986
                H  Q8642
                D  972
                C  83
West                            East
S  AK74                         S  QJT
H  A9                           H  KT73
D  QJ4                          D  T86
C  QJ75                         C  K92
                South
                S  532
                H  J5
                D  AK53
                C  AT64
```

East-West have a combined 26 HCP and a 7-card spade fit (AK74 opposite QJT). The DD table confirms 4S makes exactly — 10 tricks, +420.

After the auction reached `Pass - 1S - Pass - 4C - Pass`, East held:

**S: QJT &nbsp; H: KT73 &nbsp; D: T86 &nbsp; C: K92** &nbsp; (10 HCP)

The oracle (BBA) bid **4S**. The LLM **passed**.

Partner's 4C over 1S is a game-forcing raise — in most partnerships either a splinter (short clubs, spade support) or a strong club raise. Either way, partner is showing game values and spade support. The correct action is straightforward: sign off in 4S.

The LLM seems to have been confused by the 4C response. It may have interpreted 4C as a natural club bid rather than a conventional raise, or it may have been put off by having only three spades (QJT). But the auction is unambiguous: partner has shown a game-forcing hand with spade support. You bid 4S and take your 10 tricks.

What makes this worse is that the same error happened again later in the deal (position 66), when the auction reached an even more explicit point (`Pass - 1S - Pass - 4C - Pass - 4D - Pass - 4H - Pass`) — partner's subsequent cuebids made it crystal clear that 4S was the destination. The LLM passed again. Two times -9 IMPs on the same deal: -18 IMPs total.

**Result: LLM 0, Oracle +420. Swing: -9 IMPs (twice).**

## What the DD Numbers Tell Us

The most interesting finding isn't any single hand — it's the distribution:

| Category | Positions | % |
|----------|-----------|---|
| Same bid, same outcome | 106 | 70.7% |
| Different bid, same IMP result | 26 | 17.3% |
| LLM bid scores better (DD) | 10 | 6.7% |
| Oracle bid scores better (DD) | 8 | 5.3% |

**Nearly 88% of all positions produce identical IMP results**, whether the LLM matches the oracle or not. This means bid-level accuracy significantly *overstates* how often the LLM actually goes wrong in a way that matters at the table.

For the remaining 12% where the outcome differs: 10 swings favor the LLM, 8 favor the oracle, with roughly equal magnitude. The LLM's wins tend to come from aggressive game-finding bids in competitive auctions. Its losses tend to come from failing to recognize game-forcing sequences — particularly splinters and cuebids.

## The Oracle Comparison (for reference)

I also ran the DD analysis on the three oracles against each other:

| Comparison | Net IMPs | Mean IMP/pos |
|-----------|----------|-------------|
| BBA vs WBridge5 | **+88** | +0.59 |
| Ben vs WBridge5 | **+106** | +0.71 |
| BBA vs Ben | **-20** | -0.13 |

BBA and Ben are nearly identical in DD terms (-20 IMPs over 150 positions = essentially noise). Both significantly outperform WBridge5, confirming that WBridge5 is playing a clearly inferior system — at least for these 14 deals.

## Honest Limitations

A few caveats about this analysis:

1. **Doubles and cuebids are scored as zero.** When BBA doubles (a competitive action) and the LLM overcalls (a natural bid), the overcall gets a DD score but the double gets 0, because a double isn't a contract. This inflates the LLM's advantage by approximately 8 IMPs — meaning the *true* net is closer to zero. I'm working on a better scoring model for non-contract bids.

2. **Non-vulnerability assumed throughout.** The dataset doesn't include vulnerability information. This affects the magnitude of scores (especially for game and slam bonuses) but shouldn't change the relative ordering much.

3. **14 deals is a small sample.** With only 14 unique deals, individual hands can have outsized influence on the aggregate numbers. Deal 6 alone accounts for -18 IMPs against the LLM.

4. **We score single bids, not full auctions.** The DD analysis evaluates each bid in isolation — "what if this bid were the final contract?" In reality, a bid at move 3 of a 12-bid auction has a complex downstream effect that we can't fully model without simulating the complete auction.

## What This Means

The bid-level accuracy of 70.7% is a **lower bound** on the LLM's competitive performance. The DD analysis shows that the actual practical impact is much smaller than the error rate suggests. When measured by the metric that actually matters at the table — IMPs — the LLM is essentially even with a rule-based SAYC oracle.

This doesn't mean the LLM is as *good* as BBA. It means that most of its "errors" are bridge-inconsequential — the kind of disagreements that you'd see between any two competent SAYC players. The meaningful errors (missing game forces, failing to recognize splinters) are real but rare, and they're partially offset by cases where the LLM shows superior competitive judgment.

For tournament players: if your robot partner bids "wrong" 30% of the time but the average IMP cost is +0.05 per board, you're not losing to the field — you're holding your own.

## What's Next

1. **Better scoring for competitive bids** — Doubles, cuebids, and other non-contract calls need a more sophisticated DD evaluation (e.g., "what's the best contract reachable from this bid?")
2. **Vulnerability modeling** — Adding per-deal vulnerability to sharpen the IMP calculations
3. **Full auction simulation** — Instead of scoring single bids, simulate what happens when the LLM's bid replaces the oracle's bid at one point, and let the rest of the auction unfold
4. **Multi-model comparison** — Run the DD analysis on all tested models, not just Flash Lite, to see if bigger models make more or less costly errors

The code is all at **[bridge-llm-bench](https://github.com/albertogerli/bridge-llm-bench)** — including `scripts/ev_analysis.py` which runs the full DD pipeline.

---

*Technical note: DD tables are computed using the [endplay](https://github.com/dominicprice/endplay) library wrapping Bo Haglund's DDS solver. All 14 deals can be analyzed in under 2 seconds. Results are cached to `data/dd_tables.json` for reproducibility.*

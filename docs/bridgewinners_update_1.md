# Update: Oracle Validation and Why the "Correct Answer" Problem Matters More Than the AI

*Follow-up to [Can LLMs Play SAYC? Building a Bridge Bidding Benchmark](link-to-original-post)*

Hi everyone,

Thank you for the incredibly insightful comments on the original post. Several of you raised points that fundamentally changed how I think about this project, and I want to share the results.

## The Oracle Problem (Revisited)

In the original post I described discovering that WBridge5 doesn't actually play SAYC — it agrees with SAYC engines only about 44% of the time. I switched to Ben SAYC as the reference oracle and scores improved. But a fair question remained: **how do we know Ben SAYC is actually playing good SAYC?**

Edward Piwowar (author of BBA — Bridge Bidding Analyser) pointed out something important in the comments: Ben's neural network was actually *trained on 1.2 million deals bid by BBA*, with roughly 90% fidelity. So Ben is essentially a student that learned from BBA's rule-based SAYC engine. This gave me an idea: if I could generate BBA-style deterministic SAYC bids for my test positions, I'd have an independent validation of Ben's quality as an oracle.

I created a hand-analyzed SAYC reference for all 150 test positions, following strict SAYC rules (5-card majors, 15-17 NT, weak 2s with 6-10 HCP, standard competitive guidelines). Here's what the three-way comparison looks like:

## Oracle Agreement (N=150 positions)

| Comparison | Agreement | Rate |
|-----------|-----------|------|
| **Ben SAYC vs SAYC Reference** | 129/150 | **86.0%** |
| WBridge5 vs SAYC Reference | 80/150 | 53.3% |
| WBridge5 vs Ben SAYC | 67/150 | 44.7% |

The 86% agreement between Ben and the hand-analyzed SAYC reference is exactly what you'd expect given that Ben was trained on BBA at ~90% fidelity. The remaining 14% disagreements are almost entirely in competitive sequences where multiple bids are reasonable — Ben tends to bid more aggressively (5S where strict SAYC says Pass, 4H where 2H is more conservative, etc.).

Meanwhile, WBridge5 continues to diverge from both SAYC sources at roughly 45-53%, confirming it plays its own system.

**Key takeaway: Ben SAYC is a legitimate SAYC oracle.** It's not perfect, but the noise it introduces is small and predictable — mostly in the direction of "slightly more aggressive in competitive auctions."

## LLM Accuracy Is Stable Across Oracles

The real question is whether the choice of oracle changes how we rank the LLMs. Here's the optimized Gemini Flash Lite (our smallest model) tested against both oracles:

| Configuration | vs Ben SAYC | vs SAYC Reference |
|--------------|-------------|-------------------|
| P18 prompt, single call | 72% | 74% |
| P18 prompt + majority voting (k=9) | **80%** | **80%** |

The accuracy is nearly identical regardless of which oracle you use. This is an important validation: **the LLM ranking is robust to oracle choice**, at least within the range of legitimate SAYC interpretations.

Here's the multi-model comparison on the basic prompt (N=25 positions, no prompt optimization):

| Model | vs Ben SAYC | vs SAYC Reference |
|-------|-------------|-------------------|
| Gemini 3.1 Pro | 56% | 56% |
| Gemini Flash Lite | 48% | 52% |
| Claude Haiku 4.5 | 48% | 52% |
| Claude Opus 4.6 | 44% | 48% |
| GLM-4.7 | 44% | 44% |
| GPT-5.2 | 44% | 44% |

The relative ranking stays the same. Gemini Pro leads, followed by a cluster of Flash Lite/Haiku, then the rest. Interestingly, the biggest and most expensive models (Opus, GPT-5.2) don't outperform the smaller ones on bridge bidding — a pattern I noted in the original post.

## What the Disagreements Tell Us

Looking at the 21 positions where Ben and the SAYC reference disagree, a clear pattern emerges:

- **Ben bids more aggressively in competition** — 5S over 4S when vulnerable, 4H with a 6-card suit and 7 HCP, 6H when the SAYC reference says Pass
- **Ben occasionally opens light** — 1S with AK953 and 10 HCP where strict SAYC passes
- **Ben responds more creatively** — 3NT with a good hand rather than conservative 2NT

These are all judgment calls where reasonable SAYC players would disagree. None of them are "errors" in the usual sense — they're stylistic preferences within the SAYC framework. This is actually a useful finding: **the ~14% Ben-reference disagreement rate gives us a rough upper bound on how much SAYC experts might disagree with each other on the same hands.**

## Implications for Benchmark Design

Richard Willey made an excellent point in the comments about SAYC having "holes and inconsistencies" — and suggested that well-defined modern systems (2/1 GF, Acol, Precision) might be better benchmark targets. I think he's right for the long term, but the oracle validation work shows something encouraging: even with SAYC's ambiguities, we can get consistent enough oracles to meaningfully rank LLMs.

The framework now supports multiple oracles (Ben SAYC, WBridge5, SAYC reference) selectable via a single flag:

```bash
python scripts/optimize_prompt.py --prompt_id 18 --oracle bba    # SAYC reference
python scripts/optimize_prompt.py --prompt_id 18 --oracle ben    # Ben SAYC
python scripts/optimize_prompt.py --prompt_id 18 --oracle wbridge5  # WBridge5
```

This infrastructure is ready for when we add 2/1 GF, Precision, and Acol reference bids.

## Summary of New Numbers

| Metric | Value |
|--------|-------|
| Ben vs SAYC reference agreement | **86%** (on 150 positions) |
| WBridge5 vs SAYC sources | ~45-53% (confirms non-SAYC) |
| Best LLM accuracy (Flash Lite + voting) | **80%** (stable across oracles) |
| Oracle choice effect on LLM ranking | **None** (same relative order) |

## What's Next

1. **Edward's BBA bids** — I'd still love to get actual BBA-generated bids for these 150 positions. My hand-analyzed reference follows SAYC rules but BBA implements them algorithmically, which would be even more consistent. Edward, if you're reading this, I've prepared the positions in PBN format ready for import.

2. **Multi-system benchmarking** — Following Richard's suggestion, the next major milestone is testing LLMs on 2/1 GF, Precision, and Acol. BBA supports all of these systems, which would give us a fascinating comparison: can an LLM switch conventions just by changing the prompt?

3. **Larger model leaderboard** — Now that the oracle is validated, I want to run all available models through the optimized P18 prompt with voting. The preliminary results suggest model size doesn't strongly predict bridge bidding ability, which is an interesting finding on its own.

4. **Double-dummy evaluation** — Several commenters suggested moving beyond "match the oracle" toward "evaluate the outcome." If two bids lead to the same makeable contract, they should both get credit. This is the natural next step toward answering the harder question: not "does the LLM bid like a SAYC engine" but "does the LLM bid *well*?"

The code is all open-source at **[bridge-llm-bench](https://github.com/albertogerli/bridge-llm-bench)** — including the oracle comparison tools, prompt optimization framework, and all datasets.

Looking forward to your feedback!

---

*P.S. — For the technically curious: the 150 test positions come from 14 different deals, covering a wide range of auction situations from opening bids through competitive sequences to slam exploration. The positions are exported in PBN format and available in the repo's `data/export/` directory if you'd like to bid them yourself and compare.*

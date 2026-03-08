"""
Statistics aggregation for bridge card play benchmark.
"""

from dataclasses import dataclass
from typing import List

from .engine import PlayResult, _is_declarer_side


@dataclass
class BenchmarkStats:
    """Aggregate statistics across multiple played deals."""
    n_deals: int

    # Opening lead
    lead_dd_match_pct: float
    lead_mistakes: int
    lead_avg_trick_cost: float

    # Declarer play
    declarer_total_cards: int
    declarer_dd_match_pct: float
    declarer_mistakes: int
    declarer_avg_tricks: float
    declarer_dd_optimal_tricks: float

    # Defense
    defense_total_cards: int
    defense_dd_match_pct: float
    defense_mistakes: int

    # Overall
    total_imp_vs_dd: int
    mean_imp_per_deal: float
    contracts_made_pct: float


def compute_stats(results: List[PlayResult]) -> BenchmarkStats:
    """Compute aggregate statistics from play results."""
    n = len(results)
    if n == 0:
        return BenchmarkStats(
            n_deals=0, lead_dd_match_pct=0, lead_mistakes=0, lead_avg_trick_cost=0,
            declarer_total_cards=0, declarer_dd_match_pct=0, declarer_mistakes=0,
            declarer_avg_tricks=0, declarer_dd_optimal_tricks=0,
            defense_total_cards=0, defense_dd_match_pct=0, defense_mistakes=0,
            total_imp_vs_dd=0, mean_imp_per_deal=0, contracts_made_pct=0,
        )

    # Opening lead
    lead_matches = sum(1 for r in results if r.lead_card == r.lead_dd_optimal)
    lead_mistakes = sum(1 for r in results if r.lead_is_mistake)

    # Count declarer/defense cards and DD matches
    decl_cards = 0
    decl_dd_match = 0
    decl_mistakes = 0
    def_cards = 0
    def_dd_match = 0
    def_mistakes = 0

    for r in results:
        for trick in r.tricks:
            for cp in trick.cards:
                if _is_declarer_side(cp.seat, r.declarer):
                    decl_cards += 1
                    if cp.card == cp.dd_optimal:
                        decl_dd_match += 1
                    if cp.is_mistake:
                        decl_mistakes += 1
                else:
                    def_cards += 1
                    if cp.card == cp.dd_optimal:
                        def_dd_match += 1
                    if cp.is_mistake:
                        def_mistakes += 1

    # Tricks
    decl_tricks_total = 0
    dd_tricks_total = 0
    contracts_made = 0
    for r in results:
        decl_side_tricks = r.tricks_won_ns if r.declarer in ("N", "S") else r.tricks_won_ew
        decl_tricks_total += decl_side_tricks

        # DD optimal tricks
        dd_key = None
        for key in r.tricks[0].cards[0].__dict__:  # just need contract info
            pass
        # Use contract info from result
        contract_parts = r.contract_str.split()
        level = int(contract_parts[0][0])
        needed = level + 6
        if decl_side_tricks >= needed:
            contracts_made += 1

        # DD optimal from the play result
        dd_tricks_total += (r.contract_score_dd > 0) * 13  # rough proxy

    # Better: use contract_score to infer DD tricks
    # Actually, just sum IMP diffs
    total_imp = sum(r.imp_diff_vs_dd for r in results)

    # Average declarer tricks
    avg_decl = decl_tricks_total / n if n else 0

    return BenchmarkStats(
        n_deals=n,
        lead_dd_match_pct=lead_matches / n * 100 if n else 0,
        lead_mistakes=lead_mistakes,
        lead_avg_trick_cost=0,  # computed separately if needed
        declarer_total_cards=decl_cards,
        declarer_dd_match_pct=decl_dd_match / decl_cards * 100 if decl_cards else 0,
        declarer_mistakes=decl_mistakes,
        declarer_avg_tricks=avg_decl,
        declarer_dd_optimal_tricks=0,  # would need per-deal DD data
        defense_total_cards=def_cards,
        defense_dd_match_pct=def_dd_match / def_cards * 100 if def_cards else 0,
        defense_mistakes=def_mistakes,
        total_imp_vs_dd=total_imp,
        mean_imp_per_deal=total_imp / n if n else 0,
        contracts_made_pct=contracts_made / n * 100 if n else 0,
    )


def print_stats(stats: BenchmarkStats):
    """Print formatted statistics."""
    print(f"\n{'='*60}")
    print(f"  Bridge Card Play Benchmark — {stats.n_deals} deals")
    print(f"{'='*60}")

    print(f"\n  OPENING LEAD")
    print(f"    DD match:  {stats.lead_dd_match_pct:.1f}%")
    print(f"    Mistakes:  {stats.lead_mistakes}")

    print(f"\n  DECLARER PLAY ({stats.declarer_total_cards} cards)")
    print(f"    DD match:  {stats.declarer_dd_match_pct:.1f}%")
    print(f"    Mistakes:  {stats.declarer_mistakes} trick-losing plays")
    print(f"    Avg tricks: {stats.declarer_avg_tricks:.1f}")

    print(f"\n  DEFENSE ({stats.defense_total_cards} cards)")
    print(f"    DD match:  {stats.defense_dd_match_pct:.1f}%")
    print(f"    Mistakes:  {stats.defense_mistakes} trick-losing plays")

    print(f"\n  OVERALL")
    print(f"    Contracts made: {stats.contracts_made_pct:.1f}%")
    print(f"    Total IMPs vs DD: {stats.total_imp_vs_dd:+d}")
    print(f"    Mean IMP/deal:   {stats.mean_imp_per_deal:+.2f}")
    print(f"{'='*60}\n")

from models import Outcome, OddsLine, ArbOpportunity


def implied_probability(odds: float) -> float:
    if odds <= 0:
        return float("inf")
    return 1.0 / odds


def detect_arb(outcomes: list) -> tuple:
    """Returns (is_arb, implied_sum)."""
    implied_sum = sum(implied_probability(o.odds) for o in outcomes)
    return implied_sum < 1.0, implied_sum


def calculate_stakes(outcomes: list, bankroll: float) -> tuple:
    """Returns (stakes_list, target_payout, guaranteed_profit)."""
    implied_sum = sum(implied_probability(o.odds) for o in outcomes)
    target_payout = bankroll / implied_sum
    stakes = []
    for outcome in outcomes:
        stake = target_payout / outcome.odds
        stakes.append((outcome, round(stake, 2)))
    profit = round(target_payout - bankroll, 2)
    return stakes, round(target_payout, 2), profit


def find_best_odds_per_outcome(lines: list) -> list:
    """
    Given OddsLines for the same match+market from different bookmakers,
    returns the best (highest) Outcome per distinct outcome name.
    """
    best: dict = {}
    for line in lines:
        for outcome in line.outcomes:
            key = outcome.name.strip().lower()
            if key not in best or outcome.odds > best[key].odds:
                best[key] = outcome
    return list(best.values())


def scan_for_arbs(all_lines: list, bankroll: float) -> list:
    """Groups lines by (match_id, market), finds arbs, returns sorted by profit desc."""
    groups: dict = {}
    for line in all_lines:
        key = (line.match_id, line.market)
        if key not in groups:
            groups[key] = []
        groups[key].append(line)

    opportunities = []
    for (match_id, market), lines in groups.items():
        best_outcomes = find_best_odds_per_outcome(lines)
        if len(best_outcomes) < 2:
            continue
        is_arb, implied_sum = detect_arb(best_outcomes)
        if is_arb:
            stakes, target_payout, profit = calculate_stakes(best_outcomes, bankroll)
            arb_percent = round((1.0 - implied_sum) * 100, 2)
            opp = ArbOpportunity(
                odds_line=lines[0],
                arb_percent=arb_percent,
                implied_sum=round(implied_sum, 6),
                stakes=stakes,
                bankroll=bankroll,
                guaranteed_profit=profit,
                target_payout=target_payout,
            )
            opportunities.append(opp)

    opportunities.sort(key=lambda x: x.arb_percent, reverse=True)
    return opportunities

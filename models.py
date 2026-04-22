from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Outcome:
    name: str
    odds: float
    bookmaker: str


@dataclass
class OddsLine:
    match_id: str
    team_home: str
    team_away: str
    market: str  # "h2h" | "maps_total"
    outcomes: list
    source: str = "manual"  # "hltv" | "manual"
    commence_time: datetime = field(default_factory=datetime.now)
    game_datetime: str = ""


@dataclass
class ArbOpportunity:
    odds_line: OddsLine
    arb_percent: float
    implied_sum: float
    stakes: list  # list of (Outcome, float)
    bankroll: float
    guaranteed_profit: float
    target_payout: float

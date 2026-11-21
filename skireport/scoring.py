"""Deterministic status / condition / confidence rules. Every output can be traced to these rules."""
from dataclasses import dataclass, field

from .config import (GOOD_DEPTH_IN, SKIABLE_DEPTH_IN, SNOW_LEVEL_RISK_FACTOR, SNOW_LEVEL_RISK_FT, SOURCE_WEIGHT,
                     WEEKEND_LEAD_FACTOR)

LABELS = {5: "Powder", 4: "Packed powder", 3: "Packed powder", 2: "Crust / ice"}
# Nothing packs snow in the backcountry: the same scores describe settled snow there.
BACKCOUNTRY_LABELS = {**LABELS, 4: "Settled powder", 3: "Firm / settled"}
SPRING_MONTHS = (3, 4, 5, 6)


@dataclass
class SnowState:
    depth_in: float | None
    new_3d_in: float = 0.0
    new_7d_in: float = 0.0
    rain_since_snow: bool = False
    thaw_since_snow: bool = False
    strong_wind: bool = False
    groomed_hours: float | None = None


@dataclass
class Rated:
    value: str
    confidence: int
    basis: list = field(default_factory=list)


def condition(kind, s: SnowState, month):
    if s.depth_in is None:
        return None, "Unknown"
    if s.depth_in < SKIABLE_DEPTH_IN[kind]:
        return 1, ("No snow" if s.depth_in < 1 else "Too thin")
    labels = BACKCOUNTRY_LABELS if kind == "backcountry" else LABELS
    crust = s.rain_since_snow or s.thaw_since_snow
    if s.depth_in < GOOD_DEPTH_IN[kind]:
        return 2, ("Crust / ice" if crust else "Thin cover")
    if s.new_3d_in >= 6 and not crust:
        return 5, labels[5]
    groomed = s.groomed_hours is not None and s.groomed_hours <= 48
    if (s.new_7d_in >= 1 or groomed) and not crust:
        return 4, labels[4]
    if s.thaw_since_snow and not s.rain_since_snow and month in SPRING_MONTHS:
        return 3, "Spring / corn"
    if crust or s.strong_wind:
        return 2, labels[2]
    return 3, labels[3]


def freshness(age_hours):
    if age_hours is None:
        return 0.5
    if age_hours <= 24:
        return 1.0
    if age_hours <= 48:
        return 0.85
    if age_hours <= 96:
        return 0.6
    return 0.4


def agreement(depths):
    vals = [d for d in depths if d is not None]
    if len(vals) < 2:
        return 0.85
    mean = sum(vals) / len(vals)
    rel = (max(vals) - min(vals)) / max(mean, 6)
    return 1 - min(0.5, rel * 0.5)


def proximity(dist_km, elev_gap_ft):
    if dist_km is None:
        return 0.6
    return 1 - min(0.4, dist_km / 75 + abs(elev_gap_ft) / 6000)


def forecast_spread(pcts):
    """NBM 10th/50th/90th percentile precipitation for the window -> 0..1 factor."""
    if not pcts or 50 not in pcts:
        return 0.7
    p10, p50, p90 = pcts.get(10, 0), pcts[50], pcts.get(90, pcts[50])
    if p90 < 0.1:
        return 0.95
    ratio = (p90 - p10) / max(p50, 0.1)
    return max(0.4, min(1.0, 1 / (1 + 0.25 * ratio)))


def model_agreement(nbm_snow, nws_snow, nbm_level, nws_level):
    """NBM vs. the forecaster-edited NWS forecast: disagreement on snowfall or snow level lowers confidence."""
    if nws_snow is None:
        return 0.95
    big = max(nbm_snow, nws_snow)
    snow = 1 - min(0.3, abs(nbm_snow - nws_snow) / max(4.0, big) * 0.5)
    level = 1.0
    if nbm_level is not None and nws_level is not None:
        level = 1 - min(0.2, abs(nbm_level - nws_level) / 3000 * 0.2)
    return snow * level


def snow_level_risk(steps, elev_ft):
    for st in steps:
        if st.get("apcp_in", 0) >= 0.04 and st.get("snowlvl_ft") is not None:
            if abs(st["snowlvl_ft"] - elev_ft) <= SNOW_LEVEL_RISK_FT:
                return SNOW_LEVEL_RISK_FACTOR
    return 1.0


def pct(x):
    return int(round(max(0.0, min(1.0, x)) * 100))


def threshold_certainty(depth_in, kind, data_conf):
    """How sure a depth-vs-minimum call is: near the minimum it is a coin flip, far from it it is not."""
    minimum = SKIABLE_DEPTH_IN[kind]
    margin = min(1.0, abs(depth_in - minimum) / (0.5 * minimum))
    return (0.55 + 0.4 * margin) * (0.6 + 0.4 * data_conf)


def status_from_condition(score, confidence, basis):
    """Inferred status follows the condition: 1 is closed, 2 is sketchy, 3 and up is open."""
    if not score:
        return Rated("Unknown", pct(SOURCE_WEIGHT["none"]), ["no snow depth"])
    return Rated({1: "Closed", 2: "Sketchy"}.get(score, "Open"), confidence, [basis])


def tier(status: Rated):
    """0 open, 1 sketchy, 2 closed or unknown."""
    return {"Open": 0, "Sketchy": 1}.get(status.value, 2)


def status_now(kind, resort, grooming, depth_in, road_closed, score, cond_conf, grooming_reported=False):
    """Downhill: the resort's own open/closed. Areas with a grooming report: open when groomed in the
    last 7 days. Everything else follows the condition."""
    if kind == "downhill":
        if resort and resort.get("status"):
            return Rated(resort["status"], pct(SOURCE_WEIGHT["official"] * freshness(resort.get("age_hours"))),
                         ["resort report"])
        return Rated("Unknown", pct(SOURCE_WEIGHT["none"]), ["no resort report"])
    if grooming_reported:
        if grooming and grooming.get("age_hours") is not None:
            if grooming["age_hours"] <= 168:
                return Rated("Open", pct(SOURCE_WEIGHT["grooming"] * freshness(grooming["age_hours"] / 3)),
                             ["groomed in the last 7 days"])
            return Rated("Closed", pct(SOURCE_WEIGHT["grooming"]), ["not groomed in 7 days"])
        return Rated("Unknown", pct(SOURCE_WEIGHT["none"]), ["no grooming report"])
    if road_closed:
        return Rated("Closed", pct(SOURCE_WEIGHT["official"] * 0.9), ["road closed"])
    return status_from_condition(score if depth_in is not None else None, cond_conf, "inferred from condition")


def status_weekend(kind, now: Rated, resort, projected_depth, weekend_end, forecast_conf, score, cond_conf,
                   grooming_reported=False):
    if kind == "downhill":
        opening = resort.get("opening_date") if resort else None
        if now.value == "Open":
            return Rated("Open", pct(now.confidence / 100 * WEEKEND_LEAD_FACTOR), ["currently operating"])
        if opening and opening <= weekend_end:
            return Rated("Open", pct(0.75 * forecast_conf), ["announced opening date"])
        if now.value == "Closed":
            return Rated("Closed", pct(now.confidence / 100 * WEEKEND_LEAD_FACTOR), ["no announced opening"])
        return Rated("Unknown", now.confidence, now.basis)
    if grooming_reported:
        if now.value == "Unknown":
            return now
        return Rated(now.value, pct(now.confidence / 100 * WEEKEND_LEAD_FACTOR), now.basis)
    if now.basis == ["road closed"]:
        return Rated("Closed", pct(now.confidence / 100 * 0.7), ["road closed now"])
    return status_from_condition(score if projected_depth is not None else None, cond_conf, "projected condition")

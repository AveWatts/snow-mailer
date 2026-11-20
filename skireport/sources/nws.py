"""NWS gridpoint forecast (forecaster-edited), used as a cross-check on NBM."""
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

from .. import http

URL = "https://api.weather.gov/gridpoints/{}"
_DURATION = re.compile(r"P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?)?")


def _interval(valid_time):
    start, _, dur = valid_time.partition("/")
    d, h, m = (int(x or 0) for x in _DURATION.fullmatch(dur).groups())
    begin = datetime.fromisoformat(start)
    return begin, begin + timedelta(days=d, hours=h, minutes=m)


def _overlap_sum(values, start, end, scale):
    """Accumulated amounts, prorated by how much of each interval falls inside [start, end)."""
    total = 0.0
    for v in values:
        if v["value"] is None:
            continue
        a, b = _interval(v["validTime"])
        inside = (min(b, end) - max(a, start)).total_seconds()
        if inside > 0:
            total += v["value"] * scale * inside / (b - a).total_seconds()
    return total


def _range(values, start, end, scale):
    vals = [v["value"] * scale for v in values if v["value"] is not None
            and _interval(v["validTime"])[0] < end and _interval(v["validTime"])[1] > start]
    return (min(vals), max(vals)) if vals else (None, None)


def grid(grid_id):
    return http.get_json(URL.format(grid_id), headers={"Accept": "application/geo+json"})["properties"]


def fetch(grid_ids, errors, workers=4):
    out = {}

    def one(g):
        try:
            return g, grid(g)
        except Exception:
            return g, None

    with ThreadPoolExecutor(workers) as pool:
        for g, props in pool.map(one, sorted(set(grid_ids))):
            if props is None:
                errors.append(f"NWS grid {g}")
            else:
                out[g] = props
    return out


def summary(props, start, end):
    """Snowfall (in) and snow level range (ft) over [start, end)."""
    snow = props.get("snowfallAmount", {}).get("values", [])
    level = props.get("snowLevel", {}).get("values", [])
    lo, hi = _range(level, start, end, 3.28084)
    return {
        "snow_in": round(_overlap_sum(snow, start, end, 1 / 25.4), 1),
        "snow_level_min_ft": None if lo is None else round(lo),
        "snow_level_max_ft": None if hi is None else round(hi),
        "updated": props.get("updateTime"),
    }

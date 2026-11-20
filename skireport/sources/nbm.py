"""National Blend of Models, subset to the Cascades through the NOMADS grib filter."""
import os
import tempfile
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import eccodes
import numpy as np

from .. import http
from ..config import NBM_BOX

FILTER = "https://nomads.ncep.noaa.gov/cgi-bin/filter_blend.pl"
IDX = "https://nomads.ncep.noaa.gov/pub/data/nccf/com/blend/prod/blend.{d:%Y%m%d}/{d:%H}/{p}/blend.t{d:%H}z.{p}.f{h:03d}.co.grib2.idx"
CORE_VARS = ("ASNOW", "APCP", "SNOWLVL", "TMP", "WIND")
CORE_LEVELS = ("surface", "0_m_above_mean_sea_level", "2_m_above_ground", "10_m_above_ground")
PERCENTILES = (10, 50, 90)


def latest_run(now, max_hour):
    """Newest 00Z/12Z run whose files out to max_hour are published."""
    base = now.replace(minute=0, second=0, microsecond=0)
    for back in range(0, 49):
        run = base - timedelta(hours=back)
        if run.hour not in (0, 12) or now - run < timedelta(hours=2):
            continue
        hour = max_hour + int((now - run).total_seconds() // 3600)
        try:
            http.get(IDX.format(d=run, p="qmd", h=_round6(hour)))
            http.get(IDX.format(d=run, p="core", h=_round6(hour)))
            return run
        except Exception:
            continue
    raise RuntimeError("no complete NBM run found in the last 48 hours")


def _round6(h):
    return int(np.ceil(h / 6.0) * 6)


def hours_to(run, when):
    return _round6((when - run).total_seconds() / 3600)


def _download(run, product, hour, variables, levels):
    params = {"dir": f"/blend.{run:%Y%m%d}/{run:%H}/{product}", "file": f"blend.t{run:%H}z.{product}.f{hour:03d}.co.grib2",
              "subregion": "", **NBM_BOX}
    params.update({f"var_{v}": "on" for v in variables})
    params.update({f"lev_{l}": "on" for l in levels})
    return http.get(FILTER, params=params, timeout=120).content


def _messages(blob):
    fd, path = tempfile.mkstemp(suffix=".grib2")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(blob)
        with open(path, "rb") as f:
            while (h := eccodes.codes_grib_new_from_file(f)) is not None:
                try:
                    yield h
                finally:
                    eccodes.codes_release(h)
    finally:
        os.unlink(path)


def _get(h, key, default=None):
    return eccodes.codes_get(h, key) if eccodes.codes_is_defined(h, key) else default


class Grid:
    def __init__(self, h, points):
        lat = eccodes.codes_get_array(h, "latitudes")
        lon = eccodes.codes_get_array(h, "longitudes")
        lon = np.where(lon > 180, lon - 360, lon)
        self.index = {}
        for pid, (plat, plon) in points.items():
            d = (lat - plat) ** 2 + ((lon - plon) * np.cos(np.radians(plat))) ** 2
            self.index[pid] = int(np.argmin(d))

    def sample(self, h):
        v = eccodes.codes_get_values(h)
        return {pid: float(v[i]) for pid, i in self.index.items()}


def _step(h):
    s = str(_get(h, "stepRange", ""))
    a, _, b = s.partition("-")
    return (int(a), int(b)) if b else (int(a), int(a))


def _classify_core(h):
    level = _get(h, "typeOfLevel")
    pdt = _get(h, "productDefinitionTemplateNumber")
    name = _get(h, "shortName")
    start, end = _step(h)
    if level == "heightAboveSea":
        return "snowlvl_ft", 3.28084
    if name == "2t" and pdt == 0:
        return "t2m_c", None
    if name == "10si" and pdt == 0:
        return "wind_mph", 2.23694
    if pdt == 8 and end - start == 6:
        if name == "tp":
            return "apcp_in", 1 / 25.4
        if level == "surface" and (_get(h, "parameterCategory"), _get(h, "parameterNumber")) == (1, 29):
            return "asnow_in", 39.3701
    return None, None


def fetch(run, end_hour, points, qmd_hours=(), start_hour=6, workers=4):
    """6-hourly core fields for every point from start_hour to end_hour, plus QMD precipitation
    percentiles for every accumulation window ending at each of qmd_hours."""
    grid = {}
    steps = {pid: {} for pid in points}
    pct = {pid: {} for pid in points}

    def core(hour):
        return hour, _download(run, "core", hour, CORE_VARS, CORE_LEVELS)

    def qmd(hour):
        return hour, _download(run, "qmd", hour, ("APCP",), ("surface",))

    hours = list(range(start_hour, end_hour + 1, 6))
    with ThreadPoolExecutor(workers) as pool:
        core_blobs = list(pool.map(core, hours))
        qmd_blobs = list(pool.map(qmd, sorted(set(qmd_hours))))

    for hour, blob in core_blobs:
        for h in _messages(blob):
            if "g" not in grid:
                grid["g"] = Grid(h, points)
            field, scale = _classify_core(h)
            if not field:
                continue
            for pid, v in grid["g"].sample(h).items():
                if field == "t2m_c":
                    v -= 273.15
                elif scale:
                    v *= scale
                steps[pid].setdefault(hour, {})[field] = v

    for hour, blob in qmd_blobs:
        for h in _messages(blob):
            if _get(h, "productDefinitionTemplateNumber") != 10 or _get(h, "percentileValue") not in PERCENTILES:
                continue
            if "g" not in grid:
                grid["g"] = Grid(h, points)
            window = _step(h)
            if window[1] != hour:
                continue
            p = _get(h, "percentileValue")
            for pid, v in grid["g"].sample(h).items():
                pct[pid].setdefault(window, {})[p] = v / 25.4
    return {"run": run, "steps": steps, "percentiles": pct}


def best_window(windows, start, end):
    """The available window ending at `end` whose start is closest to `start`."""
    ending = [w for w in windows if w[1] == end]
    return min(ending, key=lambda w: abs(w[0] - start)) if ending else None


def utcnow():
    return datetime.now(timezone.utc)

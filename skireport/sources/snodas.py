"""NOAA SNODAS daily snow depth grid (the model behind the NOHRSC snow analysis), from the NSIDC archive."""
import gzip
import io
import logging
import tarfile
from datetime import timedelta

import numpy as np

from .. import http

log = logging.getLogger(__name__)
URL = "https://noaadata.apps.nsidc.org/NOAA/G02158/masked/{d:%Y}/{d:%m}_{month}/SNODAS_{d:%Y%m%d}.tar"
MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
DEPTH = "us_ssmv11036tS__T0001TTNATS{d:%Y%m%d}05HP001"


def _header(text):
    return {k.strip(): v.strip() for k, v in (line.split(":", 1) for line in text.splitlines() if ":" in line)}


def _read(blob, day, box):
    with tarfile.open(fileobj=io.BytesIO(blob)) as tar:
        name = DEPTH.format(d=day)
        head = _header(gzip.decompress(tar.extractfile(f"{name}.txt.gz").read()).decode())
        raw = gzip.decompress(tar.extractfile(f"{name}.dat.gz").read())
    cols, rows = int(head["Number of columns"]), int(head["Number of rows"])
    res = float(head["X-axis resolution"])
    west, north = float(head["Minimum x-axis coordinate"]), float(head["Maximum y-axis coordinate"])
    c0, c1 = int((box["leftlon"] - west) / res), int(np.ceil((box["rightlon"] - west) / res))
    r0, r1 = int((north - box["toplat"]) / res), int(np.ceil((north - box["bottomlat"]) / res))
    grid = np.frombuffer(raw, ">i2").reshape(rows, cols)[r0:r1, c0:c1].astype(float)
    grid[grid < 0] = np.nan
    lats = north - (np.arange(r0, r1) + 0.5) * res
    lons = west + (np.arange(c0, c1) + 0.5) * res
    return grid, lats, lons


def day_grid(day, box):
    """(depth in mm with rows north to south, row latitudes, column longitudes) for one day."""
    return _read(http.get(URL.format(d=day, month=MONTHS[day.month - 1]), timeout=180).content, day, box)


def depth(day, box, back=3):
    """(date, depth mm, row latitudes, column longitudes) from the newest daily grid on or before `day`."""
    for d in (day - timedelta(days=i) for i in range(back + 1)):
        try:
            return (d, *day_grid(d, box))
        except Exception as e:
            log.info("SNODAS %s not available: %s", d, e)
    raise RuntimeError(f"no SNODAS grid from the {back + 1} days up to {day}")


def sample(grid, lats, lons, points):
    """{key: inches} at the cell under each (lat, lon); None where the cell has no data."""
    out = {}
    for key, (lat, lon) in points.items():
        v = grid[np.argmin(abs(lats - lat)), np.argmin(abs(lons - lon))]
        out[key] = None if np.isnan(v) else round(float(v) / 25.4, 1)
    return out

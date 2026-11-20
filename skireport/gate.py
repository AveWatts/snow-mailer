"""Season gate: proceed only if some area (permanent snowfields excluded) has more than the threshold."""
import logging
from datetime import date

from . import areas
from .config import GATE_MIN_DEPTH_IN
from .sources import nohrsc, snotel

log = logging.getLogger(__name__)


def has_snow(today=None):
    candidates = [a for a in areas.all_areas(areas.load()) if not a.permanent_snowfield]
    try:
        stations = snotel.stations()
        near = {s.triplet: s for a in candidates for _, s in snotel.nearest(a, stations)}
        series = snotel.observations(list(near.values()), days=3, today=today or date.today())
        for triplet, s in series.items():
            depth = s.get("SNWD", {})
            if depth and depth[max(depth)] > GATE_MIN_DEPTH_IN:
                log.info("gate: %s has %s in", near[triplet].name, depth[max(depth)])
                return True
    except Exception as e:
        log.warning("gate: SNOTEL check failed (%s); falling back to NOHRSC", e)
    for a in candidates:
        try:
            depth = nohrsc.point(a.lat, a.lon)["depth_in"]
        except Exception as e:
            log.warning("gate: NOHRSC %s failed (%s)", a.id, e)
            continue
        if depth is not None and depth > GATE_MIN_DEPTH_IN:
            log.info("gate: NOHRSC %s has %s in", a.name, depth)
            return True
    return False

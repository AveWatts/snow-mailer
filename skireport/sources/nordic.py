"""Grooming times from Nordic Pulse's public venue pages, which embed the venue data as page state."""
import json
import logging
import re
from datetime import datetime

from bs4 import BeautifulSoup

from .. import http

log = logging.getLogger(__name__)
PAGE = "https://www.nordic-pulse.com/ski-areas/US/OR/{}"
VENUES = {
    "meissner": "Meissner-Sno-Park",
    "bachelor-nordic": "Mt-Bachelor-Nordic-Center",
    "elk-lake": "Elk-Lake-Resort",
}
REPORTED = {"meadows-nordic", *VENUES}


def venue(permalink, now):
    url = PAGE.format(permalink)
    state = BeautifulSoup(http.get(url).text, "html.parser").select_one("script#ng-state")
    data = json.loads(state.string)
    for entry in data.values():
        if isinstance(entry, dict) and re.search(r"/v3/ski-areas/[^/?]+\?project=npw$", str(entry.get("u", ""))):
            b = entry["b"]
            groomed = datetime.fromisoformat(b["lastGroomed"].replace("Z", "+00:00")) if b.get("lastGroomed") else None
            return {
                "groomed_at": groomed,
                "age_hours": None if groomed is None else (now - groomed).total_seconds() / 3600,
                "in_progress": bool(b.get("inProgress")),
                "url": url,
            }
    raise ValueError(f"no venue state on {url}")


def meadows_nordic(now):
    """Meadows' own trail feed; the Nordic Center sector only lists trails while the center is operating."""
    url = "https://www.skihood.com/mountain-report"
    data = http.get_json("https://www.skihood.com/api/weather/poi", params={"include": "Nordic Center"})
    trails = [c for s in data.get("data", []) for c in s.get("children", [])]
    groomed = []
    for t in trails:
        stamp = t.get("groomingDate") or t.get("lastGroomed")
        if stamp and str(t.get("groomingStatus", "")).upper() not in ("", "NOT_GROOMED", "UNDEF"):
            groomed.append(datetime.fromisoformat(str(stamp).replace("Z", "+00:00")))
        elif str(t.get("groomingStatus", "")).upper() in ("GROOMED", "GROOMED_TODAY"):
            groomed.append(now)
    if not groomed:
        return None
    last = max(groomed)
    return {"groomed_at": last, "age_hours": (now - last).total_seconds() / 3600, "in_progress": False, "url": url}


def fetch_all(now, errors):
    out = {}
    try:
        if (m := meadows_nordic(now)):
            out["meadows-nordic"] = m
    except Exception as e:
        log.warning("grooming meadows-nordic failed: %s", e)
        errors.append("Meadows Nordic grooming")
    for area_id, permalink in VENUES.items():
        try:
            out[area_id] = venue(permalink, now)
        except Exception as e:
            log.warning("grooming %s failed: %s", area_id, e)
            errors.append(f"Nordic Pulse ({area_id})")
    return out

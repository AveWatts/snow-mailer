"""Road status: ODOT TripCheck map data, WSDOT pass report, NPS Mount Rainier alerts. All keyless."""
import logging
import re
import time

from .. import http
from ..geo import km

log = logging.getLogger(__name__)
TRIPCHECK = "https://www.tripcheck.com/Scripts/map/data/{}.js"
WSDOT_WHITE_PASS = "https://wsdot.com/Travel/Real-time/Service/api/MountainPass/Details/12"
NPS_MORA = "https://www.nps.gov/mora/park-alerts-mora.json"

RW_LOCATIONS = {
    "mt-hood": ("GOVERNMENT CAMP", "TIMBERLINE LODGE", "BENNETT PASS/MT HOOD MEADOWS"),
    "santiam": ("SANTIAM PASS SMT", "SANTIAM JCT"),
    "bend": ("MT BACHELOR",),
    "newberry": ("SOUTH OF BEND",),
    "willamette": ("WILLAMETTE PASS",),
    "diamond": ("E DIAMOND LAKE SMT", "W DIAMOND LAKE SMT"),
}
INCIDENT_RADIUS_KM = 25


def _first_sentence(text):
    text = (text or "").strip()
    m = re.match(r"(.+?)\.(\s|$)", text)
    return m.group(1) if m else text


CHECKPOINT_NAMES = {
    "GOVERNMENT CAMP": "Government Camp", "TIMBERLINE LODGE": "Timberline Lodge",
    "BENNETT PASS/MT HOOD MEADOWS": "Bennett Pass / Meadows", "SANTIAM PASS SMT": "Santiam Pass",
    "SANTIAM JCT": "Santiam Junction", "MT BACHELOR": "Mt Bachelor", "SOUTH OF BEND": "South of Bend", "WILLAMETTE PASS": "Willamette Pass",
    "E DIAMOND LAKE SMT": "Diamond Lake summit (east)", "W DIAMOND LAKE SMT": "Diamond Lake summit (west)",
}


def chain_level(text):
    t = (text or "").lower()
    if "closed" in t:
        return "closed"
    if "chains required" in t:
        return "required"
    if "chain" in t or "traction" in t:
        return "carry"
    return None


def _route(link):
    m = re.match(r"(US|ORE|OR|HWY|I-?)(\d+)", (link or "").upper())
    if not m:
        return link
    prefix = {"ORE": "OR", "HWY": "Hwy", "I": "I-", "I-": "I-"}.get(m.group(1), m.group(1))
    return f"{prefix}{'' if prefix == 'I-' else ' '}{m.group(2)}"


def _road_weather(zones, out):
    feats = http.get_json(TRIPCHECK.format("rw"))["features"]
    by_loc = {f["attributes"].get("locationName"): f["attributes"] for f in feats}
    for zid, locs in RW_LOCATIONS.items():
        for loc in locs:
            a = by_loc.get(loc)
            if not a:
                continue
            chains = _first_sentence(a.get("chainRestrictionDesc"))
            out[zid]["checkpoints"].append({
                "name": CHECKPOINT_NAMES.get(loc, loc.title()), "route": _route(a.get("linkName")),
                "chains": chains, "chain_level": chain_level(chains), "surface": a.get("pavementConditionDesc"),
            })
            out[zid]["has_data"] = True


def _incidents(zones, out):
    """Closure notices near each Oregon zone. Shown as notes only: a nearby closure is not
    necessarily the access road for any one area."""
    feats = http.get_json(TRIPCHECK.format("INCD"))["features"]
    for f in feats:
        a = f["attributes"]
        lat, lon = a.get("startLatitude"), a.get("startLongitude")
        text = " ".join(str(a.get(k) or "") for k in ("eventTypeName", "eventSubTypeName", "comments"))
        if lat is None or not re.search(r"\bclos(ed|ure)\b", text, re.I):
            continue
        for z in zones:
            if z.state != "OR" or not any(km(lat, lon, ar.lat, ar.lon) <= INCIDENT_RADIUS_KM for ar in z.areas):
                continue
            note = (f"{a.get('route')} {(a.get('locationName') or '').title()}: "
                    f"{_first_sentence(a.get('comments')) or a.get('eventSubTypeName')}")
            if note not in out[z.id]["notes"]:
                out[z.id]["notes"].append(note)


def _white_pass(out):
    c = http.get_json(WSDOT_WHITE_PASS)["condition"]
    restr = _first_sentence((c.get("restrictionOne") or {}).get("publicPage"))
    out["rainier"]["checkpoints"].append({
        "name": "White Pass", "route": "US 12", "chains": restr, "chain_level": chain_level(restr),
        "surface": _first_sentence(c.get("roadCondition")),
    })
    out["rainier"]["has_data"] = True


def _paradise(zones, out, closed):
    # The alerts file is served from a long-lived cache unless the request carries a fresh query string.
    for alert in http.get_json(NPS_MORA, params={"dt": int(time.time())}):
        if alert.get("title", "").startswith("Paradise Road Status") and alert.get("is_active"):
            desc = re.sub(r"<[^>]+>", " ", alert.get("description") or "").strip()
            out["rainier"]["notes"].append(f"Paradise road (NPS): {desc}")
            out["rainier"]["has_data"] = True
            if re.search(r"\b(road|gate)\b[^.]{0,40}\b(remains|will remain|is) closed\b(?! for the night)", desc, re.I):
                rainier = next(z for z in zones if z.id == "rainier")
                closed.update(a.id for a in rainier.areas)


def fetch(zones, errors):
    out = {z.id: {"checkpoints": [], "notes": [], "has_data": False} for z in zones}
    closed = set()
    for name, fn, args in (("TripCheck road weather", _road_weather, (zones, out)),
                           ("TripCheck incidents", _incidents, (zones, out)),
                           ("WSDOT White Pass", _white_pass, (out,)),
                           ("NPS Mount Rainier", _paradise, (zones, out, closed))):
        try:
            fn(*args)
        except Exception as e:
            log.warning("%s failed: %s", name, e)
            errors.append(name)
    return {"zones": out, "closed_areas": closed}

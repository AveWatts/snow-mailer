"""Official resort reports. Each adapter returns {area_id: report}; report keys:
status ("Open" | "Closed"), lifts_open, lifts_total, base_in, new_24h_in, new_48h_in, new_7d_in,
age_hours, opening_date, url."""
import logging
import re
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

from .. import http

log = logging.getLogger(__name__)
PACIFIC = ZoneInfo("America/Los_Angeles")
MONTHS = "January|February|March|April|May|June|July|August|September|October|November|December"


def _num(text):
    m = re.search(r"-?\d+(?:\.\d+)?", text or "")
    return float(m.group()) if m else None


def _age(now, when):
    return None if when is None else max(0.0, (now - when).total_seconds() / 3600)


def _soup(url):
    return BeautifulSoup(http.get(url).text, "html.parser")


def _month_day(text, now):
    """'December 4' (no year) -> the next such date on or after the start of this season."""
    m = re.search(rf"({MONTHS})\s+(\d{{1,2}})", text or "")
    if not m:
        return None
    month = datetime.strptime(m.group(1), "%B").month
    d = date(now.year, month, int(m.group(2)))
    return d if d >= now.date() - timedelta(days=120) else date(now.year + 1, month, int(m.group(2)))


def _opening(text, now):
    m = re.search(rf"open[^.]{{0,80}}?\b(?:on|day in|in)\b\W*(?:<[^>]+>\W*)*(({MONTHS})(?:\s+\d{{1,2}})?)", text or "", re.I)
    if not m:
        return None
    if re.search(r"\d", m.group(1)):
        return _month_day(m.group(1), now)
    return None


def bachelor(now):
    base = "https://api.mtbachelor.com/api/v1/dor/drupal"
    snow = http.get_json(f"{base}/snow-reports", params={"sort": "date", "direction": "desc"})[0]
    lifts = [l for l in http.get_json(f"{base}/lifts") if l.get("season") == "winter" and l.get("type") != "carpet"]
    c = snow.get("computed", {})
    n_open = sum(1 for l in lifts if l.get("status") == "open")
    updated = datetime.fromtimestamp(snow["updated"], PACIFIC) if snow.get("updated") else None
    return {"bachelor": {
        "status": "Open" if n_open else "Closed", "lifts_open": n_open, "lifts_total": len(lifts),
        "base_in": snow.get("base_depth"), "new_24h_in": c.get("24_hour"), "new_48h_in": c.get("48_hour"),
        "new_7d_in": c.get("7_day"), "age_hours": _age(now, updated),
        "opening_date": None if n_open else _opening(snow.get("report"), now),
        "url": "https://www.mtbachelor.com/the-mountain/snow-report/",
    }}


def timberline(now):
    soup = _soup("https://timberlinelodge.com/conditions/")
    vals = {}
    for it in soup.select(".conditions__item"):
        label, data = it.select_one(".conditions__item-label"), it.select_one(".conditions__item-data")
        if label and data:
            vals[label.get_text(" ", strip=True)] = _num(data.get_text())
    header = soup.select_one(".conditions__group-header p")
    updated = None
    if header:
        m = re.search(rf"({MONTHS})\s+(\d{{1,2}}),\s*(\d{{1,2}}):(\d{{2}})\s*([ap]m)", header.get_text(), re.I)
        if m:
            d = _month_day(f"{m.group(1)} {m.group(2)}", now)
            if d > now.date():
                d = d.replace(year=d.year - 1)
            hour = int(m.group(3)) % 12 + (12 if m.group(5).lower() == "pm" else 0)
            updated = datetime(d.year, d.month, d.day, hour, int(m.group(4)), tzinfo=PACIFIC)
    lifts = {}
    for tr in soup.select("table tr"):
        tds = tr.select("td")
        dot = tr.select_one("[class*=status__color--]")
        if tds and dot:
            lifts[tds[0].get_text(" ", strip=True)] = "green" in " ".join(dot.get("class", []))
    base = next((v for k, v in vals.items() if k.startswith("Base Depth")), None)
    common = {"base_in": base, "new_24h_in": vals.get("24 Hours"), "new_48h_in": None,
              "new_7d_in": None, "age_hours": _age(now, updated), "opening_date": None,
              "url": "https://timberlinelodge.com/conditions/"}
    tl = {k: v for k, v in lifts.items() if "Summit Pass" not in k and "Lot" not in k and "Snowcat" not in k}
    sp = {k: v for k, v in lifts.items() if "Summit Pass" in k}
    out = {}
    for area, group in (("timberline", tl), ("summit-pass", sp)):
        if group:
            n = sum(group.values())
            out[area] = {"status": "Open" if n else "Closed", "lifts_open": n, "lifts_total": len(group), **common}
    if "summit-pass" in out:
        # Timberline's snow numbers are measured at 6,000 ft; Summit Pass sits near 4,000 ft.
        out["summit-pass"].update(base_in=None, new_24h_in=None)
    return out


def meadows(now):
    data = http.get_json("https://www.skihood.com/api/weather/report",
                         params={"includeResortInfo": "true", "includeSnowInfo": "true"})["data"]
    zones = {z.get("name"): z for z in data.get("snow", {}).get("snowZones", [])}
    base = zones.get("Base Area") or next(iter(zones.values()), {})

    def inch(key):
        v = base.get(key)
        return v.get("countryValue") if isinstance(v, dict) else None

    counters = http.get_json("https://www.skihood.com/api/weather/poi",
                             params={"include": "Lifts", "onlyCounts": "true"}).get("counters", [])
    lift = next((c for c in counters if "lift" in (c.get("name") or "").lower()), None)
    days_open = any(d.get("open") for d in data.get("resort", {}).get("availability", {}).get("openingDays", []))
    n_open = lift.get("open") if lift else None
    total = (lift.get("open", 0) + lift.get("closed", 0)) if lift else None
    is_open = (n_open or 0) > 0 if lift else days_open
    updated = datetime.fromisoformat(base["lastModified"]) if base.get("lastModified") else None
    return {"meadows": {
        "status": "Open" if is_open else "Closed", "lifts_open": n_open, "lifts_total": total,
        "base_in": inch("snowTotalDepth") if is_open else None, "new_24h_in": inch("freshSnowFallDepth24H"),
        "new_48h_in": inch("freshSnowFallDepth48H"), "new_7d_in": inch("freshSnowFallDepth7D"),
        "age_hours": _age(now, updated) if is_open else 12, "opening_date": None,
        "url": "https://www.skihood.com/mountain-report",
    }}


def skibowl(now):
    soup = _soup("https://skibowl.com/winter-condition-and-lift-status/")
    tables = soup.select("table.jet-table")
    rows = lambda t: [[c.get_text(" ", strip=True) for c in tr.select("td")] for tr in t.select("tr")]
    weather = {r[0]: r[1] for r in rows(tables[0]) if len(r) > 1} if tables else {}
    lifts = [r for r in rows(tables[1]) if len(r) > 1 and r[0]] if len(tables) > 1 else []
    lifts = [r for r in lifts if "Chair" in r[0] or "Tow" in r[0] or "Lift" in r[0]]
    n = sum(1 for r in lifts if r[1].lower().startswith("open"))
    try:
        mod = http.get_json("https://skibowl.com/wp-json/wp/v2/pages",
                            params={"slug": "winter-condition-and-lift-status", "_fields": "modified_gmt"})[0]
        updated = datetime.fromisoformat(mod["modified_gmt"] + "+00:00")
    except Exception:
        updated = None
    return {"skibowl": {
        "status": "Open" if n else "Closed", "lifts_open": n, "lifts_total": len(lifts),
        "base_in": _num(weather.get("Snow Depth")), "new_24h_in": _num(weather.get("New Snow (Last 24 Hours)")),
        "new_48h_in": _num(weather.get("New Snow (Last 48 Hours)")), "new_7d_in": None,
        "age_hours": _age(now, updated), "opening_date": None,
        "url": "https://skibowl.com/winter-condition-and-lift-status/",
    }}


def hoodoo(now):
    html = http.get("https://hoodoo.com/the-mountain/mountain-lift-status/").text
    soup = BeautifulSoup(html, "html.parser")
    desc = soup.select_one("#tablepress-3-description")
    text = desc.get_text(" ", strip=True) if desc else ""
    m = re.search(rf"({MONTHS})\s+(\d{{1,2}}),\s*(\d{{4}})", text)
    report_day = datetime.strptime(" ".join(m.groups()), "%B %d %Y").replace(tzinfo=PACIFIC) if m else None
    age = _age(now, report_day + timedelta(hours=7)) if report_day else None
    lifts = [[c.get_text(" ", strip=True) for c in tr.select("td")] for tr in soup.select("#tablepress-10 tr")]
    lifts = [r for r in lifts if len(r) > 1 and "CARPET" not in r[0].upper()]
    season_closed = "Closed until next season" in html
    fresh = age is not None and age <= 48
    n = sum(1 for r in lifts if r[1].upper() != "CLOSED") if fresh and not season_closed else 0
    base = re.search(r"Base[^:]*:\s*(\d+)", text)
    new = re.search(r"New Snow[^:]*:\s*(\d+)", text)
    return {"hoodoo": {
        "status": "Open" if n else "Closed", "lifts_open": n, "lifts_total": len(lifts),
        "base_in": float(base.group(1)) if base and fresh else None,
        "new_24h_in": float(new.group(1)) if new and fresh else None, "new_48h_in": None, "new_7d_in": None,
        "age_hours": age if fresh else (12 if season_closed else age), "opening_date": None,
        "url": "https://hoodoo.com/the-mountain/mountain-lift-status/",
    }}


def willamette(now):
    url = "https://www.willamettepass.ski/weather-conditions-webcams/lifts-trails/"
    soup = _soup(url)
    vals = {}
    for div in soup.select(".m-snow-totals-table > div"):
        label, top = div.select_one(".m-snow-totals-label"), div.select_one(".m-snow-totals-top")
        if label and top:
            vals.setdefault(label.get_text(" ", strip=True), top.get_text(" ", strip=True))
    lifts = re.match(r"\s*(\d+)\s*/\s*(\d+)", vals.get("Lifts Open", ""))
    n, total = (int(lifts.group(1)), int(lifts.group(2))) if lifts else (None, None)
    try:
        w = http.get_json("https://www.willamettepass.ski/wp-content/uploads/sites/13/m-json/weather.json")
        stamp = w.get("conditions_table_updated") or w.get("lifts_trails_page_updated")
        updated = datetime.strptime(stamp, "%B %d, %Y %I:%M %p").replace(tzinfo=PACIFIC) if stamp else None
    except Exception:
        updated = None
    report = " ".join(x.get_text(" ", strip=True) for x in soup.select(".m-todays-report .m-fs-reg"))
    return {"willamette-pass": {
        "status": "Open" if n else "Closed", "lifts_open": n, "lifts_total": total,
        "base_in": _num(vals.get("Base Depth")), "new_24h_in": _num(vals.get("24 Hr")),
        "new_48h_in": _num(vals.get("48 Hr")), "new_7d_in": _num(vals.get("7 Day")),
        "age_hours": _age(now, updated), "opening_date": None if n else _opening(report, now),
        "url": url,
    }}


def cooper_spur(now):
    url = "https://cooperspur.com/conditions-report/"
    soup = _soup(url)
    vals = {}
    for li in soup.select("li.eael-feature-list-item"):
        t, c = li.select_one(".eael-feature-list-title"), li.select_one(".eael-feature-list-content")
        if t and c:
            vals[t.get_text(" ", strip=True)] = c.get_text(" ", strip=True)
    lifts = {k: v for k, v in vals.items() if "Lift" in k or "Tow" in k}
    n = sum(1 for v in lifts.values() if v.lower().startswith("open"))
    return {"cooper-spur": {
        "status": "Open" if n else "Closed", "lifts_open": n, "lifts_total": len(lifts),
        "base_in": _num(vals.get("Snow Depth")), "new_24h_in": _num(vals.get("New Snow")),
        "new_48h_in": None, "new_7d_in": None, "age_hours": None, "opening_date": None, "url": url,
    }}


ADAPTERS = (bachelor, timberline, meadows, skibowl, hoodoo, willamette, cooper_spur)


def fetch_all(now, errors):
    out = {}
    for fn in ADAPTERS:
        try:
            out.update(fn(now))
        except Exception as e:
            log.warning("resort %s failed: %s", fn.__name__, e)
            errors.append(f"{fn.__name__.replace('_', ' ').title()} report")
    return out

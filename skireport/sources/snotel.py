from dataclasses import dataclass
from datetime import date, timedelta

from .. import http
from ..config import SNOTEL_PER_AREA, SNOTEL_RADIUS_KM
from ..geo import km

BASE = "https://wcc.sc.egov.usda.gov/awdbRestApi/services/v1"
ELEMENTS = ("SNWD", "WTEQ", "PREC", "TMAX", "TMIN")


@dataclass
class Station:
    triplet: str
    name: str
    lat: float
    lon: float
    elev_ft: float


@dataclass
class StationObs:
    station: Station
    dist_km: float
    series: dict  # element -> {date: value}

    def latest(self, element):
        s = self.series.get(element, {})
        return s[max(s)] if s else None

    def latest_date(self):
        s = self.series.get("SNWD", {})
        return max(s) if s else None

    def depth_change(self, days):
        s = self.series.get("SNWD", {})
        if not s:
            return None
        end = max(s)
        start = end - timedelta(days=days)
        return s[end] - s[start] if start in s else None

    def daily(self, element, days):
        s = self.series.get(element, {})
        if not s:
            return []
        end = max(s)
        return [(d, s[d]) for d in sorted(s) if d > end - timedelta(days=days)]

    def precip_increments(self, days):
        s = self.series.get("PREC", {})
        out = []
        for d in sorted(s):
            prev = s.get(d - timedelta(days=1))
            if prev is not None and d > max(s) - timedelta(days=days):
                out.append((d, max(0.0, s[d] - prev)))
        return out


def stations():
    data = http.get_json(f"{BASE}/stations", params={
        "stationTriplets": "*:OR:SNTL,*:WA:SNTL", "activeOnly": "true"})
    return [Station(s["stationTriplet"], s["name"], s["latitude"], s["longitude"], s["elevation"]) for s in data]


def nearest(area, all_stations):
    near = sorted(((km(area.lat, area.lon, s.lat, s.lon), s) for s in all_stations), key=lambda t: t[0])
    return [(d, s) for d, s in near if d <= SNOTEL_RADIUS_KM][:SNOTEL_PER_AREA] or near[:1]


def observations(station_list, days=9, today=None):
    today = today or date.today()
    data = http.get_json(f"{BASE}/data", params={
        "stationTriplets": ",".join(s.triplet for s in station_list),
        "elements": ",".join(ELEMENTS),
        "duration": "DAILY",
        "beginDate": (today - timedelta(days=days)).isoformat(),
        "endDate": today.isoformat(),
    })
    out = {}
    for st in data:
        series = {}
        for block in st.get("data", []):
            el = block["stationElement"]["elementCode"]
            series[el] = {date.fromisoformat(v["date"][:10]): v["value"]
                          for v in block.get("values", []) if v.get("value") is not None}
        out[st["stationTriplet"]] = series
    return out

"""Drive times from BASE_LOCATION: OpenStreetMap routing (OSRM), normal road conditions."""
import os
import re

from .. import http

GEOCODE = "https://nominatim.openstreetmap.org/search"
TABLE = "https://router.project-osrm.org/table/v1/driving/{}"
LATLON = re.compile(r"^\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*$")


def base_point():
    """BASE_LOCATION as 'lat,lon' or a street address; None when unset."""
    value = os.environ.get("BASE_LOCATION", "").strip()
    if not value:
        return None
    m = LATLON.match(value)
    if m:
        return float(m.group(1)), float(m.group(2))
    hits = http.get_json(GEOCODE, params={"q": value, "format": "json", "limit": 1, "countrycodes": "us"})
    if not hits:
        raise ValueError("BASE_LOCATION could not be geocoded")
    return float(hits[0]["lat"]), float(hits[0]["lon"])


def drive_seconds(base, destinations):
    """{key: seconds} from base to each (lat, lon) destination, in one routing request."""
    keys = list(destinations)
    coords = ";".join(f"{lon},{lat}" for lat, lon in [base] + [destinations[k] for k in keys])
    data = http.get_json(TABLE.format(coords), params={"sources": "0", "annotations": "duration"})
    if data.get("code") != "Ok":
        raise ValueError(f"routing failed: {data.get('code')}")
    return {k: d for k, d in zip(keys, data["durations"][0][1:]) if d is not None}

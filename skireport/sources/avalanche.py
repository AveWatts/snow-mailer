from .. import http
from ..geo import in_geometry

URL = "https://api.avalanche.org/v2/public/products/map-layer"
CENTER_NAMES = {"COAA": "COAC"}
LEVELS = {1: "Low", 2: "Moderate", 3: "Considerable", 4: "High", 5: "Extreme"}


def forecast_zones():
    return http.get_json(URL)["features"]


def for_point(lat, lon, zones):
    for f in zones:
        if f.get("geometry") and in_geometry(lon, lat, f["geometry"]):
            p = f["properties"]
            level = p.get("danger_level")
            return {
                "center": p.get("center_id"),
                "center_name": CENTER_NAMES.get(p.get("center_id"), p.get("center_id")),
                "zone": p.get("name"),
                "rating": LEVELS.get(level, "No rating"),
                "level": level,
                "link": p.get("link"),
                "off_season": bool(p.get("off_season")),
                "issued": p.get("start_date"),
                "valid_until": p.get("end_date"),
            }
    return None

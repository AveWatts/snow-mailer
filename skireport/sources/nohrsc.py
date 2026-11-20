import time

from .. import http

URL = "https://mapservices.weather.noaa.gov/raster/rest/services/snow/NOHRSC_Snow_Analysis/MapServer/identify"
DEPTH_LAYER, SWE_LAYER = 3, 7


def point(lat, lon, attempts=3):
    """Modeled snow depth and SWE in inches; depth is stored in meters, SWE in millimeters."""
    for _ in range(attempts):
        result = _identify(lat, lon)
        if result["depth_in"] is not None:
            return result
        time.sleep(2)
    raise ValueError(f"NOHRSC returned no depth at {lat},{lon}")


def _identify(lat, lon):
    data = http.get_json(URL, params={
        "geometry": f"{lon},{lat}", "geometryType": "esriGeometryPoint", "sr": 4326,
        "layers": f"all:{DEPTH_LAYER},{SWE_LAYER}", "tolerance": 1,
        "mapExtent": f"{lon - 0.5},{lat - 0.5},{lon + 0.5},{lat + 0.5}", "imageDisplay": "400,400,96",
        "returnGeometry": "false", "f": "json",
    })
    vals = {}
    for r in data.get("results", []):
        raw = r["attributes"].get("Service Pixel Value")
        try:
            vals[r["layerId"]] = float(raw)
        except (TypeError, ValueError):
            continue
    depth = vals.get(DEPTH_LAYER)
    swe = vals.get(SWE_LAYER)
    return {
        "depth_in": None if depth is None else round(depth * 39.37, 1),
        "swe_in": None if swe is None else round(swe / 25.4, 1),
    }

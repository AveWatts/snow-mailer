"""The dashboard's data file: the Thursday model plus a rolling projection, as plain JSON.

Drive times are left out on purpose: the site is public and they would reveal BASE_LOCATION."""
import json
import logging
from datetime import date
from pathlib import Path

from . import depthmap, history, report, scoring
from .config import GOOD_DEPTH_IN, NBM_BOX, SKIABLE_DEPTH_IN
from .sources import snotel

log = logging.getLogger(__name__)
HORIZON_HOURS = 48
DEPTH_IMAGE = "depth-48h.png"


def _rated(r):
    return {"value": r.value, "confidence": r.confidence}


def _iso(d):
    return d.isoformat() if d else None


def _now(r):
    return {
        "status": _rated(r["status"]), "score": r["score"], "condition": _rated(r["condition"]),
        "depth_in": r["depth_in"], "depth_source": r["depth_source"], "fresh_in": r["new_2d_in"],
        "snow_level": r["snow_level_now"], "temp": r["temp_now"],
    }


def _ahead(r):
    a = r["ahead"]
    if not a:
        return None
    return {
        "status": _rated(a["status"]), "score": a["score"], "condition": _rated(a["condition"]),
        "depth_in": a["depth_in"], "depth_change_in": a["depth_change_in"], "fresh_in": a["fresh_in"],
        "rain_in": a["rain_in"], "nws_snow_in": a["nws_snow_in"], "snow_level": a["snow_level"], "temp": a["temp"],
    }


def _best(areas, view):
    out = {}
    for kind in report.KINDS:
        cands = []
        for a in areas:
            v = a[view]
            if a["kind"] != kind or not v or v["depth_in"] is None:
                continue
            tier = scoring.tier(scoring.Rated(**v["status"]))
            if tier < 2:
                cands.append((tier, -report.ski_score(v["depth_in"], v["fresh_in"] or 0), a["id"]))
        out[kind] = [aid for *_, aid in sorted(cands)[:3]]
    return out


def season_start(today):
    return date(today.year if today.month >= 8 else today.year - 1, 10, 1)


def _round(coords):
    return [_round(c) for c in coords] if isinstance(coords[0], list) else [round(c, 4) for c in coords]


def _avalanche_zones(features):
    return [{
        "type": "Feature",
        "geometry": {"type": f["geometry"]["type"], "coordinates": _round(f["geometry"]["coordinates"])},
        "properties": {k: f["properties"].get(k) for k in ("name", "center_id", "danger_level", "color", "link")},
    } for f in features if f.get("geometry") and f["properties"].get("center_id") in report.FORECAST_CENTERS]


def build():
    model = report.build_thursday(horizon_hours=HORIZON_HOURS)
    today = model["generated_local"].date()
    begin = season_start(today)
    triplets = {r["station_triplet"] for r in model["rows"].values() if r["station_triplet"]}
    try:
        series = snotel.season_depth(triplets, begin, today) if triplets else {}
    except Exception as e:
        log.warning("SNOTEL season depth failed: %s", e)
        model["errors"].append("SNOTEL season depth")
        series = {}
    reported = history.reported_depths(begin)
    depth_map, image = None, None
    if model["nbm_sums"]:
        try:
            grid_day, image, bounds = depthmap.build(today, NBM_BOX, model["nbm_sums"])
            depth_map = {"image": DEPTH_IMAGE, "bounds": bounds, "snodas_date": grid_day.isoformat()}
        except Exception as e:
            log.warning("projected depth map failed: %s", e)
            model["errors"].append("+48h snow depth map")
    areas = []
    for z in model["zones"]:
        for r in z["rows"]:
            a = r["area"]
            areas.append({
                "id": a.id, "name": a.name, "kind": a.kind, "zone": z["zone"].id,
                "lat": a.lat, "lon": a.lon, "elev_ft": a.elev_ft,
                "access": vars(r["access"]) if r["access"] else None,
                "resort_url": (r["resort"] or {}).get("url"),
                "grooming_url": (r["grooming"] or {}).get("url"),
                "avalanche": r["avalanche"], "permanent_snowfield": a.permanent_snowfield,
                "station": {"triplet": r["station_triplet"], "name": r["station"], "km": r["station_km"],
                            "elev_ft": r["station_elev_ft"]} if r["station_triplet"] else None,
                "reported": reported.get(a.id, []),
                "now": _now(r), "ahead": _ahead(r),
            })
    zones = [{
        "id": z["zone"].id, "name": z["zone"].name, "state": z["zone"].state,
        "road_link": z["zone"].road_link, "permit": z["permit"],
        "avalanche": z["avalanche"], "unforecast": z["unforecast"],
        "roads": z["roads"], "webcams": z["zone"].webcams,
    } for z in model["zones"]]
    return image, {
        "generated": _iso(model["generated_local"]), "nbm_run": _iso(model["nbm_run"]),
        "horizon_hours": HORIZON_HOURS, "ahead_until": _iso(model["ahead_until"]),
        "skiable_depth": SKIABLE_DEPTH_IN, "good_depth": GOOD_DEPTH_IN,
        "zones": zones, "areas": areas, "season_start": begin.isoformat(),
        "station_depth": {t: series.get(t, []) for t in triplets},
        "avalanche_zones": _avalanche_zones(model["avalanche_zones"]),
        "depth_map_ahead": depth_map,
        "best": {"now": _best(areas, "now"), "ahead": _best(areas, "ahead")},
        "errors": [e for e in model["errors"] if e not in ("base location", "drive times")],
    }


def write(path):
    """The data file at `path`, plus the projected depth image next to it."""
    out = Path(path).parent
    out.mkdir(parents=True, exist_ok=True)
    image, data = build()
    (out / DEPTH_IMAGE).unlink(missing_ok=True)
    if image:
        (out / DEPTH_IMAGE).write_bytes(image)
    Path(path).write_text(json.dumps(data, default=str, separators=(",", ":")))

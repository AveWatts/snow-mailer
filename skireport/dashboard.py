"""The dashboard's data file: the Thursday model plus a rolling projection, as plain JSON.

Drive times are left out on purpose: the site is public and they would reveal BASE_LOCATION."""
import json
import logging
import os
import re
from datetime import date, timedelta
from pathlib import Path

from . import depthmap, http, report, scoring
from .config import GOOD_DEPTH_IN, NBM_BOX, SKIABLE_DEPTH_IN
from .sources import snodas, snotel

log = logging.getLogger(__name__)
HORIZON_HOURS = 48
DEPTH_IMAGE = "depth-48h.png"
SERIES_FILE = "area-depth.json"
LEGACY_SERIES_FILE = "summit-depth.json"
BACKFILL_DAYS = 14


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


YOUTUBE_ID = re.compile(r"(?:youtube\.com/(?:watch\?v=|embed/)|youtu\.be/)([\w-]{11})")


def _with_preview(cam):
    """The cam plus a live-thumbnail URL when its stream is on YouTube (CamStreamer players wrap a YouTube
    stream, so their page is read once per build to find it)."""
    m = YOUTUBE_ID.search(cam["url"])
    if not m and "camstreamer.com/embed/" in cam["url"]:
        try:
            m = YOUTUBE_ID.search(http.get(cam["url"]).text)
        except Exception as e:
            log.info("no CamStreamer preview for %s: %s", cam["url"], e)
    return {**cam, "preview": f"https://i.ytimg.com/vi/{m.group(1)}/hqdefault_live.jpg"} if m else cam


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


def _previous_series(out):
    """The depth series from the last build: a local copy, else the published site's."""
    site = os.environ.get("SITE_URL")
    for name in (SERIES_FILE, LEGACY_SERIES_FILE):
        if (out / name).exists():
            return json.loads((out / name).read_text())
        if site:
            try:
                return http.get_json(f"{site.rstrip('/')}/data/{name}")
            except Exception as e:
                log.info("no published %s: %s", name, e)
    return {}


def depth_series(previous, points, begin, last_day, grid):
    """{area_id: {date: inches or None}} of SNODAS depth since `begin`: the previous series, today's grid, and
    up to BACKFILL_DAYS days from the archive that some area is still missing, newest first."""
    series = {aid: {d: v for d, v in previous.get(aid, {}).items() if d >= begin.isoformat()} for aid in points}

    def add(day, g):
        for aid, v in snodas.sample(*g, points).items():
            series[aid][day.isoformat()] = v

    if grid:
        add(last_day, grid)
    days = [begin + timedelta(days=i) for i in range((last_day - begin).days + 1)]
    missing = [d for d in reversed(days) if any(d.isoformat() not in s for s in series.values())]
    for day in missing[:BACKFILL_DAYS]:
        try:
            add(day, snodas.day_grid(day, NBM_BOX))
        except Exception as e:
            log.info("SNODAS %s skipped: %s", day, e)
    return series


def build(out=Path("site/data")):
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
    grid_day, grid = None, None
    try:
        grid_day, *grid = snodas.depth(today, NBM_BOX)
    except Exception as e:
        log.warning("SNODAS failed: %s", e)
        model["errors"].append("SNODAS snow depth")
    depth_map, image = None, None
    if grid and model["nbm_sums"]:
        try:
            image, bounds = depthmap.build(*grid, model["nbm_sums"])
            depth_map = {"image": DEPTH_IMAGE, "bounds": bounds, "snodas_date": grid_day.isoformat()}
        except Exception as e:
            log.warning("projected depth map failed: %s", e)
            model["errors"].append("+48h snow depth map")
    points = {aid: (r["area"].lat, r["area"].lon) for aid, r in model["rows"].items()}
    area_depth = depth_series(_previous_series(out), points, begin, grid_day or today, grid)
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
                "now": _now(r), "ahead": _ahead(r),
            })
    zones = [{
        "id": z["zone"].id, "name": z["zone"].name, "state": z["zone"].state,
        "road_link": z["zone"].road_link, "permit": z["permit"],
        "avalanche": z["avalanche"], "unforecast": z["unforecast"],
        "roads": z["roads"], "webcams": [_with_preview(c) for c in z["zone"].webcams],
    } for z in model["zones"]]
    return image, {
        "generated": _iso(model["generated_local"]), "nbm_run": _iso(model["nbm_run"]),
        "horizon_hours": HORIZON_HOURS, "ahead_until": _iso(model["ahead_until"]),
        "skiable_depth": SKIABLE_DEPTH_IN, "good_depth": GOOD_DEPTH_IN,
        "zones": zones, "areas": areas, "season_start": begin.isoformat(),
        "station_depth": {t: series.get(t, []) for t in triplets},
        "avalanche_zones": _avalanche_zones(model["avalanche_zones"]),
        "depth_map_ahead": depth_map,
        "area_depth": area_depth,
        "best": {"now": _best(areas, "now"), "ahead": _best(areas, "ahead")},
        "errors": [e for e in model["errors"] if e not in ("base location", "drive times")],
    }


def write(path):
    """The data file at `path`, plus the projected depth image and the depth series next to it."""
    out = Path(path).parent
    out.mkdir(parents=True, exist_ok=True)
    image, data = build(out)
    (out / DEPTH_IMAGE).unlink(missing_ok=True)
    if image:
        (out / DEPTH_IMAGE).write_bytes(image)
    (out / SERIES_FILE).write_text(json.dumps(data["area_depth"], separators=(",", ":")))
    (out / LEGACY_SERIES_FILE).unlink(missing_ok=True)
    Path(path).write_text(json.dumps(data, default=str, separators=(",", ":")))

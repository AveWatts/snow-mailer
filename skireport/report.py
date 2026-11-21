"""Collect every source, score every area, and assemble the data the templates render."""
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from . import analysis, areas, history, scoring
from .config import GOOD_DEPTH_IN, PERMITS, SKIABLE_DEPTH_IN, STORM_RAIN_ON_SNOW_IN, STORM_SNOW_IN
from .sources import avalanche, drive, nbm, nohrsc, nordic, nws, resorts, roads, snotel

log = logging.getLogger(__name__)
PACIFIC = ZoneInfo("America/Los_Angeles")
FORECAST_CENTERS = {"NWAC", "COAA"}
GLACIER_CAP_IN = 300
BEST_DEPTH_CAP_IN = 120
BEST_FRESH_CAP_IN = 24
KINDS = ("downhill", "nordic", "backcountry")


class Sources:
    """Each fetch is isolated: a failure is recorded and the affected fields print as Unknown."""

    def __init__(self):
        self.errors = []

    def run(self, name, fn, *args, default=None):
        try:
            return fn(*args)
        except Exception as e:
            log.warning("%s failed: %s", name, e)
            self.errors.append(name)
            return default


def next_weekend(now_local):
    days = (5 - now_local.weekday()) % 7
    sat = datetime.combine((now_local + timedelta(days=days)).date(), time(0), PACIFIC)
    return sat, sat + timedelta(days=2)


def snowpack(all_areas, src, now):
    stations = src.run("SNOTEL stations", snotel.stations, default=[])
    near = {a.id: snotel.nearest(a, stations) for a in all_areas} if stations else {}
    unique = {s.triplet: s for pairs in near.values() for _, s in pairs}
    series = src.run("SNOTEL data", snotel.observations, list(unique.values()), 9, now.date(), default={}) \
        if unique else {}
    station_obs = {}
    for a in all_areas:
        station_obs[a.id] = [snotel.StationObs(s, d, series.get(s.triplet, {}))
                             for d, s in near.get(a.id, []) if series.get(s.triplet, {}).get("SNWD")]
    with ThreadPoolExecutor(8) as pool:
        model = dict(zip([a.id for a in all_areas],
                         pool.map(lambda a: src.run(f"NOHRSC {a.id}", nohrsc.point, a.lat, a.lon, default={}),
                                  all_areas)))
    return station_obs, model


def ski_score(depth_in, fresh_in):
    """Best-bets ranking: coverage and fresh snow, weighted equally. Depth stops counting at
    BEST_DEPTH_CAP_IN (full coverage; glacier readings would otherwise always win), fresh snow at
    BEST_FRESH_CAP_IN."""
    return (min(depth_in, BEST_DEPTH_CAP_IN) / BEST_DEPTH_CAP_IN
            + min(fresh_in, BEST_FRESH_CAP_IN) / BEST_FRESH_CAP_IN)


def _links(rows, key):
    seen, out = set(), []
    for r in rows:
        url = (r[key] or {}).get("url")
        if url and url not in seen:
            seen.add(url)
            out.append((r["area"].name, url))
    return out


def _webcam_groups(cams):
    groups = {}
    for c in cams:
        groups.setdefault(c.get("group", "Other"), []).append(c)
    return list(groups.items())


def _mid(rng):
    lo, hi = rng
    return None if lo is None or hi is None else (lo + hi) / 2


def condition_confidence(kind, score, depth, base):
    if not score:
        return 20
    if score == 1:
        base = max(base, scoring.threshold_certainty(depth, kind, base))
    return scoring.pct(base)


def area_now(a, stations, model, resort, groom, road_closed, now):
    nearest = stations[0] if stations else None
    hist = analysis.observed_history(nearest) if nearest else None
    station_depth = nearest.latest("SNWD") if nearest else None
    model_depth = (model or {}).get("depth_in")
    if model_depth is not None:
        # NOHRSC counts glacier ice as snowpack (Adams reads over 1,600 in).
        model_depth = min(model_depth, GLACIER_CAP_IN)
    resort_depth = resort.get("base_in") if resort else None
    comparable_station = station_depth if nearest and abs(nearest.station.elev_ft - a.elev_ft) <= 1500 else None

    if resort_depth is not None:
        depth, source = resort_depth, "official"
    elif model_depth is not None:
        depth, source = model_depth, "model"
    elif comparable_station is not None:
        depth, source = comparable_station, "station"
    else:
        depth, source = None, "none"

    station_age = None
    if hist:
        station_age = (now.date() - hist["last_date"]).days * 24 + 12
    new_3d = hist["new_3d_in"] if hist else 0.0
    new_7d = hist["new_7d_in"] if hist else 0.0
    if resort:
        new_3d = max(new_3d, resort.get("new_48h_in") or 0)
        new_7d = max(new_7d, resort.get("new_7d_in") or new_3d)

    groomed_hours = groom.get("age_hours") if groom else None
    state = scoring.SnowState(
        depth_in=depth, new_3d_in=new_3d, new_7d_in=new_7d,
        rain_since_snow=bool(hist and hist["rain_since_snow"]),
        thaw_since_snow=bool(hist and hist["thaw_since_snow"]),
        groomed_hours=groomed_hours,
    )
    depth_conf = (scoring.agreement([resort_depth, model_depth, comparable_station])
                  * scoring.proximity(nearest.dist_km if nearest else None,
                                      (nearest.station.elev_ft - a.elev_ft) if nearest else 0)
                  * scoring.freshness(station_age if source != "official" else resort.get("age_hours")))
    score, label = scoring.condition(a.kind, state, now.month)
    cond = scoring.Rated(label, condition_confidence(a.kind, score, depth, scoring.SOURCE_WEIGHT[source] * depth_conf))
    status = scoring.status_now(a.kind, resort, groom, depth, road_closed, depth_conf)
    return state, score, cond, status, depth_conf, {
        "depth_in": depth, "depth_source": source, "station_depth_in": station_depth,
        "model_depth_in": model_depth, "resort_depth_in": resort_depth,
        "station": nearest.station.name if nearest else None,
        "station_km": round(nearest.dist_km, 1) if nearest else None,
        "new_3d_in": round(new_3d, 1), "new_7d_in": round(new_7d, 1),
    }


def build_thursday(now=None):
    now = now or datetime.now(timezone.utc)
    now_local = now.astimezone(PACIFIC)
    sat, mon = next_weekend(now_local)
    src = Sources()
    zones = areas.load()
    all_areas = areas.all_areas(zones)

    station_obs, model = snowpack(all_areas, src, now)
    avy_zones = src.run("avalanche.org", avalanche.forecast_zones, default=[])
    resort_data = resorts.fetch_all(now, src.errors)
    groom_data = nordic.fetch_all(now, src.errors)
    road_data = roads.fetch(zones, src.errors)
    by_id = {a.id: a for a in all_areas}
    base = src.run("base location", drive.base_point)
    drive_s = {}
    if base:
        access = {a.id: (by_id[a.access_from] if a.access_from else a) for a in all_areas}
        drive_s = src.run("drive times", drive.drive_seconds, base,
                          {aid: (x.lat, x.lon) for aid, x in access.items()}, default={})

    run = src.run("NBM run", nbm.latest_run, now, nbm.hours_to(now, mon.astimezone(timezone.utc)))
    forecast, h_now, h_sat, h_mon = None, 0, 0, 0
    if run:
        h_now = max(0, nbm.hours_to(run, now) - 6)
        h_sat = nbm.hours_to(run, sat.astimezone(timezone.utc))
        h_mon = nbm.hours_to(run, mon.astimezone(timezone.utc))
        points = {a.id: (a.lat, a.lon) for a in all_areas}
        forecast = src.run("NBM forecast", nbm.fetch, run, h_mon, points, (h_sat, h_mon))
    nws_grids = nws.fetch([a.nws_grid for a in all_areas if a.nws_grid], src.errors)
    fc_start = run + timedelta(hours=h_now) if run else now
    sat_utc, mon_utc = sat.astimezone(timezone.utc), mon.astimezone(timezone.utc)
    day = datetime.combine(now_local.date(), time(0), PACIFIC)
    today = (day.astimezone(timezone.utc), (day + timedelta(days=1)).astimezone(timezone.utc))
    weekend_lows = ((sat - timedelta(hours=12)).astimezone(timezone.utc),
                    (mon - timedelta(days=1)).astimezone(timezone.utc))

    previous = history.previous("thursday", now)
    rows = {}
    for a in all_areas:
        resort = resort_data.get(a.id)
        groom = groom_data.get(a.id)
        road_closed = a.id in road_data["closed_areas"]
        state, score, cond, status, depth_conf, facts = area_now(
            a, station_obs.get(a.id, []), model.get(a.id), resort, groom, road_closed, now)

        wk_cond = wk_status = scoring.Rated("Unknown", 0)
        wk_score = None
        wk_facts = dict.fromkeys(("snow_pre_in", "snow_weekend_in", "snow_by_sun_in", "depth_change_by_sun_in",
                                  "rain_weekend_in",
                                  "projected_depth_in", "snow_level_min_ft", "snow_level_max_ft",
                                  "precip_p10_in", "precip_p50_in", "precip_p90_in"))
        wk_facts.update(snow_level_now=(None, None), snow_level_sat=(None, None), snow_level_sun=(None, None),
                        nws_snow_by_sun_in=None, model_agreement=None)
        nws_props = nws_grids.get(a.nws_grid)
        nws_total = nws.summary(nws_props, fc_start, mon_utc) if nws_props else None
        nws_weekend = nws.summary(nws_props, sat_utc, mon_utc) if nws_props else None
        temp_now = nws.temps(nws_props, a.elev_ft, today, today) if nws_props else (None, None)
        temp_weekend = nws.temps(nws_props, a.elev_ft, (sat_utc, mon_utc), weekend_lows) \
            if nws_props else (None, None)
        if forecast:
            steps = forecast["steps"].get(a.id, {})
            wk_facts.update(
                snow_level_now=analysis.snow_level_range(steps, h_now, h_now + 6),
                snow_level_sat=analysis.snow_level_range(steps, h_sat, h_sat + 24),
                snow_level_sun=analysis.snow_level_range(steps, h_sat + 24, h_mon),
            )
        if forecast and state.depth_in is not None:
            steps = forecast["steps"].get(a.id, {})
            pre = analysis.forecast_summary(steps, a.elev_ft, h_now, h_sat)
            wk = analysis.forecast_summary(steps, a.elev_ft, h_sat, h_mon)
            wk_state, proj_depth = analysis.weekend_state(state, pre, wk)
            windows = forecast["percentiles"].get(a.id, {})
            wk_window = nbm.best_window(windows, h_sat, h_mon)
            pcts = windows.get(wk_window) if wk_window else None
            agree = scoring.model_agreement(
                pre["snow_in"] + wk["snow_in"], nws_total["snow_in"] if nws_total else None,
                _mid(analysis.snow_level_range(steps, h_sat, h_mon)),
                _mid((nws_weekend["snow_level_min_ft"], nws_weekend["snow_level_max_ft"])) if nws_weekend else None)
            fc_conf = (scoring.forecast_spread(pcts)
                       * scoring.snow_level_risk(pre["steps"] + wk["steps"], a.elev_ft)
                       * agree)
            wk_score, wk_label = scoring.condition(a.kind, wk_state, sat.month)
            # Square root: the weekend call leans on the forecast more than on today's snowpack data.
            base = (cond.confidence / 100 if score else 0.2) ** 0.5 * fc_conf * scoring.WEEKEND_LEAD_FACTOR
            wk_cond = scoring.Rated(wk_label, condition_confidence(a.kind, wk_score, proj_depth, base))
            wk_status = scoring.status_weekend(a.kind, status, resort, proj_depth, mon.date(), fc_conf)
            wk_facts |= {
                "snow_pre_in": pre["snow_in"], "snow_weekend_in": wk["snow_in"],
                "snow_by_sun_in": round(pre["snow_in"] + wk["snow_in"], 1),
                "depth_change_by_sun_in": round(proj_depth - state.depth_in, 1),
                "nws_snow_by_sun_in": nws_total["snow_in"] if nws_total else None,
                "model_agreement": round(agree, 2),
                "rain_weekend_in": wk["rain_in"], "projected_depth_in": proj_depth,
                "snow_level_min_ft": wk["snow_level_min_ft"], "snow_level_max_ft": wk["snow_level_max_ft"],
                "precip_p10_in": round(pcts.get(10, 0), 2) if pcts else None,
                "precip_p50_in": round(pcts.get(50, 0), 2) if pcts else None,
                "precip_p90_in": round(pcts.get(90, 0), 2) if pcts else None,
            }

        prev = (previous or {}).get("areas", {}).get(a.id, {})
        change = None
        if facts["depth_in"] is not None and prev.get("depth_in") is not None:
            change = round(facts["depth_in"] - prev["depth_in"], 1)
        avy = avalanche.for_point(a.lat, a.lon, avy_zones) if avy_zones else None

        sat_lo, sat_hi = wk_facts["snow_level_sat"]
        sun_lo, sun_hi = wk_facts["snow_level_sun"]
        lows, highs = [v for v in (sat_lo, sun_lo) if v is not None], [v for v in (sat_hi, sun_hi) if v is not None]
        wk_facts["snow_level_weekend"] = (min(lows) if lows else None, max(highs) if highs else None)

        rows[a.id] = {
            "area": a, "score": score, "condition": cond, "status": status,
            "weekend_score": wk_score, "weekend_condition": wk_cond, "weekend_status": wk_status,
            "depth_change_in": change, "avalanche": avy, "resort": resort, "grooming": groom,
            "drive_s": drive_s.get(a.id), "drive_via": by_id[a.access_from].name if a.access_from else None,
            "temp_now": temp_now, "temp_weekend": temp_weekend,
            **facts, **wk_facts,
        }

    zone_views = []
    for z in zones:
        zrows = [rows[a.id] for a in z.areas]
        avy = {}
        for r in zrows:
            v = r["avalanche"]
            if v and v["center"] in FORECAST_CENTERS:
                avy.setdefault(v["zone"], v)
        zone_views.append({
            "zone": z, "rows": zrows, "avalanche": list(avy.values()),
            "unforecast": [r["area"].name for r in zrows if r["area"].kind == "backcountry"
                           and not (r["avalanche"] and r["avalanche"]["center"] in FORECAST_CENTERS)],
            "roads": road_data["zones"][z.id],
            "permit": z.permit or PERMITS[z.state],
            "resort_links": _links(zrows, "resort"),
            "grooming_links": _links(zrows, "grooming"),
            "webcam_groups": _webcam_groups(z.webcams),
        })

    best = {}
    for kind in KINDS:
        cands = [r for r in rows.values() if r["area"].kind == kind and r["projected_depth_in"] is not None
                 and r["weekend_status"].value in ("Open", "Limited")]
        for r in cands:
            r["fresh_in"] = round(r["new_3d_in"] + (r["snow_by_sun_in"] or 0), 1)
            r["ski_score"] = ski_score(r["projected_depth_in"], r["fresh_in"])
        cands.sort(key=lambda r: r["ski_score"], reverse=True)
        best[kind] = cands[:3]

    openings = sorted((r["resort"]["opening_date"], r["area"].name) for r in rows.values()
                      if r["resort"] and r["resort"].get("opening_date") and r["status"].value == "Closed")

    return {
        "kind": "thursday", "openings": openings, "has_drive": bool(drive_s), "generated": now, "generated_local": now_local,
        "weekend_start": sat, "weekend_end": mon - timedelta(days=1),
        "nbm_run": run, "zones": zone_views, "rows": rows, "best": best,
        "errors": src.errors, "skiable_depth": SKIABLE_DEPTH_IN, "good_depth": GOOD_DEPTH_IN,
    }


def build_storm(now=None):
    """Monday check: does anything big arrive before the weekend is over?"""
    now = now or datetime.now(timezone.utc)
    now_local = now.astimezone(PACIFIC)
    _, mon = next_weekend(now_local)
    src = Sources()
    zones = areas.load()
    all_areas = areas.all_areas(zones)
    station_obs, model = snowpack(all_areas, src, now)

    run = src.run("NBM run", nbm.latest_run, now, nbm.hours_to(now, mon.astimezone(timezone.utc)))
    alerts, observed = [], {}
    forecast = None
    if run:
        h_now = max(0, nbm.hours_to(run, now) - 6)
        h_end = nbm.hours_to(run, mon.astimezone(timezone.utc))
        forecast = src.run("NBM forecast", nbm.fetch, run, h_end, {a.id: (a.lat, a.lon) for a in all_areas})
    for a in all_areas:
        state, score, cond, status, _, facts = area_now(a, station_obs.get(a.id, []), model.get(a.id),
                                                       None, None, False, now)
        observed[a.id] = {"score": score, "label": cond.value, "status": status.value, "depth_in": facts["depth_in"]}
        if not forecast or a.permanent_snowfield:
            continue
        f = analysis.forecast_summary(forecast["steps"].get(a.id, {}), a.elev_ft, h_now, h_end)
        rain_on_snow = f["rain_in"] if (facts["depth_in"] or 0) > 0 else 0
        if f["snow_in"] >= STORM_SNOW_IN or rain_on_snow >= STORM_RAIN_ON_SNOW_IN:
            alerts.append({"area": a, "snow_in": f["snow_in"], "rain_in": round(rain_on_snow, 2),
                           "snow_level_min_ft": f["snow_level_min_ft"], "snow_level_max_ft": f["snow_level_max_ft"]})

    by_zone = []
    for z in zones:
        za = [x for x in alerts if x["area"].zone is z]
        if za:
            by_zone.append({"zone": z, "alerts": za})
    return {
        "kind": "storm", "generated": now, "generated_local": now_local,
        "through": mon - timedelta(days=1), "nbm_run": run, "zones": by_zone,
        "observed": observed, "errors": src.errors,
        "snow_threshold": STORM_SNOW_IN, "rain_threshold": STORM_RAIN_ON_SNOW_IN,
    }

"""Turn raw station and forecast data into the SnowState inputs the scoring rules use."""
from datetime import timedelta

from .scoring import SnowState

RAIN_MIN_IN = 0.2
WARM_F = 34
FREEZE_F = 30
SNOW_DAY_MIN_IN = 1
STRONG_WIND_MPH = 30


def observed_history(obs):
    """From one SNOTEL station's daily series: new snow and crust events since the last snowfall."""
    depth = obs.series.get("SNWD", {})
    if not depth:
        return None
    days = sorted(depth)
    end = days[-1]
    tmax, tmin = obs.series.get("TMAX", {}), obs.series.get("TMIN", {})
    prec = dict(obs.precip_increments(10))

    new = {}
    last_snow = None
    for d in days[1:]:
        gain = depth[d] - depth.get(d - timedelta(days=1), depth[d])
        if gain >= SNOW_DAY_MIN_IN:
            new[d] = gain
            last_snow = d

    rain = thaw = False
    for d in days:
        if last_snow and d <= last_snow:
            continue
        warm = tmax.get(d) is not None and tmax[d] >= WARM_F
        if warm and prec.get(d, 0) >= RAIN_MIN_IN:
            rain = True
        if warm and tmin.get(d) is not None and tmin[d] <= FREEZE_F:
            thaw = True

    return {
        "new_3d_in": sum(v for d, v in new.items() if d > end - timedelta(days=3)),
        "new_7d_in": sum(v for d, v in new.items() if d > end - timedelta(days=7)),
        "rain_since_snow": rain,
        "thaw_since_snow": thaw,
        "last_date": end,
    }


def forecast_summary(steps, elev_ft, start_hour, end_hour):
    """Sum NBM 6-hour steps in (start_hour, end_hour]: snowfall, rain at the area's elevation,
    freeze-thaw and wind."""
    sel = [steps[h] for h in sorted(steps) if start_hour < h <= end_hour]
    snow = sum(s.get("asnow_in", 0) for s in sel)
    rain = sum(s.get("apcp_in", 0) for s in sel
               if s.get("snowlvl_ft") is not None and s["snowlvl_ft"] > elev_ft)
    temps = [s["t2m_c"] for s in sel if s.get("t2m_c") is not None]
    winds = [s["wind_mph"] for s in sel if s.get("wind_mph") is not None]
    levels = [s["snowlvl_ft"] for s in sel if s.get("snowlvl_ft") is not None and s.get("apcp_in", 0) >= 0.04]
    return {
        "snow_in": round(snow, 1),
        "rain_in": round(rain, 2),
        "thaw": bool(temps) and max(temps) > 1 and min(temps) < -1,
        "strong_wind": bool(winds) and max(winds) >= STRONG_WIND_MPH,
        "snow_level_min_ft": round(min(levels)) if levels else None,
        "snow_level_max_ft": round(max(levels)) if levels else None,
        "steps": sel,
    }


def snow_level_range(steps, start_hour, end_hour):
    """Lowest and highest NBM snow level in (start_hour, end_hour], whether or not precipitation falls."""
    levels = [steps[h]["snowlvl_ft"] for h in sorted(steps)
              if start_hour < h <= end_hour and steps[h].get("snowlvl_ft") is not None]
    return (round(min(levels)), round(max(levels))) if levels else (None, None)


def weekend_state(current: SnowState, pre, weekend):
    """Project the snowpack through Sunday: settle new snow by half, take 3 in of depth per inch of rain."""
    if current.depth_in is None:
        return None, None
    snow = pre["snow_in"] + weekend["snow_in"]
    rain = pre["rain_in"] + weekend["rain_in"]
    depth = max(0.0, current.depth_in + 0.5 * snow - 3 * rain)
    fresh = weekend["snow_in"] + pre["snow_in"]
    rain_after_snow = weekend["rain_in"] >= RAIN_MIN_IN or (pre["rain_in"] >= RAIN_MIN_IN and weekend["snow_in"] < 2)
    crusted = current.rain_since_snow or current.thaw_since_snow
    state = SnowState(
        depth_in=round(depth, 1),
        new_3d_in=fresh,
        new_7d_in=fresh + current.new_3d_in,
        rain_since_snow=rain_after_snow or (crusted and fresh < 2 and current.rain_since_snow),
        thaw_since_snow=weekend["thaw"] or (crusted and fresh < 2 and current.thaw_since_snow),
        strong_wind=weekend["strong_wind"],
        groomed_hours=None,
    )
    return state, round(depth, 1)

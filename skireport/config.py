USER_AGENT = "cascades-ski-report (weekly personal snow report)"
TIMEOUT = 45

GATE_MIN_DEPTH_IN = 12

# Below SKIABLE: not skiable (1/5, closed). Between SKIABLE and GOOD: thin cover, condition capped at 2/5.
SKIABLE_DEPTH_IN = {"downhill": 18, "nordic": 12, "backcountry": 12}
GOOD_DEPTH_IN = {"downhill": 36, "nordic": 24, "backcountry": 30}

STORM_SNOW_IN = 12
STORM_RAIN_ON_SNOW_IN = 1.0

NBM_BOX = {"toplat": 47.0, "bottomlat": 42.7, "leftlon": -123.8, "rightlon": -121.2}

SNOTEL_RADIUS_KM = 30
SNOTEL_PER_AREA = 3

# Confidence weights; refit from history/ with `python -m skireport calibrate`.
SOURCE_WEIGHT = {"official": 0.95, "grooming": 0.85, "station": 0.8, "model": 0.7, "inferred": 0.6, "none": 0.2}
SNOW_LEVEL_RISK_FT = 1000
SNOW_LEVEL_RISK_FACTOR = 0.6
WEEKEND_LEAD_FACTOR = 0.85

PERMITS = {
    "OR": "Oregon Sno-Park permit required Nov 1 - Apr 30.",
    "WA": "Washington Sno-Park permit required (Special Groomed Trails permit at groomed sno-parks).",
}

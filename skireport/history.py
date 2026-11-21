"""Weekly JSON archive in history/: week-over-week changes and confidence calibration."""
import json
from datetime import date, timedelta
from pathlib import Path

DIR = Path(__file__).resolve().parent.parent / "history"


def _path(kind, when):
    return DIR / f"{when:%Y-%m-%d}-{kind}.json"


def previous(kind, now, max_days=14):
    for back in range(1, max_days + 1):
        p = _path(kind, now - timedelta(days=back))
        if p.exists():
            return json.loads(p.read_text())
    return None


def reported_depths(since):
    """{area_id: [(date, depth_in), ...]} from every weekly report on or after `since`."""
    out = {}
    for p in sorted(DIR.glob("*-thursday.json")):
        day = date.fromisoformat(p.name[:10])
        if day < since:
            continue
        for aid, rec in json.loads(p.read_text())["areas"].items():
            if rec.get("depth_in") is not None:
                out.setdefault(aid, []).append((day.isoformat(), rec["depth_in"]))
    return out


def save_thursday(model):
    DIR.mkdir(exist_ok=True)
    rec = {
        "generated": model["generated"].isoformat(),
        "weekend_start": model["weekend_start"].date().isoformat(),
        "nbm_run": model["nbm_run"].isoformat() if model["nbm_run"] else None,
        "errors": model["errors"],
        "areas": {
            aid: {
                "depth_in": r["depth_in"], "depth_source": r["depth_source"],
                "status": r["status"].value, "status_conf": r["status"].confidence,
                "score": r["score"], "condition": r["condition"].value, "condition_conf": r["condition"].confidence,
                "weekend_status": r["weekend_status"].value, "weekend_status_conf": r["weekend_status"].confidence,
                "weekend_score": r["weekend_score"], "weekend_condition": r["weekend_condition"].value,
                "weekend_condition_conf": r["weekend_condition"].confidence,
                "projected_depth_in": r.get("projected_depth_in"),
            } for aid, r in model["rows"].items()
        },
    }
    path = _path("thursday", model["generated_local"])
    path.write_text(json.dumps(rec, indent=1) + "\n")
    return path


def save_observed(model):
    DIR.mkdir(exist_ok=True)
    path = _path("observed", model["generated_local"])
    path.write_text(json.dumps({"generated": model["generated"].isoformat(),
                                "areas": model["observed"]}, indent=1) + "\n")
    return path


def calibration():
    """Pair each Thursday projection with the following Monday's observation; bucket by stated confidence."""
    buckets = {}
    for t in sorted(DIR.glob("*-thursday.json")):
        thu = json.loads(t.read_text())
        mon = date.fromisoformat(t.name[:10]) + timedelta(days=4)
        o = DIR / f"{mon:%Y-%m-%d}-observed.json"
        if not o.exists():
            continue
        obs = json.loads(o.read_text())["areas"]
        for aid, p in thu["areas"].items():
            seen = obs.get(aid)
            if not seen or p["weekend_score"] is None or seen.get("score") is None:
                continue
            for metric, conf, hit in (
                ("condition", p["weekend_condition_conf"], p["weekend_score"] == seen["score"]),
                ("status", p["weekend_status_conf"], p["weekend_status"] == seen["status"]),
            ):
                b = buckets.setdefault((metric, min(90, conf // 10 * 10)), [0, 0])
                b[0] += hit
                b[1] += 1
    return {k: (v[0] / v[1], v[1]) for k, v in sorted(buckets.items())}

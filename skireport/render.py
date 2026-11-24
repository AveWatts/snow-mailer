from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined

ENV = Environment(loader=FileSystemLoader(Path(__file__).with_name("templates")),
                  autoescape=True, trim_blocks=True, lstrip_blocks=True, undefined=StrictUndefined)


def inches(v):
    if v is None:
        return "-"
    return "300+ in" if v >= 300 else f"{v:.0f} in"


def signed(v):
    return "-" if v is None else f"{v:+.0f} in"


def feet(v):
    return "-" if v is None else f"{round(v, -2):,.0f} ft"


def snow_level(lo, hi):
    if lo is None:
        return "-"
    return feet(lo) if hi is None or abs(hi - lo) < 300 else f"{feet(lo)} - {feet(hi)}"


def level(rng, elev_ft):
    """Snow level range in feet; '^' marks a level above the area, where precipitation would fall as rain."""
    lo, hi = rng
    if lo is None:
        return "-"
    short = lambda v: f"{round(v, -2):,.0f}"
    text = short(lo) if hi is None or abs(hi - lo) < 300 else f"{short(lo)}-{short(hi)}"
    return text + ("^" if hi > elev_ft else "")


def temps(pair):
    hi, lo = pair
    if hi is None and lo is None:
        return "-"
    show = lambda v: "-" if v is None else f"{v}°"
    return f"{show(hi)} / {show(lo)}F"


def tabular(area):
    return f"https://forecast.weather.gov/MapClick.php?lat={area.lat}&lon={area.lon}&FcstType=digital"


def and_join(items):
    items = list(items)
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def duration(seconds):
    if seconds is None:
        return None
    minutes = int(round(seconds / 300.0)) * 5
    return f"{minutes // 60}h {minutes % 60:02d}m" if minutes >= 60 else f"{minutes}m"


ENV.filters.update(inches=inches, signed=signed, feet=feet, duration=duration, and_join=and_join)
ENV.globals.update(snow_level=snow_level, level=level, temps=temps, tabular=tabular)


def render(name, model):
    return ENV.get_template(f"{name}.html").render(**model), ENV.get_template(f"{name}.txt").render(**model)

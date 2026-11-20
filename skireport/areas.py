from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class Area:
    id: str
    name: str
    kind: str
    lat: float
    lon: float
    elev_ft: int
    zone: "Zone" = field(repr=False, default=None)
    permanent_snowfield: bool = False
    nws_grid: str | None = None


@dataclass
class Zone:
    id: str
    name: str
    state: str
    road_link: str
    areas: list
    webcams: list
    permit: str | None = None


def load(path=Path(__file__).with_name("areas.yaml")):
    data = yaml.safe_load(Path(path).read_text())
    zones = []
    for z in data["zones"]:
        zone = Zone(z["id"], z["name"], z["state"], z["road_link"], [], z.get("webcams", []), z.get("permit"))
        for a in z["areas"]:
            zone.areas.append(Area(zone=zone, **a))
        zones.append(zone)
    return zones


def all_areas(zones):
    return [a for z in zones for a in z.areas]

"""Projected snow depth map for the dashboard: today's SNODAS depth plus the next 48 hours of NBM forecast,
drawn in the NOHRSC map layer's classes and colors so it can stand in for that layer."""
import struct
import zlib

import numpy as np
from scipy.spatial import cKDTree

SETTLE = 0.5
RAIN_LOSS_IN = 3
SNOW_TO_WATER = 10
# NOHRSC class edges (1 cm up to 10 m) in inches, and the color of each class above the first.
EDGES_IN = np.array([0.01, 0.05, 0.1, 0.25, 0.5, 1, 1.5, 2.5, 5, 7.5, 10]) / 0.0254
COLORS = ("abc1bf", "66c1c4", "63a9cb", "5079c8", "3c3fc2", "5720c3", "7d01bb", "b404b1", "a91377", "992b50", "8b4545")


def project(depth_mm, lats, lons, sums):
    """Depth in inches after the forecast: new snow settles by half, each inch of rain takes 3 in off. Rain is
    the precipitation not accounted for by snowfall at 10:1."""
    lat2, lon2 = np.meshgrid(lats, lons, indexing="ij")
    k = np.cos(np.radians(lats.mean()))
    _, idx = cKDTree(np.c_[sums["lat"], sums["lon"] * k]).query(np.c_[lat2.ravel(), lon2.ravel() * k])
    snow = sums["asnow_in"][idx].reshape(lat2.shape)
    rain = np.maximum(0, sums["apcp_in"][idx].reshape(lat2.shape) - snow / SNOW_TO_WATER)
    return np.maximum(0, depth_mm / 25.4 + SETTLE * snow - RAIN_LOSS_IN * rain)


def _mercator_rows(lats, res):
    y = lambda lat: np.log(np.tan(np.pi / 4 + np.radians(lat) / 2))
    top, bottom = lats[0] + res / 2, lats[-1] - res / 2
    ys = y(top) + (np.arange(len(lats)) + 0.5) * (y(bottom) - y(top)) / len(lats)
    out_lat = np.degrees(2 * np.arctan(np.exp(ys)) - np.pi / 2)
    return np.clip(((top - out_lat) / res).astype(int), 0, len(lats) - 1)


def _png(index):
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
    h, w = index.shape
    palette = bytes(3) + b"".join(bytes.fromhex(c) for c in COLORS)
    alpha = bytes([0] + [255] * len(COLORS))
    raw = b"".join(b"\0" + row.astype(np.uint8).tobytes() for row in index)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 3, 0, 0, 0))
            + chunk(b"PLTE", palette) + chunk(b"tRNS", alpha) + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def build(depth_mm, lats, lons, sums):
    """(PNG bytes, [[south, west], [north, east]]) for the projected depth over a SNODAS grid."""
    res = lats[0] - lats[1]
    classes = np.digitize(np.nan_to_num(project(depth_mm, lats, lons, sums), nan=-1), EDGES_IN)
    image = _png(classes[_mercator_rows(lats, res)])
    bounds = [[lats[-1] - res / 2, lons[0] - res / 2], [lats[0] + res / 2, lons[-1] + res / 2]]
    return image, bounds

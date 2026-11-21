import unittest
from datetime import datetime, timezone

from skireport.sources import nws


def utc(day, hour):
    return datetime(2026, 1, day, hour, tzinfo=timezone.utc)


PROPS = {
    "elevation": {"value": 1524.0},
    "maxTemperature": {"values": [
        {"validTime": "2026-01-02T15:00:00+00:00/PT13H", "value": 0},
        {"validTime": "2026-01-03T15:00:00+00:00/PT13H", "value": 5},
    ]},
    "minTemperature": {"values": [
        {"validTime": "2026-01-02T03:00:00+00:00/PT14H", "value": -10},
        {"validTime": "2026-01-03T03:00:00+00:00/PT14H", "value": -5},
    ]},
}


class TempsTest(unittest.TestCase):
    def test_same_elevation_converts_to_fahrenheit(self):
        self.assertEqual(nws.temps(PROPS, 5000, (utc(2, 0), utc(3, 0)), (utc(2, 0), utc(3, 0))), (32, 14))

    def test_higher_area_is_colder(self):
        hi, lo = nws.temps(PROPS, 7000, (utc(2, 0), utc(3, 0)), (utc(2, 0), utc(3, 0)))
        self.assertEqual((hi, lo), (25, 7))

    def test_windows_pick_warmest_high_and_coldest_low(self):
        self.assertEqual(nws.temps(PROPS, 5000, (utc(2, 0), utc(4, 0)), (utc(1, 0), utc(4, 0))), (41, 14))

    def test_nothing_in_window(self):
        self.assertEqual(nws.temps(PROPS, 5000, (utc(5, 0), utc(6, 0)), (utc(5, 0), utc(6, 0))), (None, None))


if __name__ == "__main__":
    unittest.main()

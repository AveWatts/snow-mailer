import unittest
from datetime import date, timedelta

from skireport import analysis, scoring
from skireport.sources.snotel import Station, StationObs


def obs(depths, tmax=None, tmin=None, prec=None):
    start = date(2026, 1, 1)
    days = [start + timedelta(days=i) for i in range(len(depths))]
    series = {"SNWD": dict(zip(days, depths))}
    if tmax:
        series["TMAX"] = dict(zip(days, tmax))
    if tmin:
        series["TMIN"] = dict(zip(days, tmin))
    if prec:
        series["PREC"] = dict(zip(days, prec))
    return StationObs(Station("1:OR:SNTL", "Test", 45, -121, 5000), 1.0, series)


class Condition(unittest.TestCase):
    def test_thin(self):
        self.assertEqual(scoring.condition("nordic", scoring.SnowState(depth_in=5), 1), (1, "Too thin"))
        self.assertEqual(scoring.condition("backcountry", scoring.SnowState(depth_in=18), 1), (2, "Thin cover"))
        self.assertEqual(scoring.condition("nordic", scoring.SnowState(depth_in=0), 1), (1, "No snow"))

    def test_powder(self):
        s = scoring.SnowState(depth_in=60, new_3d_in=8, new_7d_in=8)
        self.assertEqual(scoring.condition("downhill", s, 1), (5, "Powder"))

    def test_rain_crust_beats_new_snow(self):
        s = scoring.SnowState(depth_in=60, new_3d_in=8, new_7d_in=8, rain_since_snow=True)
        self.assertEqual(scoring.condition("downhill", s, 1), (2, "Crust / ice"))

    def test_spring_corn(self):
        s = scoring.SnowState(depth_in=60, thaw_since_snow=True)
        self.assertEqual(scoring.condition("downhill", s, 4), (3, "Spring / corn"))
        self.assertEqual(scoring.condition("downhill", s, 1), (2, "Crust / ice"))

    def test_groomed(self):
        s = scoring.SnowState(depth_in=40, groomed_hours=20)
        self.assertEqual(scoring.condition("nordic", s, 1), (4, "Packed powder"))


class History(unittest.TestCase):
    def test_new_snow_then_rain(self):
        h = analysis.observed_history(obs(
            [40, 40, 46, 50, 49], tmax=[30, 30, 28, 28, 38], tmin=[20, 20, 20, 22, 31],
            prec=[10, 10, 10.6, 11.0, 11.5]))
        self.assertEqual(h["new_3d_in"], 10)
        self.assertTrue(h["rain_since_snow"])

    def test_cold_snow_no_crust(self):
        h = analysis.observed_history(obs([40, 44, 44], tmax=[25, 25, 25], tmin=[10, 10, 10], prec=[1, 1.5, 1.5]))
        self.assertFalse(h["rain_since_snow"] or h["thaw_since_snow"])


class Status(unittest.TestCase):
    def test_inferred_follows_condition(self):
        self.assertEqual([scoring.status_now("backcountry", None, None, 40, False, s, 60).value for s in (1, 2, 3, 5)],
                         ["Closed", "Sketchy", "Open", "Open"])
        self.assertEqual(scoring.status_now("backcountry", None, None, 40, False, 2, 60).confidence, 60)

    def test_road_closed_wins(self):
        self.assertEqual(scoring.status_now("nordic", None, None, 40, True, 5, 80).value, "Closed")

    def test_downhill_uses_resort_only(self):
        resort = {"status": "Open", "lifts_open": 1, "lifts_total": 8, "age_hours": 2}
        self.assertEqual(scoring.status_now("downhill", resort, None, 5, False, 1, 80).value, "Open")
        self.assertEqual(scoring.status_now("downhill", None, None, 90, False, 5, 80).value, "Unknown")

    def test_grooming_report_decides(self):
        fresh = scoring.status_now("nordic", None, {"age_hours": 20}, 5, False, 1, 80, grooming_reported=True)
        stale = scoring.status_now("nordic", None, {"age_hours": 400}, 90, False, 5, 80, grooming_reported=True)
        self.assertEqual((fresh.value, stale.value), ("Open", "Closed"))


class Confidence(unittest.TestCase):

    def test_spread(self):
        self.assertGreater(scoring.forecast_spread({10: 0.9, 50: 1.0, 90: 1.1}),
                           scoring.forecast_spread({10: 0.1, 50: 1.0, 90: 3.0}))


if __name__ == "__main__":
    unittest.main()

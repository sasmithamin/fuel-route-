from unittest import mock

import numpy as np
from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient

from planner.models import City, Station
from planner.services import stations as stations_mod
from planner.services.optimizer import Candidate, NoFeasibleRoute, plan_fuel_stops
from planner.services.routing import Route


def C(mile, price):
    return Candidate(mile, price, ref=f"s{mile}")


class OptimizerTests(TestCase):
    def test_short_trip_buys_only_what_it_burns(self):
        p = plan_fuel_stops([C(10, 3.0), C(100, 3.5)], total_miles=200)
        self.assertAlmostEqual(sum(x.gallons for x in p), 20.0)          # 200 mi / 10 mpg
        self.assertAlmostEqual(sum(x.cost for x in p), 20.0 * 3.0)

    def test_buys_just_enough_to_reach_cheaper_station(self):
        # expensive station at 0, cheap one 200 mi later, trip 600 mi
        p = plan_fuel_stops([C(0, 4.0), C(200, 3.0)], total_miles=600)
        first = p[0]
        self.assertTrue(first.is_departure)
        self.assertAlmostEqual(first.gallons, 20.0)                      # only 200 mi worth
        second = p[1]
        self.assertEqual(second.ref, "s200")
        self.assertAlmostEqual(second.gallons, 40.0)                     # remaining 400 mi

    def test_fills_up_when_nothing_cheaper_ahead(self):
        p = plan_fuel_stops([C(0, 3.0), C(400, 3.5), C(800, 3.6)], total_miles=1000)
        self.assertAlmostEqual(p[0].gallons, 50.0)                       # full 500-mile tank
        self.assertAlmostEqual(sum(x.gallons for x in p), 100.0)         # burns exactly 100 gal

    def test_never_exceeds_range_and_total_gallons_match_distance(self):
        rng = np.random.default_rng(1)
        cands = [C(float(m), float(rng.uniform(3, 4.5))) for m in np.sort(rng.uniform(1, 2999, 80))]
        p = plan_fuel_stops(cands, total_miles=3000)
        self.assertAlmostEqual(sum(x.gallons for x in p) * 10, 3000, places=4)
        miles = [x.mile for x in p]
        self.assertTrue(all(b - a <= 500 + 1e-6 for a, b in zip(miles, miles[1:])))

    def test_greedy_is_never_worse_than_fill_at_every_cheapest_in_range(self):
        # brute-force check on a tiny instance via DP over (station, fuel in 10-mile units)
        cands = [C(0, 3.9), C(120, 3.2), C(300, 3.6), C(450, 3.1), C(700, 3.8)]
        total, rng_, mpg = 900, 500, 10
        greedy = sum(x.cost for x in plan_fuel_stops(cands, total, rng_, mpg))
        pts = sorted({c.mile for c in cands} | {total})
        price = {c.mile: c.price for c in cands}
        price[0] = 3.9
        best = {(0, 0): 0.0}
        for a, b in zip(pts, pts[1:]):
            nxt = {}
            for (m, f), cost in best.items():
                d = (b - a) // 10
                for add in range(0, rng_ // 10 - f + 1):          # buy `add` units at m
                    nf = f + add - d
                    if nf < 0:
                        continue
                    c2 = cost + add * 10 / mpg * price[a]
                    k = (b, nf)
                    if c2 < nxt.get(k, 1e18):
                        nxt[k] = c2
            best = nxt
        self.assertAlmostEqual(greedy, min(best.values()), places=4)

    def test_gap_larger_than_range_raises(self):
        with self.assertRaises(NoFeasibleRoute):
            plan_fuel_stops([C(10, 3.0), C(700, 3.0)], total_miles=900)


class ApiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        City.objects.create(key="alpha", name="Alpha", state="TX", lat=32.0, lng=-100.0)
        City.objects.create(key="omega", name="Omega", state="TX", lat=32.0, lng=-90.0)
        # stations every ~0.5 degree (~29 mi) along lat 32 with varying prices, plus one far off-route
        for i, lng in enumerate(np.arange(-100, -90.01, 0.5)):
            Station.objects.create(opis_id=i, name=f"S{i}", address="I-20", city="X", state="TX",
                                   price=3.0 + (i % 5) * 0.2, lat=32.0, lng=float(lng))
        Station.objects.create(opis_id=999, name="FAR", address="", city="Y", state="TX",
                               price=1.0, lat=36.0, lng=-95.0)

    def setUp(self):
        cache.clear()
        stations_mod.reset_index()
        lngs = np.linspace(-100, -90, 400)
        self.route = Route(lngs, np.full_like(lngs, 32.0), distance_miles=585.0, duration_seconds=36000)

    def test_end_to_end_single_routing_call(self):
        with mock.patch("planner.services.planner.fetch_route", return_value=(self.route, 1)) as fr:
            r = APIClient().post("/api/route/", {"start": "Alpha, TX", "finish": "Omega, Texas"}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        d = r.json()
        fr.assert_called_once()
        self.assertEqual(d["meta"]["external_api_calls"], 1)
        fp = d["fuel_plan"]
        self.assertAlmostEqual(fp["total_gallons"], 58.5, places=1)      # 585 mi / 10 mpg
        self.assertTrue(all(s["name"] != "FAR" for s in fp["stops"]))     # off-corridor excluded
        total = fp["total_fuel_cost_usd"]
        parts = sum(s["cost_usd"] for s in fp["stops"]) + (fp["departure_fill"] or {}).get("cost_usd", 0)
        self.assertAlmostEqual(total, parts, delta=0.05)
        self.assertEqual(d["route"]["geometry"]["type"], "LineString")

    def test_second_identical_request_is_cached(self):
        with mock.patch("planner.services.planner.fetch_route", return_value=(self.route, 1)) as fr:
            c = APIClient()
            c.post("/api/route/", {"start": "Alpha, TX", "finish": "Omega, TX"}, format="json")
            r = c.post("/api/route/", {"start": "Alpha, TX", "finish": "Omega, TX"}, format="json")
        self.assertEqual(fr.call_count, 1)
        self.assertTrue(r.json()["meta"]["cached"])
        self.assertEqual(r.json()["meta"]["external_api_calls"], 0)

    def test_coordinates_input_and_validation_errors(self):
        c = APIClient()
        self.assertEqual(c.post("/api/route/", {"start": "x"}, format="json").status_code, 400)
        r = c.post("/api/route/", {"start": "51.5,-0.12", "finish": "Omega, TX"}, format="json")
        self.assertEqual(r.status_code, 400)                              # London: outside USA
        with mock.patch("planner.services.planner.fetch_route", return_value=(self.route, 1)):
            r = c.post("/api/route/", {"start": "32.0,-100.0", "finish": "32.0,-90.0"}, format="json")
        self.assertEqual(r.status_code, 200)

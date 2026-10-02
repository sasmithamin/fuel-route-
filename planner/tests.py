import numpy as np
from django.test import TestCase

from planner.services.optimizer import Candidate, NoFeasibleRoute, plan_fuel_stops


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
"""
Fuel-stop optimiser: the classic "gas station problem", solved greedily in O(n * w).

Fuel is tracked in *miles of range* (gallons = miles / mpg).

At every station we stand at, look at the stations reachable on a full tank:
  1. If a CHEAPER one exists, buy only what is needed to reach the first such station.
  2. Otherwise fill the tank, then drive to the cheapest reachable station
     (every other reachable station costs the same or more).
The destination is modelled as a station with price 0, so the car always arrives with
(almost) an empty tank and never pays for fuel it doesn't burn.  This greedy strategy
is optimal for a fixed route with a free choice of stops.

Departure: the car leaves the origin with an empty tank, and the origin is not a station,
so the first fill-up is priced at the first station on the route (`origin_price`).
"""
from dataclasses import dataclass
from typing import Any, List, Optional, Sequence

EPS = 1e-9


class NoFeasibleRoute(Exception):
    """Two consecutive stations are further apart than the vehicle's range."""


@dataclass
class Candidate:
    mile: float
    price: float            # USD / gallon
    ref: Any = None         # caller payload (e.g. station index); None for origin/destination


@dataclass
class Purchase:
    ref: Any
    mile: float
    price: float
    gallons: float
    cost: float
    is_departure: bool = False


def plan_fuel_stops(candidates: Sequence[Candidate], total_miles: float,
                    max_range: float = 500.0, mpg: float = 10.0) -> List[Purchase]:
    stations = sorted((c for c in candidates if 0 <= c.mile <= total_miles), key=lambda c: c.mile)
    if total_miles <= 0:
        return []
    if not stations:
        raise NoFeasibleRoute("No fuel stations found along the route.")

    nodes = [Candidate(0.0, stations[0].price, None)] + stations + [Candidate(total_miles, 0.0, None)]
    last = len(nodes) - 1
    purchases: List[Purchase] = []
    i, fuel = 0, 0.0                       # fuel = miles of range currently in the tank

    while i < last:
        cur = nodes[i]
        cheaper: Optional[int] = None
        cheapest_in_range: Optional[int] = None
        j = i + 1
        while j <= last and nodes[j].mile - cur.mile <= max_range + EPS:
            if nodes[j].price < cur.price - EPS:
                cheaper = j
                break
            if cheapest_in_range is None or nodes[j].price <= nodes[cheapest_in_range].price + EPS:
                cheapest_in_range = j      # `<=` prefers the furthest of equally cheap stations
            j += 1

        if cheaper is not None:
            target, buy = cheaper, max(0.0, nodes[cheaper].mile - cur.mile - fuel)
        elif cheapest_in_range is not None:
            target, buy = cheapest_in_range, max_range - fuel
        else:
            raise NoFeasibleRoute(
                f"No fuel station within {max_range:.0f} miles after mile {cur.mile:.0f}.")

        if buy > EPS:
            gallons = buy / mpg
            purchases.append(Purchase(cur.ref, cur.mile, cur.price, gallons,
                                      gallons * cur.price, is_departure=(i == 0)))
        fuel = fuel + buy - (nodes[target].mile - cur.mile)
        i = target

    return purchases
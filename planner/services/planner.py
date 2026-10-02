import hashlib

from django.conf import settings
from django.core.cache import cache

from . import geo, optimizer
from .locations import resolve_location
from .routing import fetch_route
from .stations import get_index


class NoFeasiblePlan(Exception):
    """Route can't be driven with the stations available (the API maps this to HTTP 422)."""


def plan_trip(start_text, finish_text):
    cfg = settings.FUEL
    start, c1 = resolve_location(start_text)
    finish, c2 = resolve_location(finish_text)

    # cache hit? return immediately
    key = "plan:" + hashlib.md5(
        f"{start.lat:.4f},{start.lng:.4f}|{finish.lat:.4f},{finish.lng:.4f}".encode()
    ).hexdigest()
    cached = cache.get(key)
    if cached:
        cached = {**cached, "meta": {**cached["meta"], "cache_hit": True,
                                     "external_api_calls": c1 + c2}}
        return cached

    # exactly ONE routing call
    route, c3 = fetch_route(start, finish)

    # match stations to the route (KD-tree)
    idx = get_index()
    matched = geo.match_stations(                      # ADAPT: match your geo.py signature
        route.lng, route.lat, idx.lng, idx.lat, cfg["CORRIDOR_MILES"])

    # optimize fuel stops
    plan = optimizer.optimize(                         # ADAPT: match your optimizer.py signature
        matched, idx.prices, route.distance_miles,
        max_range=cfg["MAX_RANGE_MILES"], mpg=cfg["MPG"])
    if plan is None:
        raise NoFeasiblePlan("No feasible fuel plan: gap between stations exceeds the tank range.")

    # format JSON
    result = {
        "start": {"label": start.label, "lat": start.lat, "lng": start.lng},
        "finish": {"label": finish.label, "lat": finish.lat, "lng": finish.lng},
        "route": {
            "distance_miles": round(route.distance_miles, 1),
            "geometry": [[round(x, 5), round(y, 5)]
                         for x, y in zip(route.lng[::5], route.lat[::5])],  # thin for the map
        },
        "fuel_stops": plan["stops"],                   # ADAPT: enrich with names/addresses from idx
        "total_cost": round(plan["total_cost"], 2),
        "meta": {"external_api_calls": c1 + c2 + c3, "cache_hit": False},
    }
    cache.set(key, result, 60 * 60)
    return result
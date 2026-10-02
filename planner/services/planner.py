import hashlib
from django.conf import settings
from django.core.cache import cache

from . import geo, optimizer
from .locations import resolve_location
from .routing import fetch_route
from .stations import get_index


class NoFeasiblePlan(Exception):
    """Route can't be driven with the stations available (the API maps this to HTTP 422)."""


def plan_trip(start_text: str, finish_text: str) -> dict:
    cfg = settings.FUEL
    start, c1 = resolve_location(start_text)
    finish, c2 = resolve_location(finish_text)

    # cache hit check
    key = "plan:" + hashlib.md5(
        f"{start.lat:.4f},{start.lng:.4f}|{finish.lat:.4f},{finish.lng:.4f}".encode()
    ).hexdigest()
    cached = cache.get(key)
    if cached:
        cached = {
            **cached,
            "meta": {
                **cached["meta"],
                "cached": True,
                "external_api_calls": c1 + c2,
            },
        }
        return cached

    # fetch route geometry and distance
    route, c3 = fetch_route(start, finish)

    # densify route geometry for precise station corridor matching
    cum_miles = geo.cumulative_miles(route.lng, route.lat)
    r_lng, r_lat, r_miles = geo.resample(
        route.lng, route.lat, cum_miles, cfg.get("RESAMPLE_STEP_MILES", 1.0)
    )

    # match stations along route corridor using KD-tree
    idx = get_index()
    matched_st_indices, _, mile_markers = geo.match_stations(
        idx.lat, idx.lng, r_lng, r_lat, r_miles, cfg["CORRIDOR_MILES"]
    )

    # build candidates for fuel stop optimization
    candidates = [
        optimizer.Candidate(
            mile=float(mm),
            price=float(idx.prices[st_i]),
            ref=int(st_i),
        )
        for st_i, mm in zip(matched_st_indices, mile_markers)
    ]

    try:
        purchases = optimizer.plan_fuel_stops(
            candidates,
            route.distance_miles,
            max_range=cfg["MAX_RANGE_MILES"],
            mpg=cfg["MPG"],
            min_saving=cfg.get("MIN_SAVING_PER_GALLON", 0.0),
        )
    except optimizer.NoFeasibleRoute as e:
        raise NoFeasiblePlan(str(e))

    stops = []
    departure_fill = None
    total_gallons = 0.0
    total_cost = 0.0

    for p in purchases:
        total_gallons += p.gallons
        total_cost += p.cost
        if p.is_departure:
            departure_fill = {
                "mile_marker": round(p.mile, 1),
                "gallons": round(p.gallons, 2),
                "price_per_gallon": round(p.price, 3),
                "cost_usd": round(p.cost, 2),
            }
        else:
            st_i = p.ref
            stops.append(
                {
                    "opis_id": int(idx.ids[st_i]),
                    "name": str(idx.names[st_i]),
                    "address": str(idx.addresses[st_i]),
                    "city": str(idx.cities[st_i]),
                    "state": str(idx.states[st_i]),
                    "lat": float(idx.lat[st_i]),
                    "lng": float(idx.lng[st_i]),
                    "mile_marker": round(p.mile, 1),
                    "gallons": round(p.gallons, 2),
                    "price_per_gallon": round(p.price, 3),
                    "cost_usd": round(p.cost, 2),
                }
            )

    # Thin route geometry for client response
    thin_lng, thin_lat = geo.thin(
        route.lng, route.lat, cum_miles, cfg.get("OUTPUT_THIN_MILES", 0.25)
    )
    geometry_coords = [
        [round(float(x), 5), round(float(y), 5)]
        for x, y in zip(thin_lng, thin_lat)
    ]

    result = {
        "start": {"label": start.label, "lat": start.lat, "lng": start.lng},
        "finish": {"label": finish.label, "lat": finish.lat, "lng": finish.lng},
        "route": {
            "distance_miles": round(route.distance_miles, 1),
            "duration_hours": round(route.duration_hours, 2),
            "geometry": {
                "type": "LineString",
                "coordinates": geometry_coords,
            },
        },
        "fuel_plan": {
            "total_gallons": round(total_gallons, 2),
            "total_fuel_cost_usd": round(total_cost, 2),
            "departure_fill": departure_fill,
            "stops": stops,
        },
        "meta": {
            "external_api_calls": c1 + c2 + c3,
            "cached": False,
        },
    }

    cache.set(key, result, 60 * 60 * 24)
    return result
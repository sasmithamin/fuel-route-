from dataclasses import dataclass

import numpy as np
import requests
from django.conf import settings
from django.core.cache import cache

_session = requests.Session()
METERS_PER_MILE = 1609.344


class RoutingError(Exception):
    """Routing service failed (the API maps this to HTTP 502)."""


@dataclass
class Route:
    lng: np.ndarray
    lat: np.ndarray
    distance_miles: float
    duration_hours: float


def fetch_route(start, finish):
    """Return (Route, external_calls). start/finish are Location objects."""
    key = (f"route:{start.lat:.4f},{start.lng:.4f}"
           f":{finish.lat:.4f},{finish.lng:.4f}")
    cached = cache.get(key)
    if cached is not None:
        return cached, 0

    # OSRM wants lng,lat order
    url = (f"{settings.OSRM_BASE_URL}/route/v1/driving/"
           f"{start.lng},{start.lat};{finish.lng},{finish.lat}")
    try:
        r = _session.get(
            url,
            params={"overview": "full", "geometries": "geojson"},
            headers={"User-Agent": settings.HTTP_USER_AGENT},
            timeout=20,
        )
        r.raise_for_status()
        data = r.json()
    except (requests.RequestException, ValueError) as e:
        raise RoutingError(f"Routing service error: {e}")

    if data.get("code") != "Ok" or not data.get("routes"):
        raise RoutingError(f"No route found ({data.get('code')}).")

    rt = data["routes"][0]
    coords = np.array(rt["geometry"]["coordinates"], dtype=float)  # [[lng, lat], ...]
    route = Route(
        lng=coords[:, 0],
        lat=coords[:, 1],
        distance_miles=rt["distance"] / METERS_PER_MILE,
        duration_hours=rt["duration"] / 3600,
    )
    cache.set(key, route, 60 * 60 * 24)
    return route, 1
import re
from dataclasses import dataclass

import requests
from django.conf import settings
from django.core.cache import cache

from planner.models import City

# contiguous USA bounding box
LAT_MIN, LAT_MAX, LNG_MIN, LNG_MAX = 24.4, 49.5, -125.0, -66.9

COORD_RE = re.compile(r"^\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*$")
CITY_ST_RE = re.compile(r"^\s*([^,]+?)\s*,\s*([A-Za-z]{2})\s*$")

_session = requests.Session()


class LocationError(Exception):
    """Bad or unresolvable location (the API maps this to HTTP 400)."""


@dataclass(frozen=True)
class Location:
    lat: float
    lng: float
    label: str
    source: str  # 'coords' | 'gazetteer' | 'nominatim'


def norm_city(s):  # identical to the one in scripts/clean_and_geocode.py
    s = str(s).lower().strip()
    s = re.sub(r"\bst\.?\b", "saint", s)
    s = re.sub(r"\bste\.?\b", "sainte", s)
    s = re.sub(r"\bft\.?\b", "fort", s)
    s = re.sub(r"\bmt\.?\b", "mount", s)
    s = re.sub(r"[^a-z0-9 ]", "", s)
    return re.sub(r"\s+", " ", s).strip()


def _check_usa(lat, lng, text):
    if not (LAT_MIN <= lat <= LAT_MAX and LNG_MIN <= lng <= LNG_MAX):
        raise LocationError(f"'{text}' is outside the contiguous USA.")


def _nominatim(text):
    key = "geo:" + norm_city(text)
    hit = cache.get(key)
    if hit:
        return hit, 0
    try:
        r = _session.get(
            settings.NOMINATIM_URL,
            params={"q": text, "format": "json", "limit": 1, "countrycodes": "us"},
            headers={"User-Agent": settings.HTTP_USER_AGENT},
            timeout=10,
        )
        r.raise_for_status()
        data = r.json()
    except requests.RequestException as e:
        raise LocationError(f"Could not look up '{text}': {e}")
    if not data:
        raise LocationError(f"Could not find location '{text}'.")
    loc = Location(float(data[0]["lat"]), float(data[0]["lon"]),
                   data[0].get("display_name", text), "nominatim")
    cache.set(key, loc, 60 * 60 * 24)
    return loc, 1


def resolve_location(text):
    """Return (Location, external_calls)."""
    if not text or not str(text).strip():
        raise LocationError("Location is empty.")
    text = str(text).strip()

    # 1. "lat,lng": parsed locally
    m = COORD_RE.match(text)
    if m:
        lat, lng = float(m.group(1)), float(m.group(2))
        _check_usa(lat, lng, text)
        return Location(lat, lng, f"{lat:.4f}, {lng:.4f}", "coords"), 0

    # 2. "City, ST": local City table
    m = CITY_ST_RE.match(text)
    if m:
        city = City.objects.filter(key=norm_city(m.group(1)),
                                   state=m.group(2).upper()).first()
        if city:
            return Location(city.lat, city.lng,
                            f"{city.name}, {city.state}", "gazetteer"), 0

    # 3. fallback: Nominatim (cached)
    loc, calls = _nominatim(text)
    _check_usa(loc.lat, loc.lng, text)
    return loc, calls
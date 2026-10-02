from dataclasses import dataclass

import numpy as np

from planner.models import Station


@dataclass
class StationIndex:
    ids: np.ndarray
    names: np.ndarray
    addresses: np.ndarray
    cities: np.ndarray
    states: np.ndarray
    prices: np.ndarray
    lat: np.ndarray
    lng: np.ndarray


_index = None


def get_index():
    """Load all stations once per process and keep them in memory."""
    global _index
    if _index is None:
        rows = list(Station.objects.values_list(
            "opis_id", "name", "address", "city", "state", "price", "lat", "lng"))
        if not rows:
            raise RuntimeError("No stations loaded. Run: python manage.py load_data")
        cols = list(zip(*rows))
        _index = StationIndex(
            ids=np.array(cols[0]), names=np.array(cols[1]),
            addresses=np.array(cols[2]), cities=np.array(cols[3]),
            states=np.array(cols[4]), prices=np.array(cols[5], dtype=float),
            lat=np.array(cols[6], dtype=float), lng=np.array(cols[7], dtype=float),
        )
    return _index


def reset_index():
    """Reset cached station index (used in test setup)."""
    global _index
    _index = None
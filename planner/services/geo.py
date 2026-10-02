"""Vectorised geometry helpers (numpy / scipy only, no external calls)."""
import numpy as np
from scipy.spatial import cKDTree

EARTH_RADIUS_MI = 3958.7613


def to_xyz(lats, lngs) -> np.ndarray:
    """lat/lng degrees -> 3-D points on a sphere (miles).  KD-tree distance in this
    space is accurate everywhere in the USA, unlike a flat lat/lng approximation."""
    la, lo = np.radians(lats), np.radians(lngs)
    c = np.cos(la)
    return EARTH_RADIUS_MI * np.column_stack((c * np.cos(lo), c * np.sin(lo), np.sin(la)))


def haversine_miles(lat1, lng1, lat2, lng2):
    lat1, lng1, lat2, lng2 = map(np.radians, (lat1, lng1, lat2, lng2))
    a = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lng2 - lng1) / 2) ** 2
    return 2 * EARTH_RADIUS_MI * np.arcsin(np.sqrt(a))


def cumulative_miles(lngs, lats) -> np.ndarray:
    seg = haversine_miles(lats[:-1], lngs[:-1], lats[1:], lngs[1:])
    return np.concatenate(([0.0], np.cumsum(seg)))


def resample(lngs, lats, cum, step):
    """Evenly spaced points along the route so corridor matching never skips a long segment."""
    s = np.unique(np.append(np.arange(0.0, cum[-1], step), cum[-1]))
    return np.interp(s, cum, lngs), np.interp(s, cum, lats), s


def thin(lngs, lats, cum, min_gap):
    """Drop vertices closer than min_gap miles (keeps payload small)."""
    idx = np.unique(np.append(np.searchsorted(cum, np.arange(0.0, cum[-1], min_gap)), len(cum) - 1))
    return lngs[idx], lats[idx]


def match_stations(st_lats, st_lngs, route_lngs, route_lats, route_miles, corridor_miles):
    """For every station find the nearest route point.  Returns
    (station_indices, distance_off_route_miles, mile_marker) for stations inside the corridor."""
    tree = cKDTree(to_xyz(route_lats, route_lngs))
    dist, nearest = tree.query(to_xyz(st_lats, st_lngs), distance_upper_bound=corridor_miles)
    ok = np.isfinite(dist)
    return np.flatnonzero(ok), dist[ok], route_miles[nearest[ok]]
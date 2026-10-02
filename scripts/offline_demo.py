"""
Offline demo script showing the full fuel routing pipeline without needing external HTTP calls.
"""
import os
import sys
from pathlib import Path

# Setup Django environment
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django
django.setup()

import numpy as np
from planner.services import geo, optimizer, stations


def run_offline_demo():
    print("=== Fuel Route Planner: Offline Demo ===")
    
    # 1. Load station index from database
    idx = stations.get_index()
    print(f"Loaded {len(idx.ids)} fuel stations into memory.")

    # 2. Generate synthetic cross-country route (LA -> NYC approximation)
    start_lat, start_lng = 34.0522, -118.2437  # Los Angeles
    finish_lat, finish_lng = 40.7128, -74.0060  # New York City
    
    steps = 1000
    lats = np.linspace(start_lat, finish_lat, steps)
    lngs = np.linspace(start_lng, finish_lng, steps)
    
    cum_miles = geo.cumulative_miles(lngs, lats)
    total_miles = float(cum_miles[-1])
    print(f"Synthetic route length: {total_miles:.1f} miles")

    # 3. Resample route and match stations within 10 mile corridor
    r_lng, r_lat, r_miles = geo.resample(lngs, lats, cum_miles, 1.0)
    matched_indices, distances, mile_markers = geo.match_stations(
        idx.lat, idx.lng, r_lng, r_lat, r_miles, 10.0
    )
    print(f"Found {len(matched_indices)} stations within the 10-mile corridor.")

    # 4. Build candidates and optimize fuel stops
    candidates = [
        optimizer.Candidate(mile=float(mm), price=float(idx.prices[st_i]), ref=int(st_i))
        for st_i, mm in zip(matched_indices, mile_markers)
    ]
    
    purchases = optimizer.plan_fuel_stops(
        candidates, total_miles, max_range=500.0, mpg=10.0, min_saving=0.0
    )

    # 5. Display fuel stop itinerary
    total_cost = sum(p.cost for p in purchases)
    total_gallons = sum(p.gallons for p in purchases)

    print("\n--- Optimal Fuel Itinerary ---")
    stops_count = 0
    for i, p in enumerate(purchases):
        if p.is_departure:
            print(f"[Departure Fill] Mile 0.0: {p.gallons:.2f} gal @ ${p.price:.3f}/gal (${p.cost:.2f})")
        else:
            stops_count += 1
            st_i = p.ref
            name = idx.names[st_i]
            city = idx.cities[st_i]
            state = idx.states[st_i]
            print(f"[Stop #{stops_count}] Mile {p.mile:.1f}: {name} ({city}, {state}) - "
                  f"{p.gallons:.2f} gal @ ${p.price:.3f}/gal (${p.cost:.2f})")

    print("\n--- Summary ---")
    print(f"Total distance: {total_miles:.1f} miles")
    print(f"Total fuel:     {total_gallons:.2f} gallons")
    print(f"Total cost:     ${total_cost:.2f}")
    print(f"Total stops:    {stops_count}")
    print("========================================")


if __name__ == "__main__":
    run_offline_demo()

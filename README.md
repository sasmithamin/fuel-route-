# Fuel Route Planner

A high-performance Django web application and REST API that calculates optimal fuel stops along any driving route in the contiguous United States, minimizing total trip fuel cost for a vehicle with a 500-mile range and 10 MPG fuel efficiency.

---

## Features

- **Greedy Fuel-Stop Optimizer ($O(N \cdot W)$):** Computes mathematically optimal refuel points and gallon purchases using the classic gas station algorithm.
- **Offline Gazetteer & KD-Tree Station Matching:** Performs spatial queries in milliseconds across 6,600+ fuel stations using 3D spherical coordinates and SciPy `cKDTree` without expensive geocoding API calls.
- **Single External API Call Guarantee:** Resolves endpoints via local US gazetteer database and makes exactly **one** HTTP request to OSRM for route geometry.
- **Caching Layer:** Caches route plans and geocoding results so repeated or identical trips require **0** external API calls.
- **Interactive Dark-Mode Map UI:** Visualizes the route, start/finish points, and fuel stops with Leaflet maps and interactive statistics.

---

## Getting Started & Installation

### Prerequisites
- Python 3.10+
- Virtual environment (`.venv`)

### 1. Set Up Environment
```bash
python -m venv .venv
# On Windows PowerShell:
.venv\Scripts\Activate.ps1
# On Linux / macOS:
source .venv/bin/activate

pip install -r requirements.txt
```

### 2. Database Migration & Data Ingestion
Initialize the SQLite database schema and load stations/cities from the geocoded datasets:
```bash
python manage.py migrate
python manage.py load_data
```

---

## How to Run

### Option A: Interactive Web UI & API Server
Start the local Django development server:
```bash
python manage.py runserver
```
- Open [http://127.0.0.1:8000/](http://127.0.0.1:8000/) in your browser to use the Leaflet Map UI.
- Enter any start/finish locations (e.g., `Dallas, TX` to `Seattle, WA` or `34.05,-118.24` to `40.71,-74.00`).

### Option B: Offline Demo Script (No Internet Required)
Run the standalone pipeline script on a synthetic cross-country route:
```bash
python scripts/offline_demo.py
```

### Option C: API Request via Curl
```bash
curl -X POST http://127.0.0.1:8000/api/route/ \
     -H "Content-Type: application/json" \
     -d '{"start": "Dallas, TX", "finish": "Seattle, WA"}'
```

---

## How to Run Tests

Run the full suite of unit and integration tests (including optimizer verification against DP brute force, cache tests, and mocked API tests):

```bash
python manage.py test planner
```

---

## Key Assumptions & Design Decisions

1. **Departure Fuel State:** The vehicle leaves the origin with an empty tank, and the initial fuel fill is priced at the first fuel station on the route (`mile 0.0`).
2. **City Centroid Geocoding:** Stations are geocoded using offline US city centroids. Because highway exit addresses often fail online geocoding, city centroids provide reliable coordinates that fall within the 10-mile route corridor.
3. **Lowest Station Price Strategy:** Where multiple price listings exist for a single OPIS Truckstop ID, the lowest price is selected during raw data cleaning.
4. **Contiguous USA Scope:** Routing is bounded within the contiguous USA (latitudes 24.4°N to 49.5°N, longitudes -125.0°W to -66.9°W).

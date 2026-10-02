# Build Guide: Fuel Route Planner, one commit per step

All final files are in `fuelroute.zip`. For each step: create the file yourself (or copy it from the zip), run the **Verify** command, then commit.
Every commit leaves the project in a working state.

**Phases:** A. Data cleaning (steps 1-5) → B. Django foundation (6-8) → C. Core logic (9-13) → D. API and map (14-16) → E. Polish (17-18)

---

# PHASE A: DATA CLEANING

## Step 1: Repo and raw data
```bash
mkdir fuelroute && cd fuelroute && git init
python -m venv .venv && source .venv/bin/activate
pip install pandas
mkdir data scripts
cp /path/to/fuel-prices-for-be-assessment.csv data/
curl -L -o data/us_cities_raw.csv \
  https://raw.githubusercontent.com/kelvins/US-Cities-Database/main/csv/us_cities.csv
printf "__pycache__/\n*.pyc\ndb.sqlite3\n.venv/\n" > .gitignore
```
`us_cities_raw.csv` (about 29,880 US cities with latitude/longitude) is how we get coordinates **without any geocoding API**.

**Commit:** `git add . && git commit -m "chore: add raw fuel prices and US cities gazetteer"`

## Step 2: Profile the data (know what you're cleaning)
Create `scripts/inspect_data.py`:
```python
import pandas as pd
df = pd.read_csv("data/fuel-prices-for-be-assessment.csv")
print(df.shape, df.columns.tolist())
print(df.isna().sum())
print("unique station IDs:", df["OPIS Truckstop ID"].nunique())
print("exact duplicate rows:", df.duplicated().sum())
print("states:", sorted(df["State"].unique()))
g = df.groupby("OPIS Truckstop ID")["Retail Price"].nunique()
print("IDs with >1 distinct price:", (g > 1).sum())
print(df["Retail Price"].describe())
print(df["Address"].sample(8, random_state=1).tolist())
```
Run `python scripts/inspect_data.py`. **What you should find:**

| Finding | Number | Consequence |
|---|---|---|
| Rows | 8,151 | |
| Unique station IDs | 6,738 | duplicates must be collapsed |
| Exact duplicate rows | 26 | drop |
| Canadian provinces (AB, BC, MB, NB, NS, ON, QC, SK, YT) | present | assignment is USA only → drop |
| Same ID, different prices | 597 IDs | pick a rule (we use the lowest) |
| Addresses like `I-44, EXIT 283 & US-69` | about 88% | street geocoders fail → geocode by **city** |
| Missing values | 0 | nothing to impute |

**Commit:** `git commit -am "chore: add data profiling script"` (after `git add scripts`)

## Step 3: Clean: filter and dedupe
Create `scripts/clean_and_geocode.py`. Write the cleaning half first:
```python
import pandas as pd
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"
CANADA = {"AB", "BC", "MB", "NB", "NS", "ON", "QC", "SK", "YT"}

raw = pd.read_csv(DATA / "fuel-prices-for-be-assessment.csv")

# 1. consistent column names
df = raw.rename(columns={
    "OPIS Truckstop ID": "opis_id", "Truckstop Name": "name", "Address": "address",
    "City": "city", "State": "state", "Rack ID": "rack_id", "Retail Price": "price"})

# 2. trim whitespace (city names are padded with spaces!) and upper-case state
for col in ("name", "address", "city", "state"):
    df[col] = df[col].astype(str).str.strip()
df["state"] = df["state"].str.upper()

# 3. USA only
df = df[~df["state"].isin(CANADA)]                       # 8151 -> 7531

# 4. drop invalid prices and exact duplicate rows
df = df[df["price"] > 0].drop_duplicates()               # 7531 -> 7505

# 5. ONE row per station ID
stations = df.groupby("opis_id").agg(
    name=("name", lambda s: max(s, key=len)),            # 'PILOT TRAVEL CENTER #1243' beats 'PILOT #1243'
    address=("address", lambda s: s.mode().iat[0]),
    city=("city", lambda s: s.mode().iat[0]),
    state=("state", lambda s: s.mode().iat[0]),
    rack_id=("rack_id", "first"),
    price=("price", "min"),                              # lowest price per station (documented assumption)
).reset_index()                                          # -> 6626 stations
print(len(stations), "unique stations")
```
**Why `min`?** The same station appears with several prices (different dates or fuel grades are likely). Choosing one is an assumption, so write it in the README. The zip's script has a `--price-strategy min|mean|median` flag.

**Verify:** prints `6626 unique stations`.

**Commit:** `git commit -am "feat(data): clean fuel prices (drop Canada, dedupe by station ID)"`

## Step 4: Geocode offline by city centroid
Add this below step 3, replacing the final `print`:
```python
import re

def norm_city(s):
    s = str(s).lower().strip()
    s = re.sub(r"\bst\.?\b", "saint", s)      # "St. Louis" == "Saint Louis"
    s = re.sub(r"\bste\.?\b", "sainte", s)
    s = re.sub(r"\bft\.?\b", "fort", s)
    s = re.sub(r"\bmt\.?\b", "mount", s)
    s = re.sub(r"[^a-z0-9 ]", "", s)
    return re.sub(r"\s+", " ", s).strip()

cities = pd.read_csv(DATA / "us_cities_raw.csv").rename(columns={
    "CITY": "name", "STATE_CODE": "state", "LATITUDE": "lat", "LONGITUDE": "lng"})
cities["key"] = cities["name"].map(norm_city)
lookup = (cities.drop_duplicates(["key", "state"])
          .set_index(["key", "state"])[["lat", "lng"]].to_dict("index"))

# 6 cities spelled differently in the gazetteer: add by hand
MANUAL = {("port wentworth", "GA"): (32.1488, -81.1626), ("elizabethport", "NJ"): (40.6457, -74.1932),
          ("brookpark", "OH"): (41.3995, -81.8046), ("evergreen", "AL"): (31.4335, -86.9544),
          ("henrico", "VA"): (37.5543, -77.3330), ("university park", "IL"): (41.4423, -87.6836)}
for k, (la, ln) in MANUAL.items():
    lookup.setdefault(k, {"lat": la, "lng": ln})

def coords(row):
    hit = lookup.get((norm_city(row["city"]), row["state"]))
    return pd.Series([hit["lat"], hit["lng"]] if hit else [None, None])

stations[["lat", "lng"]] = stations.apply(coords, axis=1)
print("unmatched:", stations["lat"].isna().sum())       # expect 0
stations = stations.dropna(subset=["lat", "lng"])
```
**Why city-level?** About 88% of addresses are highway exits, so street geocoding fails. A city centroid is within a few miles of the truck stop, which is fine because the API searches a 10-mile corridor around the route. It is also instant, free, and needs no API key.

**Commit:** `git commit -am "feat(data): geocode stations offline via city centroid"`

## Step 5: Write outputs and commit the generated data
Append:
```python
stations["price"] = stations["price"].round(4)
stations.to_csv(DATA / "stations_geocoded.csv", index=False)
cities[["name", "state", "lat", "lng", "key"]].to_csv(DATA / "us_cities.csv", index=False)
```
**Verify:** `python scripts/clean_and_geocode.py && head -3 data/stations_geocoded.csv`

We commit the generated CSVs so a reviewer doesn't have to rerun the pipeline.

**Commit:** `git add data && git commit -m "feat(data): export stations_geocoded.csv and us_cities.csv"`

---

# PHASE B: DJANGO FOUNDATION

## Step 6: Django skeleton
```bash
pip install "django==6.1.1" djangorestframework numpy scipy requests pandas
pip freeze > /dev/null   # (we use a hand-written requirements.txt instead)
django-admin startproject config .
python manage.py startapp planner
mkdir -p planner/services planner/management/commands planner/templates/planner
touch planner/services/__init__.py planner/management/__init__.py planner/management/commands/__init__.py
```
Create `requirements.txt` (copy from the zip). Edit `config/settings.py` to match the zip's version. The key parts:
- `INSTALLED_APPS`: add `"rest_framework"`, `"planner"`
- DRF set to JSON-only, no auth
- `FUEL = {"MAX_RANGE_MILES": 500, "MPG": 10, "CORRIDOR_MILES": 10, ...}`
- `OSRM_BASE_URL`, `NOMINATIM_URL`, `HTTP_USER_AGENT`
- `CACHES` (local memory)

**Verify:** `python manage.py check` → `no issues`

**Commit:** `git add . && git commit -m "chore: django 6.1 project skeleton with DRF and fuel settings"`

## Step 7: Models and migration
Copy `planner/models.py` (`City` and `Station`). Then:
```bash
python manage.py makemigrations planner && python manage.py migrate
```
**Commit:** `git add . && git commit -m "feat: Station and City models"`

## Step 8: Data loader command
Copy `planner/management/commands/load_data.py`.

**Verify:** `python manage.py load_data` → `Loaded 6626 stations and 29738 cities.` Run it twice. It's idempotent.

**Commit:** `git add . && git commit -m "feat: load_data management command"`

---

# PHASE C: CORE LOGIC

## Step 9: Geometry helpers → `planner/services/geo.py`
Functions: `to_xyz`, `haversine_miles`, `cumulative_miles`, `resample`, `thin`, `match_stations`.

The key idea is that `match_stations` builds a KD-tree of route points and queries all 6,626 stations at once, which takes a few milliseconds. It returns each station's distance from the route and its **mile marker** (distance along the route).

**Verify:**
```bash
python manage.py shell -c "
import numpy as np
from planner.services import geo
lng=np.array([-100.,-90.]); lat=np.array([32.,32.])
print(geo.cumulative_miles(lng,lat))   # about [0, 585]"
```
**Commit:** `git add . && git commit -m "feat: geometry helpers (haversine, resample, KD-tree station matching)"`

## Step 10: The optimizer → `planner/services/optimizer.py` (the heart of the assignment)
Fuel is tracked in *miles of range*. At each station:
1. If a **cheaper** station is reachable on a full tank, buy **only enough** to reach the first such station.
2. Otherwise **fill up**, then go to the cheapest reachable station.
3. The destination is a virtual station with price 0, so you arrive nearly empty.

Create `planner/tests.py` with **only** the `OptimizerTests` class from the zip (6 tests, including a brute-force comparison).

**Verify:** `python manage.py test planner` → 6 tests OK

**Commit:** `git add . && git commit -m "feat: greedy fuel-stop optimizer with tests (incl. brute-force check)"`

## Step 11: Location resolver → `planner/services/locations.py`
Input handling that keeps external calls low:
- `"34.05,-118.24"` is parsed locally (0 calls)
- `"Dallas, TX"` is looked up in the `City` table (0 calls)
- anything else goes to Nominatim, then cached (1 call)
- anything outside the contiguous USA is rejected

**Verify:**
```bash
python manage.py shell -c "
from planner.services.locations import resolve_location
print(resolve_location('Dallas, TX'))"    # source='gazetteer', 0 calls
```
**Commit:** `git add . && git commit -m "feat: location resolver (coords, local gazetteer, Nominatim fallback)"`

## Step 12: Routing client → `planner/services/routing.py`
**One** HTTP GET to OSRM (`overview=full&geometries=geojson`) returns the full polyline and distance. The result is cached, and a `requests.Session` is reused.

**Verify (needs internet):**
```bash
python manage.py shell -c "
from planner.services.locations import resolve_location as r
from planner.services.routing import fetch_route
a,_=r('Dallas, TX'); b,_=r('Houston, TX')
route,calls=fetch_route(a,b); print(route.distance_miles, calls)"   # about 240 mi, 1
```
**Commit:** `git add . && git commit -m "feat: OSRM routing client (single call, cached)"`

## Step 13: Station index and planner orchestration
Copy `planner/services/stations.py` (all stations held in memory as numpy arrays) and `planner/services/planner.py`. The `plan_trip` function runs this pipeline:

resolve → (cache hit? return) → **1 route call** → match stations → optimize → format JSON → cache

**Commit:** `git add . && git commit -m "feat: stations in-memory index and plan_trip orchestration"`

---

# PHASE D: API AND MAP

## Step 14: API endpoint
Copy `planner/serializers.py`, `planner/views.py`, `planner/urls.py`. Then in `config/urls.py` use:
```python
from django.urls import include, path
urlpatterns = [path("", include("planner.urls"))]
```
Error mapping: bad input → **400**, no feasible plan → **422**, routing down → **502**.

**Verify (needs internet):**
```bash
python manage.py runserver
curl -X POST localhost:8000/api/route/ -H 'Content-Type: application/json' \
     -d '{"start":"Dallas, TX","finish":"Seattle, WA"}'
```
**Commit:** `git add . && git commit -m "feat: POST /api/route/ endpoint with error handling"`

## Step 15: API tests
Add the `ApiTests` class from the zip to `planner/tests.py`. It mocks the routing call, so it needs no internet. It verifies exactly one routing call, cache behaviour, off-corridor stations excluded, and input validation.

**Verify:** `python manage.py test planner` → 9 tests OK

**Commit:** `git add . && git commit -m "test: API integration tests with mocked routing"`

## Step 16: Map page
Copy `planner/templates/planner/map.html` (Leaflet draws the route, stop markers and a cost table). The route `/` is already wired up in `planner/urls.py`.

**Verify:** open http://127.0.0.1:8000/ and click **Plan route**.

**Commit:** `git add . && git commit -m "feat: Leaflet map UI"`

---

# PHASE E: POLISH

## Step 17: Offline demo and tuning knob
- Copy `scripts/offline_demo.py`. It runs the whole pipeline with a synthetic route, so it needs no internet.
- Add the optional `min_saving` parameter to the optimizer. A station counts as "cheaper" only if it saves at least `min_saving` $/gal, which avoids 1-gallon stops. Expose it as `FUEL["MIN_SAVING_PER_GALLON"]` (default `0.0`) and pass it through in `planner.py`.

**Verify:** `python scripts/offline_demo.py` → LA→NYC about $886, 1 external call

**Commit:** `git add . && git commit -m "feat: offline demo script and min-saving optimizer option"`

## Step 18: README
Copy `README.md` and edit it. Set your own contact in `HTTP_USER_AGENT`. **State your assumptions clearly:**
- the empty tank at departure, with the first fill-up priced at the first station on the route
- city-centroid geocoding
- the lowest price chosen per station
- detours not counted

**Commit:** `git add . && git commit -m "docs: README with setup, API, design and assumptions"`

---

## Final checklist before sending
- [ ] Fresh clone works: `pip install -r requirements.txt && python manage.py migrate && python manage.py load_data && python manage.py test`
- [ ] A real request returns in well under a second (after the first cached route)
- [ ] `meta.external_api_calls` is 1 for `"City, ST"` input
- [ ] README assumptions section is honest
- [ ] Push to GitHub and include a short Loom/screen recording showing the map and one API call

## Likely interview questions (be ready)
1. **Why greedy, and is it optimal?** For a fixed route, yes. The cheapest-next-station argument is the classic gas-station problem, and the tests compare it with a dynamic-programming optimum.
2. **Why city-level geocoding?** The addresses are highway exits. It's offline and free, and the 10-mile corridor absorbs the error.
3. **How do you keep API calls to one?** Local gazetteer for the endpoints, one OSRM call for the geometry, and everything else in numpy and a KD-tree.
4. **What would you change for production?** Self-hosted routing, PostGIS and real station coordinates, Redis cache, detour-aware costs, and price freshness.

import re
import pandas as pd
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"
CANADA = {"AB", "BC", "MB", "NB", "NS", "ON", "QC", "SK", "YT"}

raw = pd.read_csv(DATA / "fuel-prices-for-be-assessment.csv")
print("raw rows:", len(raw))

# 1. consistent column names
df = raw.rename(columns={
    "OPIS Truckstop ID": "opis_id", "Truckstop Name": "name", "Address": "address",
    "City": "city", "State": "state", "Rack ID": "rack_id", "Retail Price": "price"})

# 2. trim whitespace and upper-case state
for col in ("name", "address", "city", "state"):
    df[col] = df[col].astype(str).str.strip()
df["state"] = df["state"].str.upper()

# 3. USA only
df = df[~df["state"].isin(CANADA)]
print("after dropping Canada:", len(df))

# 4. drop invalid prices and exact duplicate rows
df = df[df["price"] > 0].drop_duplicates()
print("after removing duplicates:", len(df))

# 5. ONE row per station ID
stations = df.groupby("opis_id").agg(
    name=("name", lambda s: max(s, key=len)),
    address=("address", lambda s: s.mode().iat[0]),
    city=("city", lambda s: s.mode().iat[0]),
    state=("state", lambda s: s.mode().iat[0]),
    rack_id=("rack_id", "first"),
    price=("price", "min"),
).reset_index()
print(len(stations), "unique stations")


def norm_city(s):
    s = str(s).lower().strip()
    s = re.sub(r"\bst\.?\b", "saint", s)
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
print("unmatched:", stations["lat"].isna().sum())
stations = stations.dropna(subset=["lat", "lng"])
print(len(stations), "stations with coordinates")
print(stations[["name", "city", "state", "lat", "lng"]].head(3).to_string())

stations["price"] = stations["price"].round(4)
stations.to_csv(DATA / "stations_geocoded.csv", index=False)
cities[["name", "state", "lat", "lng", "key"]].to_csv(DATA / "us_cities.csv", index=False)
print("wrote data/stations_geocoded.csv and data/us_cities.csv")
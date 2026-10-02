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
print(stations.head(3).to_string())
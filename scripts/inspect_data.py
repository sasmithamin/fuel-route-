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
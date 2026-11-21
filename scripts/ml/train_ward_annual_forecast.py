"""Reproducible ward-level (not 30 m pixel) NDVI forecast for 2026."""
import json
from pathlib import Path

import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder
import joblib

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "data/gee/statistics"
OUT = ROOT / "data/gee/forecast_2026_wards.csv"
ARTIFACT = ROOT / "data/gee/ward_annual_model.joblib"
METRICS = ROOT / "data/gee/ward_annual_model_metrics.json"

def load():
    frames = []
    for year in range(2015, 2026):
        frame = pd.read_csv(SOURCE / f"HCM_NDVI_167_WARDS_{year}.csv")
        frame["year"] = year
        frames.append(frame)
    return pd.concat(frames, ignore_index=True).sort_values(["wardCode", "year"])

def main():
    data = load()
    data["lag1"] = data.groupby("wardCode")["mean"].shift(1)
    data = data.dropna(subset=["lag1"])
    features = ["wardCode", "year", "lag1"]
    pipeline = Pipeline([("encode", ColumnTransformer([("ward", OneHotEncoder(handle_unknown="ignore"), ["wardCode"])], remainder="passthrough")), ("model", Ridge(alpha=1.0))])
    folds = []
    for test_year in range(2020, 2026):
        train, test = data[data.year < test_year], data[data.year == test_year]
        pipeline.fit(train[features], train["mean"])
        predicted = pipeline.predict(test[features])
        baseline = test["lag1"]
        folds.append({"year": test_year, "ridge_mae": mean_absolute_error(test["mean"], predicted), "persistence_mae": mean_absolute_error(test["mean"], baseline)})
    pipeline.fit(data[data.year <= 2025][features], data[data.year <= 2025]["mean"])
    latest = data[data.year == 2025].copy()
    forecast_input = latest[["wardCode"]].assign(year=2026, lag1=latest["mean"].values)
    latest["forecast_mean_ndvi_2026"] = pipeline.predict(forecast_input).clip(-1, 1)
    latest[["wardCode", "ward", "wardType", "geom_km2", "forecast_mean_ndvi_2026"]].to_csv(OUT, index=False)
    joblib.dump(pipeline, ARTIFACT)
    all_actual, all_predicted = [], []
    for test_year in range(2020, 2026):
        train, test = data[data.year < test_year], data[data.year == test_year]
        pipeline.fit(train[features], train["mean"]); all_actual.extend(test["mean"]); all_predicted.extend(pipeline.predict(test[features]))
    payload = {"model": "Ridge ward fixed effects + year + lag-1", "spatial_resolution": "ward-level only", "validation": "expanding walk-forward, test years 2020-2025", "metrics": {"mae": mean_absolute_error(all_actual, all_predicted), "rmse": mean_squared_error(all_actual, all_predicted) ** .5, "r2": r2_score(all_actual, all_predicted)}, "folds": folds, "limitation": "Only 11 annual observations per ward; forecast is experimental and not a 30 m raster."}
    METRICS.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False))

if __name__ == "__main__": main()

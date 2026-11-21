#!/usr/bin/env python3
"""Validate and idempotently import real thermal and ward-forecast artifacts into local PostgreSQL."""
import argparse
import csv
import hashlib
import json
import math
import os
from pathlib import Path
from urllib.parse import urlparse

import psycopg2
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
BOUNDARY_VERSION = "gee_167wards_v1"
THERMAL_FILE = ROOT / "data/gee/statistics/HCM_NDVI_LST_TVDI_167_WARDS_2025.csv"
FORECAST_FILE = ROOT / "data/gee/forecast_2026_wards.csv"
ARTIFACT_FILE = ROOT / "data/gee/ward_annual_model.joblib"
METRICS_FILE = ROOT / "data/gee/ward_annual_model_metrics.json"
MIGRATION_FILE = ROOT / "database/migrations/003_indicator_forecast_statistics.sql"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def local_connection():
    load_dotenv(ROOT / ".env")
    url = os.getenv("DATABASE_URL")
    if url:
        parsed = urlparse(url)
        host, database = parsed.hostname, parsed.path.lstrip("/")
        if host not in {"localhost", "127.0.0.1", "::1"} or database != "ndvi_ai":
            raise RuntimeError("Refusing non-local or unexpected database target")
        return psycopg2.connect(url)
    host = os.getenv("POSTGRES_HOST", "localhost")
    database = os.getenv("POSTGRES_DB", "ndvi_ai")
    if host not in {"localhost", "127.0.0.1", "::1"} or database != "ndvi_ai":
        raise RuntimeError("Refusing non-local or unexpected database target")
    return psycopg2.connect(host=host, port=os.getenv("POSTGRES_PORT", "5432"), database=database,
                            user=os.getenv("POSTGRES_USER", "postgres"), password=os.getenv("POSTGRES_PASSWORD", "postgres"))


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def validate(thermal: list[dict[str, str]], forecast: list[dict[str, str]], db_codes: set[str]) -> None:
    if len(thermal) != 167 or len(forecast) != 167:
        raise ValueError("Thermal and forecast files must each contain 167 rows")
    thermal_codes = {row["wardCode"].strip() for row in thermal}
    forecast_codes = {row["wardCode"].strip() for row in forecast}
    if len(thermal_codes) != 167 or len(forecast_codes) != 167 or thermal_codes != db_codes or forecast_codes != db_codes:
        raise ValueError("wardCode sets do not exactly match administrative_wards")
    for row in thermal:
        if row["year"].strip() != "2025":
            raise ValueError("Thermal year must be 2025")
        ndvi, lst, tvdi = (float(row[key]) for key in ("NDVI_mean", "LST_mean_C", "TVDI_mean"))
        if not all(math.isfinite(value) for value in (ndvi, lst, tvdi)) or not -1 <= ndvi <= 1 or not 0 <= tvdi <= 1:
            raise ValueError(f"Invalid thermal values for {row['wardCode']}")
    for row in forecast:
        value = float(row["forecast_mean_ndvi_2026"])
        if not math.isfinite(value) or not -1 <= value <= 1:
            raise ValueError(f"Invalid forecast value for {row['wardCode']}")


def apply_migration(conn) -> None:
    with conn.cursor() as cursor:
        cursor.execute(MIGRATION_FILE.read_text(encoding="utf-8"))


def import_rows(conn, thermal: list[dict[str, str]], forecast: list[dict[str, str]]) -> dict[str, int]:
    thermal_checksum, forecast_checksum = sha256(THERMAL_FILE), sha256(FORECAST_FILE)
    artifact_checksum, metrics_checksum = sha256(ARTIFACT_FILE), sha256(METRICS_FILE)
    metadata = json.loads(METRICS_FILE.read_text(encoding="utf-8"))
    with conn.cursor() as cursor:
        cursor.execute("SELECT ward_code, id FROM administrative_wards WHERE boundary_version = %s", (BOUNDARY_VERSION,))
        ward_ids = dict(cursor.fetchall())
        cursor.execute(
            """INSERT INTO ndvi_forecast_model_runs (model_name, artifact_checksum, metrics_checksum, source_metadata, validation_strategy, evaluation_period)
               VALUES (%s, %s, %s, %s::jsonb, %s, %s)
               ON CONFLICT (artifact_checksum) DO UPDATE SET metrics_checksum = EXCLUDED.metrics_checksum,
                   source_metadata = EXCLUDED.source_metadata, validation_strategy = EXCLUDED.validation_strategy,
                   evaluation_period = EXCLUDED.evaluation_period
               RETURNING id""",
            (metadata["model"], artifact_checksum, metrics_checksum, json.dumps(metadata), metadata.get("validation"), "2020-2025"),
        )
        model_run_id = cursor.fetchone()[0]
        for row in thermal:
            cursor.execute(
                """INSERT INTO ward_thermal_statistics (ward_id, boundary_version, year, ndvi_mean_source, lst_mean_c, tvdi_mean, source_file, source_workflow, source_checksum)
                   VALUES (%s, %s, 2025, %s, %s, %s, %s, %s, %s)
                   ON CONFLICT (ward_id, boundary_version, year, source_checksum) DO NOTHING""",
                (ward_ids[row["wardCode"].strip()], BOUNDARY_VERSION, float(row["NDVI_mean"]), float(row["LST_mean_C"]), float(row["TVDI_mean"]),
                 THERMAL_FILE.relative_to(ROOT).as_posix(), "HCM_NDVI_LST_TVDI_167_WARDS_2025.csv separate thermal workflow", thermal_checksum),
            )
        for row in forecast:
            cursor.execute(
                """INSERT INTO ward_ndvi_forecasts (ward_id, boundary_version, forecast_year, predicted_ndvi, model_run_id, source_file, source_checksum)
                   VALUES (%s, %s, 2026, %s, %s, %s, %s)
                   ON CONFLICT (ward_id, boundary_version, forecast_year, model_run_id, source_checksum) DO NOTHING""",
                (ward_ids[row["wardCode"].strip()], BOUNDARY_VERSION, float(row["forecast_mean_ndvi_2026"]), model_run_id,
                 FORECAST_FILE.relative_to(ROOT).as_posix(), forecast_checksum),
            )
    return {"thermal_checksum": thermal_checksum, "forecast_checksum": forecast_checksum, "artifact_checksum": artifact_checksum}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply-migration", action="store_true")
    args = parser.parse_args()
    for source in (THERMAL_FILE, FORECAST_FILE, ARTIFACT_FILE, METRICS_FILE):
        if not source.exists():
            raise FileNotFoundError(source)
    conn = local_connection()
    try:
        thermal, forecast = read_rows(THERMAL_FILE), read_rows(FORECAST_FILE)
        with conn.cursor() as cursor:
            cursor.execute("SELECT ward_code FROM administrative_wards WHERE boundary_version = %s", (BOUNDARY_VERSION,))
            db_codes = {row[0] for row in cursor.fetchall()}
        validate(thermal, forecast, db_codes)
        if args.apply_migration:
            conn.rollback()
            conn.autocommit = True
            apply_migration(conn)
            conn.autocommit = False
        result = import_rows(conn, thermal, forecast)
        conn.commit()
        print(json.dumps(result, sort_keys=True))
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()

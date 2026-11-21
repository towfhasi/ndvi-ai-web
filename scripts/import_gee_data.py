#!/usr/bin/env python3
"""Import GEE ward boundaries and NDVI statistics into PostgreSQL/PostGIS.
Reads from data/gee/boundaries/ and data/gee/statistics/. Read-only source files."""
import csv
import hashlib
import json
import os
from pathlib import Path

import psycopg2
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

BOUNDARY_VERSION = "gee_167wards_v1"
GEE_SOURCE = "Local delivered GEE artifacts; export manifest not supplied"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def artifact(path: Path) -> dict:
    return {"path": path.relative_to(PROJECT_ROOT).as_posix(), "sha256": sha256(path)}


def connection():
    url = os.getenv("DATABASE_URL")
    if url:
        return psycopg2.connect(url)
    return psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=os.getenv("POSTGRES_PORT", "5432"),
        database=os.getenv("POSTGRES_DB", "ndvi_ai"),
        user=os.getenv("POSTGRES_USER", "postgres"),
        password=os.getenv("POSTGRES_PASSWORD", "postgres"),
    )


def normalize_ward_type(raw: str) -> str:
    v = raw.strip().lower()
    if v in ("phường", "phuong"):
        return "phuong"
    if v in ("xã", "xa"):
        return "xa"
    return v


def import_boundaries(conn):
    geojson_path = PROJECT_ROOT / "data" / "gee" / "boundaries" / "HCM_167_WARDS_BOUNDARY.geojson"
    with open(geojson_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    inserted = 0
    with conn.cursor() as cur:
        for feat in data["features"]:
            props = feat["properties"]
            ward_code = str(props["wardCode"])
            ward_name = props["ward"]
            ward_type_raw = props["wardType"]
            ward_type = normalize_ward_type(ward_type_raw)
            geom_km2 = float(props["geom_km2"])
            geom_geojson = json.dumps(feat["geometry"])

            # Convert geometry to MultiPolygon via ST_Multi(ST_CollectionExtract(...))
            cur.execute(
                """
                INSERT INTO administrative_wards (
                    ward_code, ward, ward_type, ward_type_raw, geom_km2,
                    geom, boundary_version, boundary_source
                ) VALUES (
                    %s, %s, %s, %s, %s,
                    ST_Multi(ST_CollectionExtract(ST_GeomFromGeoJSON(%s), 3)),
                    %s, %s
                )
                ON CONFLICT (ward_code, boundary_version) DO UPDATE SET
                    ward = EXCLUDED.ward,
                    ward_type = EXCLUDED.ward_type,
                    ward_type_raw = EXCLUDED.ward_type_raw,
                    geom_km2 = EXCLUDED.geom_km2,
                    geom = EXCLUDED.geom,
                    boundary_source = EXCLUDED.boundary_source
                """,
                (ward_code, ward_name, ward_type, ward_type_raw, geom_km2,
                 geom_geojson, BOUNDARY_VERSION, "data/gee/boundaries/HCM_167_WARDS_BOUNDARY.geojson"),
            )
            inserted += 1

    print(f"OK Boundaries: {inserted} wards imported/updated (version={BOUNDARY_VERSION})")


def import_csv_year(conn, year: int):
    csv_path = PROJECT_ROOT / "data" / "gee" / "statistics" / f"HCM_NDVI_167_WARDS_{year}.csv"
    raster_path = PROJECT_ROOT / "data" / "gee" / "rasters" / f"HCM_GEE_NDVI_{year}.tif"
    if not csv_path.exists():
        print(f"SKIP {year}: file not found")
        return 0

    run_key = f"gee_ndvi_{year}_{BOUNDARY_VERSION}"
    if not raster_path.exists():
        raise FileNotFoundError(f"Missing raster: {raster_path}")
    artifacts = [artifact(csv_path), artifact(raster_path)]
    fingerprint = hashlib.sha256(
        json.dumps({"year": year, "boundary_version": BOUNDARY_VERSION, "artifacts": artifacts},
                   sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO ndvi_gee_processing_runs (
                run_key, observation_year, gee_source, gee_image_collection, provenance_status, source_artifacts,
                source_image_ids, period_start, period_end,
                composite_method, reducer_method, ndvi_method_version,
                output_crs, resolution_m, cloud_mask_method, cloud_mask_parameters,
                boundary_version, source_fingerprint,
                processing_started_at, processing_completed_at
            ) VALUES (
                %s, %s, %s, NULL, 'unverified', %s::jsonb,
                '[]'::jsonb, make_date(%s, 1, 1), make_date(%s + 1, 1, 1),
                'unverified_from_delivered_artifact', 'unverified_from_delivered_csv',
                'unverified',
                'EPSG:4326', 30.0, 'unverified',
                '{}'::jsonb,
                %s, %s,
                NULL, NULL
            )
            ON CONFLICT (run_key) DO UPDATE SET
                gee_source = EXCLUDED.gee_source,
                gee_image_collection = EXCLUDED.gee_image_collection,
                provenance_status = EXCLUDED.provenance_status,
                source_artifacts = EXCLUDED.source_artifacts,
                source_image_ids = EXCLUDED.source_image_ids,
                composite_method = EXCLUDED.composite_method,
                reducer_method = EXCLUDED.reducer_method,
                ndvi_method_version = EXCLUDED.ndvi_method_version,
                output_crs = EXCLUDED.output_crs,
                resolution_m = EXCLUDED.resolution_m,
                cloud_mask_method = EXCLUDED.cloud_mask_method,
                cloud_mask_parameters = EXCLUDED.cloud_mask_parameters,
                source_fingerprint = EXCLUDED.source_fingerprint
            RETURNING id
            """,
            (run_key, year, GEE_SOURCE, json.dumps(artifacts), year, year, BOUNDARY_VERSION, fingerprint),
        )
        row = cur.fetchone()
        if row:
            run_id = row[0]
        else:
            cur.execute("SELECT id FROM ndvi_gee_processing_runs WHERE run_key = %s", (run_key,))
            run_id = cur.fetchone()[0]

    count = 0
    with open(csv_path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        with conn.cursor() as cur:
            for row in reader:
                ward_code = str(row["wardCode"])
                # Find ward_id
                cur.execute(
                    "SELECT id FROM administrative_wards WHERE ward_code = %s AND boundary_version = %s",
                    (ward_code, BOUNDARY_VERSION),
                )
                ward_row = cur.fetchone()
                if not ward_row:
                    continue
                ward_id = ward_row[0]

                mean_val = float(row["mean"])
                min_val = float(row["min"])
                max_val = float(row["max"])
                std_val = float(row["stdDev"])
                pixel_count = int(row["count"])

                cur.execute(
                    """
                    INSERT INTO ward_ndvi_statistics (
                        ward_id, processing_run_id, boundary_version, year,
                        mean_ndvi, min_ndvi, max_ndvi, std_dev_ndvi, pixel_count
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (processing_run_id, ward_id) DO UPDATE SET
                        mean_ndvi = EXCLUDED.mean_ndvi,
                        min_ndvi = EXCLUDED.min_ndvi,
                        max_ndvi = EXCLUDED.max_ndvi,
                        std_dev_ndvi = EXCLUDED.std_dev_ndvi,
                        pixel_count = EXCLUDED.pixel_count
                    """,
                    (ward_id, run_id, BOUNDARY_VERSION, year,
                     mean_val, min_val, max_val, std_val, pixel_count),
                )
                count += 1

    print(f"OK {year}: {count} ward statistics imported (run_id={run_id})")
    return count


def validate_sources():
    """Fail before opening a write transaction if delivered files are incomplete."""
    boundary_path = PROJECT_ROOT / "data" / "gee" / "boundaries" / "HCM_167_WARDS_BOUNDARY.geojson"
    with boundary_path.open(encoding="utf-8") as stream:
        features = json.load(stream)["features"]
    codes = [str(feature["properties"]["wardCode"]) for feature in features]
    if len(features) != 167 or len(set(codes)) != 167:
        raise ValueError("Boundary source must contain 167 unique wardCode values")
    for year in range(2015, 2026):
        csv_path = PROJECT_ROOT / "data" / "gee" / "statistics" / f"HCM_NDVI_167_WARDS_{year}.csv"
        with csv_path.open(encoding="utf-8-sig") as stream:
            rows = list(csv.DictReader(stream))
        if len(rows) != 167 or {str(row["wardCode"]) for row in rows} != set(codes):
            raise ValueError(f"{csv_path.name} does not match the 167 boundary codes")
        for row in rows:
            if not (-1 <= float(row["min"]) <= float(row["mean"]) <= float(row["max"]) <= 1 and int(row["count"]) > 0):
                raise ValueError(f"Invalid NDVI statistics in {csv_path.name} for {row['wardCode']}")


def main():
    validate_sources()
    conn = connection()
    try:
        import_boundaries(conn)
        total_stats = 0
        for year in range(2015, 2026):
            total_stats += import_csv_year(conn, year)
        print(f"\nDone. Total ward statistics: {total_stats}")

        # Verify
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM administrative_wards WHERE boundary_version = %s", (BOUNDARY_VERSION,))
            print(f"Wards in DB: {cur.fetchone()[0]}")
            cur.execute("SELECT COUNT(*) FROM ward_ndvi_statistics WHERE boundary_version = %s", (BOUNDARY_VERSION,))
            print(f"Statistics rows: {cur.fetchone()[0]}")
            cur.execute("SELECT COUNT(*) FROM ndvi_gee_processing_runs WHERE boundary_version = %s", (BOUNDARY_VERSION,))
            print(f"Processing runs: {cur.fetchone()[0]}")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()

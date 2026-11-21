import json
import csv
import hashlib
from functools import lru_cache
from pathlib import Path
from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import text
from app.database import SessionLocal

router = APIRouter(tags=["wards"])

BOUNDARY_VERSION = "gee_167wards_v1"
INDICATOR_CSV = Path(__file__).resolve().parents[3] / "data" / "gee" / "statistics" / "HCM_NDVI_LST_TVDI_167_WARDS_2025.csv"


@lru_cache(maxsize=1)
def _thermal_indicator_rows():
    with INDICATOR_CSV.open(encoding="utf-8-sig") as stream:
        return tuple(csv.DictReader(stream))


@router.get("/wards/indicators/2025/csv-legacy", include_in_schema=False)
def ward_indicators_2025(ward_code: str | None = Query(None)):
    if not INDICATOR_CSV.exists():
        raise HTTPException(status_code=503, detail="Dữ liệu đang được cập nhật")
    rows = _thermal_indicator_rows()
    if ward_code is not None:
        rows = [row for row in rows if row["wardCode"] == ward_code]
        if not rows:
            raise HTTPException(status_code=404, detail="Không tìm thấy xã/phường")
    return [{"ward_code": row["wardCode"], "ward": row["ward"], "ndvi_mean_source": float(row["NDVI_mean"]), "lst_mean_c": float(row["LST_mean_C"]), "tvdi_mean": float(row["TVDI_mean"]), "source": "HCM_NDVI_LST_TVDI_167_WARDS_2025.csv (separate thermal workflow)"} for row in rows]


@lru_cache(maxsize=1)
def _thermal_source_checksum() -> str:
    digest = hashlib.sha256()
    with INDICATOR_CSV.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


@router.get("/wards/indicators/2025")
def ward_indicators_2025_postgres(ward_code: str | None = Query(None)):
    if not INDICATOR_CSV.exists():
        raise HTTPException(status_code=503, detail="Thermal source artifact is unavailable")
    params = {"checksum": _thermal_source_checksum(), "bv": BOUNDARY_VERSION}
    sql = """
        SELECT w.ward_code, w.ward, t.ndvi_mean_source, t.lst_mean_c, t.tvdi_mean,
               t.source_file || ' (separate thermal workflow)' AS source
        FROM ward_thermal_statistics t
        JOIN administrative_wards w ON w.id = t.ward_id AND w.boundary_version = t.boundary_version
        WHERE t.year = 2025 AND t.boundary_version = :bv AND t.source_checksum = :checksum
    """
    if ward_code is not None:
        sql += " AND w.ward_code = :ward_code"
        params["ward_code"] = ward_code
    sql += " ORDER BY w.ward_code"
    with SessionLocal() as db:
        rows = db.execute(text(sql), params).mappings().all()
    if ward_code is not None and not rows:
        raise HTTPException(status_code=404, detail="Ward or thermal statistics not found")
    if ward_code is None and len(rows) != 167:
        raise HTTPException(status_code=503, detail="Thermal PostgreSQL dataset is unavailable or incomplete")
    return [dict(row) for row in rows]


@router.get("/wards/statistics")
def all_wards_statistics(year: int = Query(..., ge=2015, le=2025)):
    with SessionLocal() as db:
        rows = db.execute(
            text("""
                SELECT w.ward_code, w.ward, w.ward_type, w.geom_km2,
                       s.mean_ndvi, s.min_ndvi, s.max_ndvi, s.std_dev_ndvi, s.pixel_count
                FROM ward_ndvi_statistics s
                JOIN administrative_wards w ON w.id = s.ward_id AND w.boundary_version = s.boundary_version
                WHERE s.year = :year AND s.boundary_version = :bv
                ORDER BY w.ward_code
            """), {"year": year, "bv": BOUNDARY_VERSION}
        ).mappings().all()
    return [dict(row) for row in rows]


@router.get("/wards")
def list_wards():
    with SessionLocal() as db:
        rows = db.execute(
            text("""
                SELECT ward_code, ward, ward_type, geom_km2
                FROM administrative_wards
                WHERE boundary_version = :bv
                ORDER BY ward_code
            """),
            {"bv": BOUNDARY_VERSION},
        ).mappings().all()
    return [dict(r) for r in rows]


@router.get("/wards/geojson")
def wards_geojson(web: bool = Query(False)):
    if web:
        path = Path(__file__).resolve().parents[3] / "data" / "gee" / "boundaries" / "HCM_167_WARDS_BOUNDARY_WEB.geojson"
        if not path.exists():
            raise HTTPException(status_code=404, detail="Optimized ward boundary is unavailable")
        return json.loads(path.read_text(encoding="utf-8"))
    with SessionLocal() as db:
        row = db.execute(
            text("""
                SELECT json_build_object(
                    'type', 'FeatureCollection',
                    'features', json_agg(
                        json_build_object(
                            'type', 'Feature',
                            'geometry', ST_AsGeoJSON(geom)::json,
                            'properties', json_build_object(
                                'wardCode', ward_code,
                                'ward', ward,
                                'wardType', ward_type,
                                'geom_km2', geom_km2
                            )
                        )
                    )
                ) AS geojson
                FROM administrative_wards
                WHERE boundary_version = :bv
            """),
            {"bv": BOUNDARY_VERSION},
        ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Chưa có dữ liệu ranh giới")
    return json.loads(row) if isinstance(row, str) else row


@router.get("/wards/{ward_code}")
def get_ward(ward_code: str):
    with SessionLocal() as db:
        row = db.execute(
            text("""
                SELECT ward_code, ward, ward_type, ward_type_raw, geom_km2,
                       boundary_version, boundary_source
                FROM administrative_wards
                WHERE ward_code = :wc AND boundary_version = :bv
            """),
            {"wc": ward_code, "bv": BOUNDARY_VERSION},
        ).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="Không tìm thấy xã/phường")
    return dict(row)


@router.get("/wards/{ward_code}/statistics")
def ward_statistics(ward_code: str, year: int = Query(None)):
    with SessionLocal() as db:
        row = db.execute(
            text("SELECT id FROM administrative_wards WHERE ward_code = :wc AND boundary_version = :bv"),
            {"wc": ward_code, "bv": BOUNDARY_VERSION},
        ).mappings().first()
        if not row:
            raise HTTPException(status_code=404, detail="Không tìm thấy xã/phường")
        ward_id = row["id"]

        sql = """
            SELECT s.year, s.mean_ndvi, s.min_ndvi, s.max_ndvi, s.std_dev_ndvi, s.pixel_count,
                   r.gee_source, r.composite_method, r.ndvi_method_version, r.output_crs, r.resolution_m
            FROM ward_ndvi_statistics s
            JOIN ndvi_gee_processing_runs r ON r.id = s.processing_run_id
            WHERE s.ward_id = :wid AND s.boundary_version = :bv
        """
        params = {"wid": ward_id, "bv": BOUNDARY_VERSION}
        if year is not None:
            sql += " AND s.year = :year"
            params["year"] = year
        sql += " ORDER BY s.year"

        rows = db.execute(text(sql), params).mappings().all()
    return [dict(r) for r in rows]


@router.get("/wards/{ward_code}/timeseries")
def ward_timeseries(ward_code: str):
    with SessionLocal() as db:
        row = db.execute(
            text("SELECT id FROM administrative_wards WHERE ward_code = :wc AND boundary_version = :bv"),
            {"wc": ward_code, "bv": BOUNDARY_VERSION},
        ).mappings().first()
        if not row:
            raise HTTPException(status_code=404, detail="Không tìm thấy xã/phường")
        ward_id = row["id"]

        rows = db.execute(
            text("""
                SELECT year, mean_ndvi
                FROM ward_ndvi_statistics
                WHERE ward_id = :wid AND boundary_version = :bv
                ORDER BY year
            """),
            {"wid": ward_id, "bv": BOUNDARY_VERSION},
        ).mappings().all()
    return {
        "ward_code": ward_code,
        "data": [{"date": str(r["year"]), "value": float(r["mean_ndvi"])} for r in rows],
    }



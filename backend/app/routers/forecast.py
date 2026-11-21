from pathlib import Path
import csv
import hashlib
import json
import zipfile
from functools import lru_cache

from fastapi import APIRouter, HTTPException, Response
from app.config import settings
from app.database import SessionLocal
from sqlalchemy import text

router = APIRouter(tags=["forecast"])
ZIP_PATH = Path(settings.SOURCE_DATA_DIR) / "HCM_NDVI_Forecast_Maps_2026.zip"
WARD_FORECAST_PATH = Path(settings.GEE_RASTER_DIR).parent / "forecast_2026_wards.csv"
WARD_METRICS_PATH = Path(settings.GEE_RASTER_DIR).parent / "ward_annual_model_metrics.json"


@lru_cache(maxsize=2)
def _sha256(path: str) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()

def _forecast_rows():
    if not ZIP_PATH.exists():
        raise HTTPException(status_code=503, detail="Không tìm thấy file dự báo nguồn")
    with zipfile.ZipFile(ZIP_PATH) as archive:
        with archive.open("HCM_NDVI_Forecast_2026.csv") as stream:
            return list(csv.DictReader(line.decode("utf-8-sig") for line in stream))

@router.get("/forecast/2026")
def forecast_2026():
    rows = _forecast_rows()
    months = [f"{int(row['year']):04d}-{int(row['month']):02d}" for row in rows]
    values = [float(row["NDVI_forecast"]) for row in rows]
    return {"model": "Random Forest", "forecast_period": "2026", "values": values, "months": months,
            "statistics": {"min": min(values), "max": max(values), "mean": sum(values) / len(values)},
            "status": "reference_results",
            "source_note": "Kết quả tham chiếu từ bộ dữ liệu và mô hình do giảng viên cung cấp"}

@router.get("/models")
def models():
    return ["Random Forest", "Extra Trees", "HistGradientBoosting", "Seasonal Naive"]

@router.get("/models/metrics")
def model_metrics():
    if not WARD_METRICS_PATH.exists():
        return []
    with SessionLocal() as db:
        row = db.execute(text("""
            SELECT model_name, source_metadata
            FROM ndvi_forecast_model_runs
            WHERE artifact_checksum = :checksum
        """), {"checksum": _sha256(str(WARD_FORECAST_PATH.parent / "ward_annual_model.joblib"))}).mappings().first()
    if not row:
        raise HTTPException(status_code=503, detail="Forecast model metrics are not imported into PostgreSQL")
    return [{"model_name": row["model_name"], **row["source_metadata"]["metrics"]}]

@router.get("/forecast/2026/wards/csv-legacy", include_in_schema=False)
def ward_forecast_2026():
    if not WARD_FORECAST_PATH.exists() or not WARD_METRICS_PATH.exists():
        raise HTTPException(status_code=503, detail="Ward forecast artifact is not available")
    with WARD_FORECAST_PATH.open(encoding="utf-8-sig") as stream:
        rows = list(csv.DictReader(stream))
    return {"status": "experimental", "metadata": json.loads(WARD_METRICS_PATH.read_text(encoding="utf-8")), "data": rows}


@router.get("/forecast/2026/wards")
def ward_forecast_2026_postgres():
    if not WARD_FORECAST_PATH.exists() or not WARD_METRICS_PATH.exists():
        raise HTTPException(status_code=503, detail="Ward forecast source artifact is unavailable")
    with SessionLocal() as db:
        model = db.execute(text("""
            SELECT id, source_metadata FROM ndvi_forecast_model_runs
            WHERE artifact_checksum = :checksum
        """), {"checksum": _sha256(str(WARD_FORECAST_PATH.parent / "ward_annual_model.joblib"))}).mappings().first()
        if not model:
            raise HTTPException(status_code=503, detail="Ward forecast model is not imported into PostgreSQL")
        rows = db.execute(text("""
            SELECT w.ward_code AS "wardCode", w.ward, w.ward_type AS "wardType", w.geom_km2,
                   f.predicted_ndvi AS forecast_mean_ndvi_2026
            FROM ward_ndvi_forecasts f
            JOIN administrative_wards w ON w.id = f.ward_id AND w.boundary_version = f.boundary_version
            WHERE f.forecast_year = 2026 AND f.model_run_id = :model_run_id
              AND f.source_checksum = :source_checksum
            ORDER BY w.ward_code
        """), {"model_run_id": model["id"], "source_checksum": _sha256(str(WARD_FORECAST_PATH))}).mappings().all()
    if len(rows) != 167:
        raise HTTPException(status_code=503, detail="Ward forecast PostgreSQL dataset is unavailable or incomplete")
    return {"status": "experimental", "metadata": model["source_metadata"], "data": [dict(row) for row in rows]}

@router.get("/forecast/2026/maps/{month}.png")
def forecast_map(month: int):
    if month < 1 or month > 12:
        raise HTTPException(status_code=400, detail="Month phải nằm trong khoảng 1-12")
    filename = f"HCM_NDVI_Forecast_2026_M{month:02d}.png"
    with zipfile.ZipFile(ZIP_PATH) as archive:
        try:
            content = archive.read(filename)
        except KeyError:
            raise HTTPException(status_code=404, detail="Không tìm thấy bản đồ dự báo tháng")
    return Response(content=content, media_type="image/png", headers={"Cache-Control": "public, max-age=86400"})

@router.get("/forecast/2026/maps")
def forecast_maps():
    return [{"month": month, "label": f"Tháng {month:02d}", "url": f"/api/forecast/2026/maps/{month}.png"} for month in range(1, 13)]

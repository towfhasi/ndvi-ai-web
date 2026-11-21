from pathlib import Path
import io
import math
import threading
import numpy as np
import rasterio
from PIL import Image
from rasterio.enums import Resampling
from rasterio.warp import transform, transform_bounds
from rasterio.windows import from_bounds
from fastapi import APIRouter, HTTPException, Response
from app.config import settings

router = APIRouter(tags=["tiles"])
DATA_ROOT = Path(settings.GEE_RASTER_DIR)
FILES = {f"ndvi_{year}": f"HCM_GEE_NDVI_{year}.tif" for year in range(2015, 2026)}
FILES.update({"lst_2025": "HCM_LST_2025.tif", "tvdi_2025": "HCM_TVDI_2025.tif"})
TILE_SEMAPHORE = threading.BoundedSemaphore(2)

# Display ranges and palettes follow bin/Thang màu LST-NDVI-TVDI.pdf.
DISPLAY_SCALES = {
    "lst": (20.0, 45.0, ((0, 0, 255), (0, 102, 255), (0, 255, 255), (0, 255, 0), (255, 255, 0), (255, 204, 0), (255, 102, 0), (255, 0, 0))),
    "ndvi": (-0.2, 1.0, ((255, 0, 0), (255, 127, 0), (255, 255, 0), (173, 255, 47), (0, 255, 0), (0, 255, 255), (0, 127, 255), (0, 0, 255))),
    "tvdi": (0.0, 1.0, ((6, 107, 0), (11, 196, 0), (12, 225, 0), (0, 255, 0), (255, 255, 0), (255, 204, 0), (255, 102, 0), (255, 0, 0))),
}
VALUE_RANGES = {"lst": (-100.0, 150.0), "ndvi": (-1.0, 1.0), "tvdi": (0.0, 1.0)}


def _indicator(dataset_id: str) -> str:
    return "lst" if dataset_id.startswith("lst_") else "tvdi" if dataset_id.startswith("tvdi_") else "ndvi"


def _palette_rgba(values: np.ndarray, valid: np.ndarray, indicator: str) -> np.ndarray:
    low, high, colors = DISPLAY_SCALES[indicator]
    palette = np.asarray(colors, dtype=np.float32)
    positions = np.clip((np.where(valid, values, low) - low) / (high - low), 0, 1) * (len(palette) - 1)
    lower = np.floor(positions).astype(np.intp)
    upper = np.minimum(lower + 1, len(palette) - 1)
    fraction = (positions - lower)[..., None]
    rgba = np.zeros((*values.shape, 4), dtype=np.uint8)
    rgba[..., :3] = np.rint(palette[lower] * (1 - fraction) + palette[upper] * fraction).astype(np.uint8)
    rgba[..., 3] = (valid * 210).astype(np.uint8)
    return rgba

def _tile_bounds(x: int, y: int, z: int):
    n = 2 ** z
    west, east = x / n * 360 - 180, (x + 1) / n * 360 - 180
    north = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / n))))
    south = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * (y + 1) / n))))
    return west, south, east, north


def _read_tile(path: Path, bounds):
    west, south, east, north = bounds
    with rasterio.open(path) as src:
        if src.crs and not src.crs.is_geographic:
            west, south, east, north = transform_bounds(
                "EPSG:4326", src.crs, west, south, east, north
            )
        window = from_bounds(west, south, east, north, src.transform)
        return src.read(
            1,
            window=window,
            out_shape=(256, 256),
            boundless=True,
            masked=True,
            resampling=Resampling.bilinear,
        ).filled(np.nan).astype("float32")

def _render_tile(dataset_id: str, z: int, x: int, y: int):
    filename = FILES.get(dataset_id)
    if filename is None:
        raise HTTPException(status_code=404, detail="Dataset không tồn tại")
    if not (DATA_ROOT / filename).exists():
        raise HTTPException(status_code=503, detail="Dữ liệu đang được cập nhật")
    bounds = _tile_bounds(x, y, z)
    destination = _read_tile(DATA_ROOT / filename, bounds)
    indicator = _indicator(dataset_id)
    valid_low, valid_high = VALUE_RANGES[indicator]
    valid = np.isfinite(destination) & (destination >= valid_low) & (destination <= valid_high)
    rgba = _palette_rgba(destination, valid, indicator) if valid.any() else np.zeros((256, 256, 4), dtype=np.uint8)
    buffer = io.BytesIO()
    Image.fromarray(rgba, "RGBA").save(buffer, format="PNG", optimize=True)
    return Response(content=buffer.getvalue(), media_type="image/png", headers={"Cache-Control": "public, max-age=3600"})


@router.get("/tiles/{dataset_id}/{z}/{x}/{y}.png")
def tile(dataset_id: str, z: int, x: int, y: int):
    with TILE_SEMAPHORE, rasterio.Env(GDAL_CACHEMAX=16, GDAL_NUM_THREADS="1"):
        return _render_tile(dataset_id, z, x, y)


@router.get("/tiles/{dataset_id}/pixel")
def pixel(dataset_id: str, lat: float, lng: float):
    filename = FILES.get(dataset_id)
    if filename is None:
        raise HTTPException(status_code=404, detail="Dataset does not exist")
    if not (DATA_ROOT / filename).exists():
        raise HTTPException(status_code=503, detail="Dữ liệu đang được cập nhật")
    with rasterio.open(DATA_ROOT / filename) as src:
        x, y = transform("EPSG:4326", src.crs, [lng], [lat]) if src.crs and not src.crs.is_geographic else ([lng], [lat])
        row, col = src.index(x[0], y[0])
        if not (0 <= row < src.height and 0 <= col < src.width):
            raise HTTPException(status_code=404, detail="Point is outside raster")
        value = float(src.read(1, window=((row, row + 1), (col, col + 1)))[0, 0])
        nodata = src.nodata
    low, high = VALUE_RANGES[_indicator(dataset_id)]
    is_nodata = nodata is not None and math.isclose(value, float(nodata))
    return {"lat": lat, "lng": lng, "value": value if math.isfinite(value) and not is_nodata and low <= value <= high else None}


@router.get("/indicators/2025")
def indicators_2025():
    return {key: {"available": (DATA_ROOT / filename).exists()} for key, filename in FILES.items() if key in ("lst_2025", "tvdi_2025")}

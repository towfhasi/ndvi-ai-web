import { useEffect, useState } from 'react';
import { GeoJSON, MapContainer, TileLayer, useMap } from 'react-leaflet';
import type { GeoJsonObject } from 'geojson';
import 'leaflet/dist/leaflet.css';

const PALETTE_VERSION = '20261012';
const extent: [[number, number], [number, number]] = [[10.32, 106.33], [11.50, 107.57]];
function FitExtent() { const map = useMap(); useEffect(() => { map.fitBounds(extent, { padding: [6, 6] }); }, [map]); return null; }
export function MapPreview() {
  const [wards, setWards] = useState<GeoJsonObject>(); const [tileError, setTileError] = useState(false);
  useEffect(() => { fetch('/api/wards/geojson?web=true').then(r => r.ok ? r.json() : Promise.reject()).then(setWards).catch(() => undefined); }, []);
  return <div className="relative h-64 overflow-hidden rounded-lg bg-gray-100"><MapContainer center={[10.8, 106.7]} zoom={10} zoomControl={false} attributionControl={false} className="h-full w-full"><TileLayer url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" /><TileLayer url={`/api/tiles/ndvi_2025/{z}/{x}/{y}.png?palette=${PALETTE_VERSION}`} opacity={0.8} eventHandlers={{ tileerror: () => setTileError(true) }} />{wards && <GeoJSON data={wards} style={{ color: '#334155', weight: 1, fillOpacity: 0 }} />}<FitExtent /></MapContainer>{tileError && <div className="absolute inset-0 flex items-center justify-center bg-white/90 p-4 text-center text-sm text-red-700">Không tải được NDVI preview. Vui lòng xem bản đồ chi tiết.</div>}<div className="pointer-events-none absolute bottom-2 left-2 rounded bg-white/90 px-2 py-1 text-xs text-gray-700">NDVI năm 2025 — Google Earth Engine</div></div>;
}

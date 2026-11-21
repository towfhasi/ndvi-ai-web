import { useEffect, useRef, useState } from 'react';
import { GeoJSON, MapContainer, TileLayer, useMap, useMapEvents } from 'react-leaflet';
import { DomEvent, type Map as LeafletMap } from 'leaflet';
import 'leaflet/dist/leaflet.css';

interface Props { datasetId: string; selectedWardCode?: string; onPixelClick?: (lat: number, lng: number, value: number | null) => void; onWardClick?: (code: string) => void; syncId?: string; }
const PALETTE_VERSION = '20261012';
const extent: [[number, number], [number, number]] = [[10.32, 106.33], [11.50, 107.57]];
const normal = { color: '#334155', weight: 1, fillOpacity: 0 };
const hover = { color: '#f59e0b', weight: 3, fillColor: '#fbbf24', fillOpacity: 0.12 };
const selected = { color: '#0891b2', weight: 4, fillColor: '#22d3ee', fillOpacity: 0.2 };
const syncMaps: Record<string, LeafletMap[]> = {}; let syncing = false;
function ResetControl() { const map = useMap(); return <button onClick={() => map.fitBounds(extent)} className="absolute top-3 left-3 z-[1000] bg-white rounded shadow px-3 py-2 text-sm">Reset extent</button>; }
function MapSizeInvalidator() { const map = useMap(); useEffect(() => { const observer = new ResizeObserver(() => map.invalidateSize({ pan: false })); observer.observe(map.getContainer()); return () => observer.disconnect(); }, [map]); return null; }
function ClickHandler({ datasetId, onPixelClick }: Props) { useMapEvents({ click: async e => { if (!onPixelClick) return; try { const r = await fetch(`/api/tiles/${datasetId}/pixel?lat=${e.latlng.lat}&lng=${e.latlng.lng}`); const v = await r.json(); onPixelClick(e.latlng.lat, e.latlng.lng, r.ok ? v.value : null); } catch { onPixelClick(e.latlng.lat, e.latlng.lng, null); } } }); return null; }
function SyncController({ syncId }: { syncId?: string }) { const map = useMap(); useEffect(() => { if (!syncId) return; const group = syncMaps[syncId] ?? (syncMaps[syncId] = []); group.push(map); const move = () => { if (syncing) return; syncing = true; group.filter(x => x !== map).forEach(x => x.setView(map.getCenter(), map.getZoom(), { animate: false })); setTimeout(() => syncing = false); }; map.on('moveend', move); return () => { map.off('moveend', move); group.splice(group.indexOf(map), 1); }; }, [map, syncId]); return null; }
export function MapViewer({ datasetId, selectedWardCode, onPixelClick, onWardClick, syncId }: Props) {
  const [opacity, setOpacity] = useState(0.8); const [wards, setWards] = useState<any>(); const geoRef = useRef<any>(); const selectedRef = useRef(selectedWardCode);
  selectedRef.current = selectedWardCode;
  useEffect(() => { fetch('/api/wards/geojson').then(r => r.ok ? r.json() : undefined).then(setWards).catch(() => undefined); }, []);
  useEffect(() => { geoRef.current?.eachLayer((layer: any) => { const code = String(layer.feature?.properties?.wardCode); layer.setStyle(code === selectedWardCode ? selected : normal); if (code === selectedWardCode) layer.bringToFront(); }); }, [selectedWardCode, wards]);
  return <div className="relative h-full w-full"><div className="absolute top-3 right-3 z-[1000] bg-white p-3 rounded shadow text-sm"><label>Raster opacity: {Math.round(opacity * 100)}%</label><input aria-label="Raster opacity" type="range" min="0" max="100" value={opacity * 100} onChange={e => setOpacity(Number(e.target.value) / 100)} className="block w-32" /></div><MapContainer center={[10.8, 106.7]} zoom={10} className="h-full w-full"><TileLayer url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" attribution="&copy; OpenStreetMap contributors" /><TileLayer url={`/api/tiles/${datasetId}/{z}/{x}/{y}.png?palette=${PALETTE_VERSION}`} opacity={opacity} />{wards && <GeoJSON ref={geoRef} data={wards} style={normal} onEachFeature={(f, layer: any) => { const code = String(f.properties.wardCode); layer.on({ mouseover: () => { if (selectedRef.current !== code) layer.setStyle(hover); }, mouseout: () => layer.setStyle(selectedRef.current === code ? selected : normal), click: (event: any) => { DomEvent.stopPropagation(event); onWardClick?.(code); layer.setStyle(selected); layer.bringToFront(); } }); }} />}<ResetControl /><MapSizeInvalidator /><SyncController syncId={syncId} /><ClickHandler datasetId={datasetId} onPixelClick={onPixelClick} /></MapContainer></div>;
}
export default MapViewer;

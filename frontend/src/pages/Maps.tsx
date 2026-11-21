import { useEffect, useMemo, useRef, useState } from 'react';
import { Card } from '../components/common/Card';
import { Legend } from '../components/map/Legend';
import { MapViewer } from '../components/map/MapViewer';
import { WardNdviTrendChart } from '../components/charts/WardNdviTrendChart';
import { api } from '../api/client';
import type { Dataset, TimeSeries } from '../types';

type Indicator = 'ndvi' | 'lst' | 'tvdi';
type Ward = { ward_code: string; ward: string; geom_km2: number; ward_type?: string };
type WardStat = { year: number; mean_ndvi: number; min_ndvi?: number; max_ndvi?: number; std_dev_ndvi?: number; pixel_count?: number; gee_source?: string };
type Thermal = { ward_code: string; ndvi_mean_source: number; lst_mean_c: number; tvdi_mean: number; source: string };
const ndviYears = Array.from({ length: 11 }, (_, index) => 2015 + index);
const number = (value: number | undefined, digits = 4) => value === undefined || value === null ? 'Chưa có dữ liệu' : new Intl.NumberFormat('vi-VN', { maximumFractionDigits: digits, minimumFractionDigits: digits }).format(value);

function dataset(indicator: Indicator, year: number): Dataset {
  const name = indicator === 'ndvi' ? `NDVI ${year}` : indicator === 'lst' ? 'LST 2025' : 'TVDI 2025';
  return { id: `${indicator}_${year}`, name, type: 'ndvi_2025', year, resolution: 'GEE', crs: 'EPSG:4326', source: 'Google Earth Engine', dimensions: { width: 0, height: 0 }, bounds: { minLat: 10.32, maxLat: 11.5, minLng: 106.33, maxLng: 107.57 } };
}

export default function Maps() {
  const [indicator, setIndicator] = useState<Indicator>('ndvi');
  const [year, setYear] = useState(2025);
  const [lastNdviYear, setLastNdviYear] = useState(2025);
  const [compare, setCompare] = useState(false);
  const [wards, setWards] = useState<Ward[]>([]);
  const [query, setQuery] = useState('');
  const [selectedCode, setSelectedCode] = useState<string>();
  const [ward, setWard] = useState<Ward>();
  const [stats, setStats] = useState<WardStat[]>([]);
  const [series, setSeries] = useState<TimeSeries>();
  const [thermal, setThermal] = useState<Thermal>();
  const [panelState, setPanelState] = useState<'idle' | 'loading' | 'error'>('idle');
  const [pixel, setPixel] = useState<{ lat: number; lng: number; value: number | null }>();
  const request = useRef(0);

  useEffect(() => { fetch('/api/wards').then(response => response.ok ? response.json() : []).then(setWards).catch(() => setWards([])); }, []);
  const matches = useMemo(() => query.trim() ? wards.filter(item => `${item.ward} ${item.ward_code}`.toLocaleLowerCase('vi').includes(query.trim().toLocaleLowerCase('vi'))).slice(0, 8) : [], [query, wards]);
  const currentDataset = useMemo(() => dataset(indicator, year), [indicator, year]);
  const current = stats.find(item => item.year === (indicator === 'ndvi' ? year : 2025));

  const selectWard = async (wardCode: string) => {
    const id = ++request.current;
    setSelectedCode(wardCode); setQuery(''); setPanelState('loading'); setPixel(undefined);
    try {
      const [wardResponse, statisticsResponse, seriesResponse, thermalResponse] = await Promise.all([
        fetch(`/api/wards/${encodeURIComponent(wardCode)}`),
        fetch(`/api/wards/${encodeURIComponent(wardCode)}/statistics`),
        fetch(`/api/wards/${encodeURIComponent(wardCode)}/timeseries`),
        api.getWardIndicators2025(wardCode),
      ]);
      if (id !== request.current) return;
      if (!wardResponse.ok || !statisticsResponse.ok || !seriesResponse.ok) throw new Error('ward request failed');
      setWard(await wardResponse.json()); setStats(await statisticsResponse.json()); setSeries(await seriesResponse.json()); setThermal(thermalResponse[0]); setPanelState('idle');
    } catch { if (id === request.current) { setPanelState('error'); setThermal(undefined); } }
  };
  const changeIndicator = (next: Indicator) => { setIndicator(next); setYear(next === 'ndvi' ? lastNdviYear : 2025); if (next !== 'ndvi') setCompare(false); };
  const changeYear = (next: number) => { setYear(next); if (indicator === 'ndvi') setLastNdviYear(next); };
  const clearSelection = () => { request.current++; setSelectedCode(undefined); setWard(undefined); setStats([]); setSeries(undefined); setThermal(undefined); };
  const mapProps = { selectedWardCode: selectedCode, onWardClick: selectWard, onPixelClick: (lat: number, lng: number, value: number | null) => setPixel({ lat, lng, value }) };

  return <div className="space-y-5">
    <Card title="Bản đồ NDVI">
      <div className="flex flex-wrap items-center gap-3">
        <select aria-label="Chỉ số" className="border rounded px-3 py-2" value={indicator} onChange={event => changeIndicator(event.target.value as Indicator)}><option value="ndvi">NDVI</option><option value="lst">LST</option><option value="tvdi">TVDI</option></select>
        <select aria-label="Năm" className="border rounded px-3 py-2" value={year} onChange={event => changeYear(Number(event.target.value))}>{(indicator === 'ndvi' ? ndviYears : [2025]).map(item => <option key={item} value={item}>{item}</option>)}</select>
        <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={compare} disabled={indicator !== 'ndvi'} onChange={event => setCompare(event.target.checked)} /> So sánh 2015 ↔ 2025</label>
        <div className="relative"><input value={query} onChange={event => setQuery(event.target.value)} placeholder="Tìm tên hoặc mã xã/phường" className="w-full border rounded px-3 py-2" aria-label="Tìm tên hoặc mã xã/phường" />{matches.length > 0 && <div className="absolute z-[1100] mt-1 w-full min-w-[280px] rounded border bg-white shadow-lg">{matches.map(item => <button type="button" className="block w-full px-3 py-2 text-left text-sm hover:bg-cyan-50" key={item.ward_code} onClick={() => selectWard(item.ward_code)}>{item.ward} ({item.ward_code})</button>)}</div>}</div>
      </div>
      {indicator !== 'ndvi' && <p className="mt-3 text-sm text-slate-600">{indicator === 'lst' ? 'LST hiển thị theo °C; giới hạn màu là giới hạn hiển thị, không phải kết luận toàn bộ dữ liệu.' : 'TVDI là chỉ số khô hạn tương đối, không phải phép đo độ ẩm đất trực tiếp.'}</p>}
      <div className="mt-4 grid items-stretch gap-4 lg:grid-cols-[minmax(0,7fr)_minmax(20rem,3fr)]">
        <section className="relative h-[540px] min-w-0 lg:h-[575px]">
          <div className={`grid h-full gap-4 ${compare ? 'lg:grid-cols-2' : 'grid-cols-1'}`}><div className="min-h-0 overflow-hidden rounded-lg border"><MapViewer datasetId={compare ? 'ndvi_2015' : currentDataset.id} syncId={compare ? 'compare' : undefined} {...mapProps} /></div>{compare && <div className="min-h-0 overflow-hidden rounded-lg border"><MapViewer datasetId="ndvi_2025" syncId="compare" {...mapProps} /></div>}</div>
          <div className="absolute bottom-3 left-3 z-[1000] max-w-[calc(100%-1.5rem)]"><Legend dataset={currentDataset} /></div>
          {pixel && <div className="absolute bottom-3 right-3 z-[1000] max-w-[calc(100%-1.5rem)] rounded-lg bg-white/95 p-3 text-sm shadow"><strong>Pixel đã chọn</strong><div>{pixel.value === null ? 'Không có dữ liệu tại vị trí này' : `${number(pixel.value)}${indicator === 'lst' ? ' °C' : ''}`}</div><div className="text-slate-500">{number(pixel.lat, 5)}, {number(pixel.lng, 5)}</div></div>}
        </section>
        <aside className="h-[540px] overflow-y-auto rounded-lg border border-gray-200 bg-white shadow-sm lg:h-[575px]">
          <div className="sticky top-0 z-10 border-b border-gray-200 bg-white px-5 py-4"><h3 className="text-lg font-semibold text-gray-800">Thuộc tính xã/phường</h3></div>
          <div className="space-y-4 p-5">
            {!selectedCode && <p className="text-sm text-slate-600">Chọn một xã/phường trên bản đồ hoặc từ ô tìm kiếm để xem thống kê.</p>}
            {selectedCode && panelState === 'loading' && <p className="text-sm text-slate-600">Đang tải dữ liệu xã/phường...</p>}
            {selectedCode && panelState === 'error' && <p className="text-sm text-red-600">Không tải được dữ liệu xã/phường. Vui lòng thử lại.</p>}
            {ward && panelState === 'idle' && <><div className="flex items-start justify-between gap-3"><div><h4 className="font-semibold text-slate-800">{ward.ward}</h4><p className="text-sm text-slate-500">Mã hành chính: {ward.ward_code}</p><p className="text-sm text-slate-600">Diện tích: {new Intl.NumberFormat('vi-VN', { maximumFractionDigits: 2 }).format(ward.geom_km2)} km²</p></div><button type="button" className="rounded border px-3 py-1 text-sm" onClick={clearSelection}>Xóa lựa chọn</button></div>
              <div className="grid grid-cols-2 gap-2"><div className="rounded bg-slate-50 p-2.5"><div className="text-xs text-slate-500">NDVI TB ({indicator === 'ndvi' ? year : 2025})</div><strong>{number(current?.mean_ndvi)}</strong></div><div className="rounded bg-slate-50 p-2.5"><div className="text-xs text-slate-500">NDVI min / max</div><strong>{number(current?.min_ndvi)} / {number(current?.max_ndvi)}</strong></div><div className="rounded bg-slate-50 p-2.5"><div className="text-xs text-slate-500">Độ lệch chuẩn</div><strong>{number(current?.std_dev_ndvi)}</strong></div><div className="rounded bg-slate-50 p-2.5"><div className="text-xs text-slate-500">Pixel hợp lệ</div><strong>{current?.pixel_count?.toLocaleString('vi-VN') ?? 'Chưa có dữ liệu'}</strong></div><div className="col-span-2 rounded bg-cyan-50 p-2.5"><div className="text-xs text-slate-500">LST 2025 / TVDI 2025</div><strong>{number(thermal?.lst_mean_c, 2)} °C / {number(thermal?.tvdi_mean)}</strong></div></div>
              <p className="text-xs text-slate-500">NDVI dùng workflow chính. LST/TVDI dùng CSV thermal 2025 riêng; NDVI thermal không thay thế chuỗi NDVI chính.</p>
              <div><h5 className="mb-1 text-sm font-medium text-slate-700">Biến động NDVI 2015–2025</h5>{series ? <WardNdviTrendChart data={series} activeYear={indicator === 'ndvi' ? year : 2025} /> : <p className="text-sm text-slate-500">Chưa có chuỗi NDVI.</p>}</div>
            </>}
          </div>
        </aside>
      </div>
    </Card>
  </div>;
}

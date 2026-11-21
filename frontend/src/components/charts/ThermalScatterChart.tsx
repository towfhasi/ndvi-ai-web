import { useEffect, useRef } from 'react';
import * as echarts from 'echarts';

export type ThermalIndicator = { ward_code: string; ward: string; ndvi_mean_source: number; lst_mean_c: number; tvdi_mean: number };
export function ThermalScatterChart({ data, measure }: { data: ThermalIndicator[]; measure: 'lst' | 'tvdi' }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!ref.current) return;
    const chart = echarts.init(ref.current);
    const isLst = measure === 'lst';
    chart.setOption({
      grid: { left: 58, right: 22, top: 25, bottom: 48 },
      tooltip: { formatter: (item: any) => { const row = item.data.row as ThermalIndicator; return `<b>${row.ward}</b> (${row.ward_code})<br/>NDVI: ${row.ndvi_mean_source.toFixed(4)}<br/>${isLst ? 'LST: ' + row.lst_mean_c.toFixed(2) + ' °C' : 'TVDI: ' + row.tvdi_mean.toFixed(4)}`; } },
      xAxis: { type: 'value', name: 'NDVI (thermal workflow)', nameLocation: 'middle', nameGap: 30 },
      yAxis: { type: 'value', name: isLst ? 'LST (°C)' : 'TVDI', nameLocation: 'middle', nameGap: 42, min: isLst ? undefined : 0, max: isLst ? undefined : 1 },
      series: [{ type: 'scatter', symbolSize: 9, itemStyle: { color: isLst ? '#f97316' : '#0891b2' }, data: data.map(row => ({ value: [row.ndvi_mean_source, isLst ? row.lst_mean_c : row.tvdi_mean], row })) }],
    });
    const resize = () => chart.resize(); window.addEventListener('resize', resize);
    return () => { window.removeEventListener('resize', resize); chart.dispose(); };
  }, [data, measure]);
  return <div ref={ref} className="h-80 w-full" />;
}

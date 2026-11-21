import { useEffect, useRef } from 'react';
import * as echarts from 'echarts';
import type { TimeSeries } from '../../types';

export function WardNdviTrendChart({ data, activeYear }: { data: TimeSeries; activeYear: number }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!ref.current || !data.data.length) return;
    const chart = echarts.init(ref.current);
    const years = data.data.map(point => point.date);
    chart.setOption({
      grid: { left: 42, right: 12, top: 22, bottom: 30 },
      tooltip: { trigger: 'axis', formatter: (items: any) => `${items[0].axisValue}<br/>NDVI: ${Number(items[0].data).toFixed(4)}` },
      xAxis: { type: 'category', data: years, axisLabel: { fontSize: 10 } },
      yAxis: { type: 'value', min: 0, max: 1, axisLabel: { formatter: (v: number) => v.toFixed(1), fontSize: 10 }, splitLine: { lineStyle: { color: '#e5e7eb' } } },
      series: [{ type: 'line', data: data.data.map(point => point.value), smooth: true, symbol: 'circle', symbolSize: 6, lineStyle: { color: '#0f766e', width: 2 }, itemStyle: { color: '#0f766e' }, areaStyle: { color: 'rgba(13,148,136,.12)' }, markPoint: { data: [{ coord: [String(activeYear), data.data.find(point => point.date === String(activeYear))?.value], symbolSize: 12, itemStyle: { color: '#f59e0b' }, label: { show: false } }] } }]
    });
    const resize = () => chart.resize(); window.addEventListener('resize', resize);
    return () => { window.removeEventListener('resize', resize); chart.dispose(); };
  }, [data, activeYear]);
  return <div ref={ref} className="h-48 w-full" aria-label="Biểu đồ biến động NDVI 2015 đến 2025" />;
}

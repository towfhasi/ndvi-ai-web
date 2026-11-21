import React, { useEffect, useState } from 'react';
import { Card } from '../components/common/Card';
import { TimeSeriesChart } from '../components/charts/TimeSeriesChart';
import { api } from '../api/client';
import type { TimeSeries } from '../types';
import { Link } from 'react-router-dom';
import { MapPreview } from '../components/map/MapPreview';

export const Dashboard: React.FC = () => {
  const [timeSeries, setTimeSeries] = useState<TimeSeries | null>(null);
  const [timeSeriesError, setTimeSeriesError] = useState(false);

  useEffect(() => {
    api.getTimeSeries().then(setTimeSeries).catch(() => setTimeSeriesError(true));
  }, []);

  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <Card title="Dự báo NDVI 7 ngày tiếp theo">
          <MapPreview />
          <Link to="/maps" className="mt-3 inline-block text-sm font-medium text-primary-700 hover:underline">Xem bản đồ chi tiết →</Link>
        </Card>

        <Card title="Biểu đồ biến động NDVI">
          {timeSeries ? <TimeSeriesChart data={timeSeries} title="" /> : <div className="flex h-96 items-center justify-center text-sm text-gray-500">{timeSeriesError ? 'Không tải được chuỗi biến động NDVI.' : 'Đang tải biểu đồ biến động NDVI...'}</div>}
        </Card>
    </div>
  );
};

export default Dashboard;

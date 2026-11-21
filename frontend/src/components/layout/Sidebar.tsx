import React from 'react';
import { Link, useLocation } from 'react-router-dom';

const BrainCircuitIcon = () => <svg viewBox="0 0 24 24" className="h-5 w-5 text-teal-600" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M9.5 2A2.5 2.5 0 0 0 7 4.5V6a2 2 0 0 0-2 2v1a2 2 0 0 0 2 2v1.5a2.5 2.5 0 0 0 2.5 2.5H10v4"/><path d="M14.5 2A2.5 2.5 0 0 1 17 4.5V6a2 2 0 0 1 2 2v1a2 2 0 0 1-2 2v1.5a2.5 2.5 0 0 1-2.5 2.5H14v4"/><path d="M10 6h4M10 10h4M12 2v4M12 10v8"/><circle cx="12" cy="21" r="1"/></svg>;
const menuItems = [
  { path: '/', label: 'TỔNG QUAN', icon: '📊' },
  { path: '/maps', label: 'BẢN ĐỒ NDVI', icon: '🗺️' },
  { path: '/analytics', label: 'PHÂN TÍCH NDVI', icon: '📈' },
  { path: '/timeseries', label: 'CHUỖI THỜI GIAN', icon: '📉' },
  { path: '/forecast', label: 'DỰ BÁO AI', icon: <BrainCircuitIcon /> },
];
export const Sidebar: React.FC = () => {
  const location = useLocation();
  return <div className="w-64 bg-white h-screen shadow-lg fixed left-0 top-0 flex flex-col"><div className="p-6 border-b border-gray-200"><h1 className="text-2xl font-bold text-primary-600">NDVI AI</h1><p className="text-sm text-gray-600 mt-1">TP. Hồ Chí Minh</p></div><nav className="flex-1 overflow-y-auto py-4">{menuItems.map(item => <Link key={item.path} to={item.path} className={`flex items-center gap-3 px-6 py-3 transition-colors ${location.pathname === item.path ? 'bg-primary-50 text-primary-700' : 'text-gray-700 hover:bg-gray-50'}`}><span className="text-xl flex h-5 w-5 items-center justify-center">{item.icon}</span><span className="font-medium">{item.label}</span></Link>)}</nav><div className="p-6 border-t border-gray-200 text-xs text-gray-500"><p>© 2026 NDVI AI System</p><p className="mt-1">Phiên bản 1.0.0</p></div></div>;
};
export default Sidebar;

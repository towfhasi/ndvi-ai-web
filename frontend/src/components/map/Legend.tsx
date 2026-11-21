import type { Dataset } from '../../types';

const LEGENDS = {
  lst: {
    title: 'LST (°C)',
    range: ['20 °C', '45 °C'],
    colors: ['#0000FF', '#0066FF', '#00FFFF', '#00FF00', '#FFFF00', '#FFCC00', '#FF6600', '#FF0000'],
  },
  ndvi: {
    title: 'NDVI',
    range: ['-0,2', '1,0'],
    colors: ['#FF0000', '#FF7F00', '#FFFF00', '#ADFF2F', '#00FF00', '#00FFFF', '#007FFF', '#0000FF'],
  },
  tvdi: {
    title: 'TVDI — khô hạn tương đối',
    range: ['0,0 thấp', '1,0 cao'],
    colors: ['#066B00', '#0BC400', '#0CE100', '#00FF00', '#FFFF00', '#FFCC00', '#FF6600', '#FF0000'],
  },
};

// Must remain identical to DISPLAY_SCALES in backend/app/routers/tiles.py.
export function Legend({ dataset }: { dataset?: Dataset }) {
  const type = dataset?.id.startsWith('lst') ? 'lst' : dataset?.id.startsWith('tvdi') ? 'tvdi' : 'ndvi';
  const legend = LEGENDS[type];
  const gradient = `linear-gradient(to right, ${legend.colors.join(', ')})`;
  return <div className="bg-white p-4 rounded-lg shadow-md"><h4 className="mb-3 text-sm font-semibold text-gray-700">{legend.title}</h4><div className="h-4 rounded border" style={{ background: gradient }} /><div className="mt-1 flex justify-between text-xs text-gray-600"><span>{legend.range[0]}</span><span>{legend.range[1]}</span></div>{dataset && <div className="mt-4 border-t pt-4 text-xs text-gray-500">{dataset.name}</div>}</div>;
}
export default Legend;

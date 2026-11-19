// A flat map of India drawn on a canvas from the RF25 land mask (no map tiles, no extra dependency, nothing fetched from a third party).
// Layers: RF25 client regions, Weather Union gauges coloured by where they are in the check -> flag -> audit cycle, and IMD stations
// (NOAA's list of Indian synoptic stations). Drag to pan, wheel to zoom, click a marker to select it.
import { useEffect, useMemo, useRef, useState } from 'react';
import { Minus, Plus, Maximize2 } from 'lucide-react';
import { CYCLE_COLOR, MapView, fitView, nearestPoint, panBy, project, regionColor, zoomAt } from './lib';
import type { CycleState } from './lib';
import type { MapLayers } from './types';

export interface MapPoint {
  key: string; kind: 'gauge' | 'imd' | 'upload'; id: string; label: string; lat: number; lon: number; state: CycleState;
  synthetic?: boolean;                       // every checked row of this station is synthetic: drawn with a violet dashed ring
}
export interface MapShow { regions: boolean; gauges: boolean; imd: boolean; dataOnly: boolean }

interface Props {
  layers: MapLayers | null;
  points: MapPoint[];
  show: MapShow;
  selected: string | null;
  onSelect: (p: MapPoint | null) => void;
  height?: number;
}

const HIT_PX = 9;

export function IndiaMap({ layers, points, show, selected, onSelect, height = 560 }: Props) {
  const wrap = useRef<HTMLDivElement | null>(null);
  const canvas = useRef<HTMLCanvasElement | null>(null);
  const drag = useRef<{ x: number; y: number; moved: number } | null>(null);
  const touched = useRef(false);               // once the user pans or zooms, a later resize no longer refits the map
  const [size, setSize] = useState({ w: 0, h: height });
  const [view, setView] = useState<MapView | null>(null);
  const [hover, setHover] = useState<{ p: MapPoint; x: number; y: number } | null>(null);

  const visible = useMemo(() => points.filter((p) => {
    if (p.kind === 'imd') return show.imd;
    if (p.kind === 'gauge') return show.gauges && (!show.dataOnly || p.state !== 'unchecked');
    return true;                                                   // stations from uploaded files are always drawn
  }), [points, show]);

  useEffect(() => {
    const el = wrap.current;
    if (!el) return;
    const measure = () => setSize({ w: Math.max(200, Math.floor(el.clientWidth)), h: height });
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, [height]);
  useEffect(() => { if (size.w > 0 && !touched.current) setView(fitView(size.w, size.h)); }, [size]);

  // wheel zoom needs a non-passive listener to stop the page from scrolling
  useEffect(() => {
    const c = canvas.current;
    if (!c) return;
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      touched.current = true;
      const r = c.getBoundingClientRect();
      setView((v) => (v ? zoomAt(v, e.deltaY < 0 ? 1.25 : 0.8, e.clientX - r.left, e.clientY - r.top, size.w, size.h) : v));
    };
    c.addEventListener('wheel', onWheel, { passive: false });
    return () => c.removeEventListener('wheel', onWheel);
  }, [size]);

  useEffect(() => {
    const c = canvas.current;
    if (!c || !view || size.w === 0) return;
    const dpr = window.devicePixelRatio || 1;
    c.width = size.w * dpr; c.height = size.h * dpr;
    const ctx = c.getContext('2d');
    if (!ctx) return;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.fillStyle = '#F1F5F9';
    ctx.fillRect(0, 0, size.w, size.h);

    // graticule every 5 degrees
    ctx.strokeStyle = '#D9E2EE'; ctx.lineWidth = 1; ctx.fillStyle = '#94A3B8'; ctx.font = '10px monospace';
    for (let lat = 5; lat <= 40; lat += 5) {
      const y = project(lat, view.cx, view, size.w, size.h).y;
      ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(size.w, y); ctx.stroke(); ctx.fillText(`${lat}°N`, 4, y - 2);
    }
    for (let lon = 65; lon <= 100; lon += 5) {
      const x = project(view.cy, lon, view, size.w, size.h).x;
      ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, size.h); ctx.stroke(); ctx.fillText(`${lon}°E`, x + 3, size.h - 4);
    }

    // RF25 land cells (row 0 is the southernmost)
    if (layers) {
      const { lat0, lon0, step } = layers.grid;
      const px = step * view.scale;
      layers.rows.forEach((row, r) => {
        for (let col = 0; col < row.length; col++) {
          const d = row.charCodeAt(col) - 48;
          if (d <= 0) continue;
          const p = project(lat0 + step * r + step / 2, lon0 + step * col - step / 2, view, size.w, size.h);
          if (p.x > size.w || p.y > size.h || p.x + px < 0 || p.y + px < 0) continue;
          ctx.fillStyle = show.regions ? regionColor(d) : '#E2E8F0';
          ctx.fillRect(Math.floor(p.x), Math.floor(p.y), Math.ceil(px) + 1, Math.ceil(px) + 1);
        }
      });
    }

    const at = (p: MapPoint) => project(p.lat, p.lon, view, size.w, size.h);
    const draw = (p: MapPoint) => {
      const { x, y } = at(p);
      if (x < -10 || y < -10 || x > size.w + 10 || y > size.h + 10) return;
      ctx.lineWidth = 1.2; ctx.strokeStyle = '#FFFFFF';
      if (p.kind === 'imd') {
        ctx.fillStyle = '#111827';
        ctx.beginPath(); ctx.moveTo(x, y - 5); ctx.lineTo(x + 4.5, y + 3.5); ctx.lineTo(x - 4.5, y + 3.5); ctx.closePath(); ctx.fill(); ctx.stroke();
      } else if (p.kind === 'upload') {
        ctx.fillStyle = CYCLE_COLOR[p.state];
        ctx.beginPath(); ctx.moveTo(x, y - 6); ctx.lineTo(x + 6, y); ctx.lineTo(x, y + 6); ctx.lineTo(x - 6, y); ctx.closePath(); ctx.fill(); ctx.stroke();
      } else {
        const hasData = p.state !== 'unchecked';
        ctx.fillStyle = hasData ? CYCLE_COLOR[p.state] : 'rgba(100,116,139,0.55)';
        ctx.beginPath(); ctx.arc(x, y, hasData ? 5.5 : 3, 0, Math.PI * 2); ctx.fill(); if (hasData) ctx.stroke();
      }
    };
    visible.filter((p) => p.kind === 'imd').forEach(draw);
    visible.filter((p) => p.kind === 'gauge' && p.state === 'unchecked').forEach(draw);
    visible.filter((p) => p.kind !== 'imd' && !(p.kind === 'gauge' && p.state === 'unchecked')).forEach(draw);
    // a violet dashed ring marks a station whose checked rows are all synthetic, so it is never read as a real gauge status
    ctx.strokeStyle = '#7C3AED'; ctx.lineWidth = 1.6; ctx.setLineDash([3, 2]);
    for (const p of visible) {
      if (!p.synthetic || p.state === 'unchecked') continue;
      const { x, y } = at(p);
      if (x < -10 || y < -10 || x > size.w + 10 || y > size.h + 10) continue;
      ctx.beginPath(); ctx.arc(x, y, 8.5, 0, Math.PI * 2); ctx.stroke();
    }
    ctx.setLineDash([]);
    const sel = visible.find((p) => p.key === selected);
    if (sel) {
      const { x, y } = at(sel);
      ctx.lineWidth = 2.5; ctx.strokeStyle = '#0F172A';
      ctx.beginPath(); ctx.arc(x, y, 11, 0, Math.PI * 2); ctx.stroke();
    }
  }, [layers, view, size, visible, show.regions, selected]);

  const pointer = (e: React.MouseEvent) => {
    const r = (canvas.current as HTMLCanvasElement).getBoundingClientRect();
    return { x: e.clientX - r.left, y: e.clientY - r.top };
  };
  const hit = (x: number, y: number): MapPoint | null => {
    if (!view) return null;
    const screen = visible.map((p) => ({ ...project(p.lat, p.lon, view, size.w, size.h), p }));
    // markers with data win over the small grey gauges and the IMD triangles when they overlap
    const withData = screen.filter((s) => s.p.kind === 'upload' || (s.p.kind === 'gauge' && s.p.state !== 'unchecked'));
    return (nearestPoint(withData, x, y, HIT_PX) ?? nearestPoint(screen, x, y, HIT_PX))?.p ?? null;
  };

  return (
    <div ref={wrap} className="relative rounded-lg border border-[#D3DCE7] overflow-hidden bg-slate-100" style={{ height }}>
      <canvas
        ref={canvas} role="img" aria-label="Map of India with gauges and IMD stations" style={{ width: size.w, height: size.h, cursor: drag.current ? 'grabbing' : hover ? 'pointer' : 'grab' }}
        onMouseDown={(e) => { const p = pointer(e); drag.current = { x: p.x, y: p.y, moved: 0 }; }}
        onMouseMove={(e) => {
          const p = pointer(e);
          if (drag.current) {
            const dx = p.x - drag.current.x, dy = p.y - drag.current.y;
            drag.current = { x: p.x, y: p.y, moved: drag.current.moved + Math.abs(dx) + Math.abs(dy) };
            touched.current = true;
            setView((v) => (v ? panBy(v, dx, dy) : v));
            setHover(null);
          } else {
            const h = hit(p.x, p.y);
            setHover(h ? { p: h, x: p.x, y: p.y } : null);
          }
        }}
        onMouseUp={(e) => {
          const moved = drag.current?.moved ?? 0;
          drag.current = null;
          if (moved < 4) { const p = pointer(e); onSelect(hit(p.x, p.y)); }
        }}
        onMouseLeave={() => { drag.current = null; setHover(null); }}
      />
      {hover && (
        <div className="absolute pointer-events-none px-2 py-1 rounded bg-slate-900 text-white text-[11px] font-mono shadow" style={{ left: Math.min(hover.x + 12, size.w - 180), top: Math.max(4, hover.y - 28) }}>
          {hover.p.label}
        </div>)}
      <div className="absolute top-2 right-2 flex flex-col gap-1">
        {([['Zoom in', Plus, () => { touched.current = true; setView((v) => (v ? zoomAt(v, 1.5, size.w / 2, size.h / 2, size.w, size.h) : v)); }],
           ['Zoom out', Minus, () => { touched.current = true; setView((v) => (v ? zoomAt(v, 1 / 1.5, size.w / 2, size.h / 2, size.w, size.h) : v)); }],
           ['Show all of India', Maximize2, () => { touched.current = false; setView(fitView(size.w, size.h)); }]] as const).map(([label, Icon, fn]) => (
          <button key={label} onClick={fn} aria-label={label} title={label} className="w-7 h-7 rounded bg-white border border-[#D3DCE7] shadow flex items-center justify-center hover:bg-[#F4F6FA]">
            <Icon className="w-3.5 h-3.5 text-slate-700" /></button>))}
      </div>
      {!layers && <div className="absolute inset-x-0 top-2 mx-auto w-fit text-[11px] bg-amber-50 border border-amber-300 text-amber-900 rounded px-2 py-1">The land mask is not available on this server; stations are drawn without the India outline.</div>}
    </div>
  );
}

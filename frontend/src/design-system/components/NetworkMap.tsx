import React, { useMemo, useState } from 'react';

/** One pin of the flat map. Only stations with a REAL position are drawn. */
export interface NetworkMapStation {
  station_id: string;
  name: string;
  latitude: number | null;
  longitude: number | null;
  /** Worst verdict among the station's checked rows; NO_DATA when nothing has been checked. */
  state: 'OK' | 'UNCERTAIN' | 'SUSPECT' | 'NO_DATA';
}

export interface NetworkMapProps {
  stations: NetworkMapStation[];
  selectedStationId?: string;
  onSelectStation?: (stationId: string) => void;
  className?: string;
}

const STATE_COLOR: Record<NetworkMapStation['state'], string> = {
  OK: '#10B981',
  UNCERTAIN: '#F59E0B',
  SUSPECT: '#EF4444',
  NO_DATA: '#94A3B8',
};

// Restored look of the original 2D radar (restored in slice S2b). Changed: pins are placed by their own latitude and longitude, fitted to
// the stations shown; the fixed demo positions, the "spatial consensus" links and the made-up health colours are gone.
export const NetworkMap: React.FC<NetworkMapProps> = ({
  stations,
  selectedStationId,
  onSelectStation,
  className = '',
}) => {
  const [hoveredStation, setHoveredStation] = useState<NetworkMapStation | null>(null);

  const placed = useMemo(
    () => stations.filter((s): s is NetworkMapStation & { latitude: number; longitude: number } => s.latitude !== null && s.longitude !== null),
    [stations],
  );

  const project = useMemo(() => {
    if (placed.length === 0) return () => ({ x: 300, y: 120 });
    const lats = placed.map((s) => s.latitude);
    const lons = placed.map((s) => s.longitude);
    const latMin = Math.min(...lats), latMax = Math.max(...lats);
    const lonMin = Math.min(...lons), lonMax = Math.max(...lons);
    const spanLat = Math.max(0.5, latMax - latMin);
    const spanLon = Math.max(0.5, lonMax - lonMin);
    const scale = Math.min(480 / spanLon, 170 / spanLat);
    const cx = (lonMin + lonMax) / 2, cy = (latMin + latMax) / 2;
    return (lat: number, lon: number) => ({ x: 300 + (lon - cx) * scale, y: 120 - (lat - cy) * scale });
  }, [placed]);

  return (
    <div className={`relative bg-[#FFFFFF] border border-[#D3DCE7] rounded-xl overflow-hidden shadow-lg ${className}`}>
      {/* Top Map Header & Controls */}
      <div className="absolute top-3 left-4 right-4 z-10 flex items-center justify-between pointer-events-none">
        <div className="flex items-center gap-2 pointer-events-auto">
          <span className="text-[11px] font-bold font-mono uppercase tracking-wider text-slate-600">
            Station map (2D)
          </span>
          <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-sky-500/15 text-sky-700 border border-sky-500/30 font-semibold">
            {placed.length} stations
          </span>
        </div>

        <div className="flex items-center gap-3 text-[10px] font-mono text-slate-500 bg-[#F4F6FA]/90 backdrop-blur-md px-2.5 py-1 rounded-lg border border-[#D3DCE7] pointer-events-auto">
          <span className="flex items-center gap-1">
            <span className="w-2 h-2 rounded-full bg-emerald-400" /> OK
          </span>
          <span className="flex items-center gap-1">
            <span className="w-2 h-2 rounded-full bg-amber-400" /> UNCERTAIN
          </span>
          <span className="flex items-center gap-1">
            <span className="w-2 h-2 rounded-full bg-rose-400" /> SUSPECT
          </span>
          <span className="flex items-center gap-1">
            <span className="w-2 h-2 rounded-full bg-slate-400" /> Not checked
          </span>
        </div>
      </div>

      {/* 2D SVG Canvas */}
      <svg viewBox="0 0 600 240" className="w-full h-56 sm:h-64 select-none">
        {/* Background grid circles */}
        <circle cx="300" cy="120" r="100" fill="none" stroke="#D3DCE7" strokeDasharray="3 3" opacity="0.5" />
        <circle cx="300" cy="120" r="60" fill="none" stroke="#D3DCE7" strokeDasharray="2 2" opacity="0.4" />
        <line x1="300" y1="20" x2="300" y2="220" stroke="#D3DCE7" strokeDasharray="2 2" opacity="0.3" />
        <line x1="100" y1="120" x2="500" y2="120" stroke="#D3DCE7" strokeDasharray="2 2" opacity="0.3" />

        {/* Station Nodes */}
        {placed.map((st) => {
          const pos = project(st.latitude, st.longitude);
          const isSelected = st.station_id === selectedStationId;
          const isHovered = hoveredStation?.station_id === st.station_id;
          const nodeColor = STATE_COLOR[st.state];

          return (
            <g
              key={st.station_id}
              className="cursor-pointer"
              onMouseEnter={() => setHoveredStation(st)}
              onMouseLeave={() => setHoveredStation(null)}
              onClick={() => onSelectStation && onSelectStation(st.station_id)}
            >
              {(isSelected || isHovered || st.state === 'SUSPECT') && (
                <circle
                  cx={pos.x}
                  cy={pos.y}
                  r={isSelected ? 12 : 9}
                  fill="none"
                  stroke={isSelected ? '#38BDF8' : nodeColor}
                  strokeWidth={1.5}
                  opacity={0.7}
                />
              )}

              <circle
                cx={pos.x}
                cy={pos.y}
                r={isSelected ? 5 : 3}
                fill={isSelected ? '#38BDF8' : nodeColor}
                stroke="#FFFFFF"
                strokeWidth={1.5}
              />
            </g>
          );
        })}
      </svg>

      {placed.length === 0 && (
        <div className="absolute inset-0 flex items-center justify-center text-xs text-slate-500 font-mono pointer-events-none">
          No station with a position loaded.
        </div>
      )}

      {/* Hover Station Card */}
      {hoveredStation && hoveredStation.latitude !== null && hoveredStation.longitude !== null && (
        <div className="absolute bottom-2 left-4 right-4 z-20 bg-[#EDF1F7]/95 backdrop-blur-md p-2.5 rounded-lg border border-sky-500/40 shadow-xl flex items-center justify-between text-xs font-mono">
          <div>
            <span className="font-bold text-slate-900">{hoveredStation.station_id}</span>
            <span className="text-slate-600 ml-2">({hoveredStation.name})</span>
            <span className="text-slate-500 text-[11px] block mt-0.5">
              Lat: {hoveredStation.latitude.toFixed(2)}°, Lon: {hoveredStation.longitude.toFixed(2)}°
            </span>
          </div>
          <span className="text-[10px] uppercase text-slate-500">{hoveredStation.state === 'NO_DATA' ? 'not checked' : hoveredStation.state}</span>
        </div>
      )}
    </div>
  );
};

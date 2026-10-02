import React, { useState } from 'react';
import { Station } from '../../types';
import { StatusBadge } from './StatusBadge';

export interface NetworkMapProps {
  stations: Station[];
  selectedStationId?: string;
  onSelectStation?: (stationId: string) => void;
  className?: string;
}

export const NetworkMap: React.FC<NetworkMapProps> = ({
  stations,
  selectedStationId,
  onSelectStation,
  className = '',
}) => {
  const [hoveredStation, setHoveredStation] = useState<Station | null>(null);

  const defaultCoordinates: Record<string, { x: number; y: number }> = {
    'AWS-001': { x: 180, y: 110 },
    'AWS-002': { x: 320, y: 80 },
    'AWS-003': { x: 420, y: 150 },
    'AWS-004': { x: 260, y: 180 },
    'PUNE-EXT-001': { x: 200, y: 130 },
    'DELHI-EXT-001': { x: 280, y: 60 },
    'LONDON-EXT-001': { x: 120, y: 70 },
    'TOKYO-EXT-001': { x: 460, y: 100 },
    'DV-EXT-001': { x: 80, y: 140 },
  };

  const getStationPosition = (st: Station, index: number) => {
    if (defaultCoordinates[st.station_id]) {
      return defaultCoordinates[st.station_id];
    }
    if (st.latitude && st.longitude) {
      const x = Math.max(50, Math.min(550, ((st.longitude + 180) / 360) * 500 + 50));
      const y = Math.max(40, Math.min(200, ((90 - st.latitude) / 180) * 180 + 30));
      return { x, y };
    }
    const angle = (index / Math.max(1, stations.length)) * 2 * Math.PI;
    return {
      x: 300 + Math.cos(angle) * 160,
      y: 120 + Math.sin(angle) * 70,
    };
  };

  return (
    <div className={`relative bg-[#152033] border border-[#263B5E] rounded-xl overflow-hidden shadow-lg ${className}`}>
      {/* Top Map Header & Controls */}
      <div className="absolute top-3 left-4 right-4 z-10 flex items-center justify-between pointer-events-none">
        <div className="flex items-center gap-2 pointer-events-auto">
          <span className="text-[11px] font-bold font-mono uppercase tracking-wider text-slate-300">
            Regional AWS Telemetry Radar & Consensus Cluster (2D)
          </span>
          <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-sky-500/15 text-sky-300 border border-sky-500/30 font-semibold">
            Tier 3.5 Spatial QC
          </span>
        </div>

        <div className="flex items-center gap-3 text-[10px] font-mono text-slate-400 bg-[#10192A]/90 backdrop-blur-md px-2.5 py-1 rounded-lg border border-[#263B5E] pointer-events-auto">
          <span className="flex items-center gap-1">
            <span className="w-2 h-2 rounded-full bg-emerald-400" /> Nominal
          </span>
          <span className="flex items-center gap-1">
            <span className="w-2 h-2 rounded-full bg-amber-400" /> Degraded
          </span>
          <span className="flex items-center gap-1">
            <span className="w-2 h-2 rounded-full bg-rose-400" /> Fault
          </span>
        </div>
      </div>

      {/* 2D SVG Canvas Topology */}
      <svg viewBox="0 0 600 240" className="w-full h-56 sm:h-64 select-none">
        {/* Background Radar Grid Circles */}
        <circle cx="300" cy="120" r="100" fill="none" stroke="#263B5E" strokeDasharray="3 3" opacity="0.5" />
        <circle cx="300" cy="120" r="60" fill="none" stroke="#263B5E" strokeDasharray="2 2" opacity="0.4" />
        <line x1="300" y1="20" x2="300" y2="220" stroke="#263B5E" strokeDasharray="2 2" opacity="0.3" />
        <line x1="100" y1="120" x2="500" y2="120" stroke="#263B5E" strokeDasharray="2 2" opacity="0.3" />

        {/* Consensus Buddy-Check Connection Links */}
        {stations.map((st, i) => {
          const pos1 = getStationPosition(st, i);
          return stations.slice(i + 1).map((st2, j) => {
            const pos2 = getStationPosition(st2, i + 1 + j);
            const dist = Math.hypot(pos1.x - pos2.x, pos1.y - pos2.y);
            if (dist > 180) return null;

            return (
              <line
                key={`${st.station_id}-${st2.station_id}`}
                x1={pos1.x}
                y1={pos1.y}
                x2={pos2.x}
                y2={pos2.y}
                stroke="#38BDF8"
                strokeWidth={1}
                strokeDasharray="4 4"
                opacity={0.35}
              />
            );
          });
        })}

        {/* Station Nodes */}
        {stations.map((st, idx) => {
          const pos = getStationPosition(st, idx);
          const isSelected = st.station_id === selectedStationId;
          const isHovered = hoveredStation?.station_id === st.station_id;
          const health = st.health_score ?? 98;
          const isCritical = health < 50;
          const isWarning = health >= 50 && health < 75;

          const nodeColor = isCritical ? '#EF4444' : isWarning ? '#F59E0B' : '#10B981';

          return (
            <g
              key={st.station_id}
              className="cursor-pointer"
              onMouseEnter={() => setHoveredStation(st)}
              onMouseLeave={() => setHoveredStation(null)}
              onClick={() => onSelectStation && onSelectStation(st.station_id)}
            >
              {/* Outer Pulsing Halo */}
              {(isSelected || isHovered || isCritical) && (
                <circle
                  cx={pos.x}
                  cy={pos.y}
                  r={isSelected ? 16 : 12}
                  fill="none"
                  stroke={nodeColor}
                  strokeWidth={1.5}
                  opacity={0.7}
                  className="animate-pulse"
                />
              )}

              {/* Station Core Marker */}
              <circle
                cx={pos.x}
                cy={pos.y}
                r={isSelected ? 7 : 5}
                fill={nodeColor}
                stroke="#152033"
                strokeWidth={2}
              />

              {/* Station ID Label */}
              <text
                x={pos.x}
                y={pos.y + 16}
                fill={isSelected ? '#38BDF8' : '#CBD5E1'}
                fontSize="10"
                fontFamily="monospace"
                fontWeight={isSelected ? 'bold' : 'normal'}
                textAnchor="middle"
              >
                {st.station_id}
              </text>
            </g>
          );
        })}
      </svg>

      {/* Hover Station Card Tooltip */}
      {hoveredStation && (
        <div className="absolute bottom-2 left-4 right-4 z-20 bg-[#1B2A44]/95 backdrop-blur-md p-2.5 rounded-lg border border-sky-500/40 shadow-xl flex items-center justify-between text-xs font-mono">
          <div>
            <span className="font-bold text-white">{hoveredStation.station_id}</span>
            <span className="text-slate-300 ml-2">({hoveredStation.name})</span>
            <span className="text-slate-400 text-[11px] block mt-0.5">
              Lat: {hoveredStation.latitude?.toFixed(2)}°, Lon: {hoveredStation.longitude?.toFixed(2)}° • Elev: {hoveredStation.elevation}m
            </span>
          </div>

          <div className="flex items-center gap-3">
            <div className="text-right">
              <span className="text-[10px] text-slate-400 uppercase block">Health Index</span>
              <span className="font-bold text-emerald-400">{hoveredStation.health_score ?? 98}%</span>
            </div>
            <StatusBadge
              label={hoveredStation.health_status || 'NOMINAL'}
              variant={(hoveredStation.health_score ?? 98) >= 75 ? 'nominal' : 'warning'}
              size="sm"
            />
          </div>
        </div>
      )}
    </div>
  );
};

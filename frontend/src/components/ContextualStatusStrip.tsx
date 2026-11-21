/**
 * frontend/src/components/ContextualStatusStrip.tsx
 * DataMend — Compact 1-Line Operational Context Strip (restored in slice S2b).
 * Shows the active live source and the selected station. Changed against the original: no invented freshness ("Age: 1s"), no fixed
 * "WMO QC VALID" pill, no default coordinates; without a live stream it says so.
 */

import React from 'react';
import { useSystemConfiguration } from '../context/SystemConfigurationContext';
import { StatusBadge } from '../design-system/components/StatusBadge';
import { useStation } from '../validation/StationContext';
import { sourceLabel } from './sourceLabel';

interface ContextualStatusStripProps {
  className?: string;
}

export const ContextualStatusStrip: React.FC<ContextualStatusStripProps> = ({ className = '' }) => {
  const { activeSource, selectedCity, activeSourceStatus, streamConnected, openSettings } = useSystemConfiguration();
  const { stationId, entry, gauges } = useStation();
  const gauge = gauges.find((g) => g.station_id === stationId);

  return (
    <div
      className={`bg-[#FFFFFF]/90 border border-[#D3DCE7] rounded-xl px-4 py-2.5 shadow-md flex flex-wrap items-center justify-between gap-3 text-xs font-mono select-none ${className}`}
    >
      {/* Left: Active Source & Station */}
      <div className="flex flex-wrap items-center gap-3 text-slate-600">
        <div className="flex items-center gap-2">
          <div className="p-1 rounded-md bg-[#EDF1F7] border border-slate-200">
            <span className="text-[10px] font-bold text-slate-600 font-mono">{activeSource ? 'SRC' : 'OFF'}</span>
          </div>
          <span className="font-bold text-slate-900 tracking-wide">{sourceLabel(activeSource, selectedCity?.name)}</span>
        </div>

        <div className="h-4 w-px bg-slate-300/60 hidden sm:block" />

        <div className="flex items-center gap-2 text-slate-600">
          {stationId ? (
            <>
              <span className="text-sky-600 font-bold">{stationId}</span>
              {entry && <span className="text-slate-500 hidden md:inline">({entry.place}, {entry.city})</span>}
              {gauge && (
                <span className="text-[11px] text-slate-500 hidden lg:flex items-center gap-1">
                  {gauge.latitude.toFixed(2)}°N, {gauge.longitude.toFixed(2)}°E
                </span>
              )}
            </>
          ) : (
            <span className="text-slate-500">No station selected</span>
          )}
        </div>
      </div>

      {/* Right: link status and the configure button */}
      <div className="flex items-center gap-3">
        <StatusBadge
          label={streamConnected ? activeSourceStatus?.status || 'STREAM OPEN' : 'NO LIVE STREAM'}
          variant={streamConnected ? 'nominal' : 'neutral'}
          size="sm"
          pulse={streamConnected}
        />
        {activeSourceStatus?.data_age_seconds !== undefined && (
          <div className="hidden sm:flex items-center gap-1 text-[11px] text-slate-500">
            <span>Age: <strong className="text-slate-700">{activeSourceStatus.data_age_seconds}s</strong></span>
          </div>
        )}

        <button
          onClick={openSettings}
          className="flex items-center gap-1.5 px-3 py-1 bg-[#F4F6FA] hover:bg-[#EDF1F7] border border-[#D3DCE7] hover:border-sky-400 text-slate-700 hover:text-slate-900 rounded-lg text-xs font-bold transition-all shadow-sm group"
        >
          <span>Configure</span>
        </button>
      </div>
    </div>
  );
};

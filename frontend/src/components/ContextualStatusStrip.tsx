/**
 * frontend/src/components/ContextualStatusStrip.tsx
 * DataMend — Compact 1-Line Operational Context Strip (restored in slice S2b, wired to the stream state).
 * Shows the active live source, the selected station and the stream state from the socket and the server's status frames. Changed
 * against the original: no invented freshness, no fixed "WMO QC VALID" pill, no default coordinates; without a live stream it says so.
 */

import React from 'react';
import { useSystemConfiguration } from '../context/SystemConfigurationContext';
import { StatusBadge } from '../design-system/components/StatusBadge';
import { useStation } from '../validation/StationContext';
import { describeStream, fmtUtc } from '../services/stream';
import { sourceLabel } from './sourceLabel';
import { fmtLatLon, packetCount } from '../services/geo';

interface ContextualStatusStripProps {
  className?: string;
}

export const ContextualStatusStrip: React.FC<ContextualStatusStripProps> = ({ className = '' }) => {
  const { activeSource, activeSourceStatus, selectedCity, streamConnected, streamStatus, openSettings } = useSystemConfiguration();
  const { stationId, entry, gauges, streamStations } = useStation();
  const gauge = gauges.find((g) => g.station_id === stationId);
  const pos = gauge ?? streamStations.find((s) => s.station_id === stationId);
  const view = describeStream(streamConnected, streamStatus);
  const packets = packetCount(activeSourceStatus);   // the data-sources status, the same number the settings drawer shows

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
              {entry && <span className="text-slate-500 hidden md:inline">({entry.place}{entry.source === 'stream' ? '' : `, ${entry.city}`})</span>}
              {pos && pos.latitude != null && pos.longitude != null && (
                <span className="text-[11px] text-slate-500 hidden lg:flex items-center gap-1">
                  {fmtLatLon(pos.latitude, pos.longitude)}
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
        <span title={view.detail}>
          <StatusBadge
            label={view.label}
            variant={view.tone === 'nominal' ? 'nominal' : view.tone === 'warning' ? 'warning' : view.tone === 'critical' ? 'critical' : 'neutral'}
            size="sm"
            pulse={view.live}
          />
        </span>
        {streamStatus && streamStatus.state !== 'stopped' && packets !== null && (
          <span className="hidden sm:inline text-[11px] text-slate-500">{packets} packets</span>
        )}
        {streamStatus?.last_reading_at && (
          <span className="hidden md:inline text-[11px] text-slate-500">last reading {fmtUtc(streamStatus.last_reading_at)} UTC</span>
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

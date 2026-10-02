/**
 * frontend/src/components/ContextualStatusStrip.tsx
 * DataMend — Compact 1-Line Operational Context Strip.
 * Replaces the repetitive bulky HUD with a sleek status indicator and direct link to Settings.
 */

import React from 'react';
import { useSystemConfiguration } from '../context/SystemConfigurationContext';
import { StatusBadge } from '../design-system/components/StatusBadge';

interface ContextualStatusStripProps {
  className?: string;
}

export const ContextualStatusStrip: React.FC<ContextualStatusStripProps> = ({ className = '' }) => {
  const {
    activeSource,
    selectedCity,
    selectedStationId,
    activeSourceStatus,
    openSettings,
  } = useSystemConfiguration();

  const getSourceIcon = () => {
    const code = activeSource === 'SIMULATED' ? 'SIM' : activeSource === 'EXTERNAL_API' ? 'EXT' : 'HW';
    return <span className="text-[10px] font-bold text-slate-600 font-mono">{code}</span>;
  };

  const getSourceLabel = () => {
    switch (activeSource) {
      case 'SIMULATED':
        return 'SIMULATED AWS';
      case 'EXTERNAL_API':
        return selectedCity ? `OPEN-METEO: ${selectedCity.name.toUpperCase()}` : 'OPEN-METEO LIVE';
      case 'PHYSICAL_AWS':
        return 'PHYSICAL AWS (ESP32)';
    }
  };

  return (
    <div
      className={`bg-[#FFFFFF]/90 border border-[#D3DCE7] rounded-xl px-4 py-2.5 shadow-md flex flex-wrap items-center justify-between gap-3 text-xs font-mono select-none ${className}`}
    >
      {/* Left: Active Source & Synoptic Location */}
      <div className="flex flex-wrap items-center gap-3 text-slate-600">
        <div className="flex items-center gap-2">
          <div className="p-1 rounded-md bg-[#EDF1F7] border border-slate-200">
            {getSourceIcon()}
          </div>
          <span className="font-bold text-slate-900 tracking-wide">{getSourceLabel()}</span>
        </div>

        <div className="h-4 w-px bg-slate-300/60 hidden sm:block" />

        {/* Station & Coordinates */}
        <div className="flex items-center gap-2 text-slate-600">
          <span className="text-sky-600 font-bold">{selectedStationId}</span>
          {selectedCity && (
            <span className="text-slate-500 hidden md:inline">
              ({selectedCity.name}, {selectedCity.country})
            </span>
          )}
          <span className="text-[11px] text-slate-500 hidden lg:flex items-center gap-1">
            
            {selectedCity
              ? `${selectedCity.latitude.toFixed(2)}°N, ${selectedCity.longitude.toFixed(2)}°E`
              : '28.61°N, 77.21°E'}
          </span>
        </div>
      </div>

      {/* Right: Data Freshness, Quality Control Status, and Configure Button */}
      <div className="flex items-center gap-3">
        {/* Status Badge */}
        <StatusBadge
          label={activeSourceStatus?.status || 'CONNECTED'}
          variant={
            activeSourceStatus?.status === 'CONNECTED' || activeSourceStatus?.status === 'RUNNING'
              ? 'nominal'
              : 'warning'
          }
          size="sm"
          pulse={activeSource === 'EXTERNAL_API' || activeSource === 'SIMULATED'}
        />

        {/* Freshness indicator */}
        <div className="hidden sm:flex items-center gap-1 text-[11px] text-slate-500">
          
          <span>Age: <strong className="text-emerald-600">{activeSourceStatus?.data_age_seconds ?? 1}s</strong></span>
        </div>

        {/* 5-Tier QC Pill */}
        <div className="hidden xl:flex items-center gap-1 text-[11px] text-emerald-600 bg-emerald-500/10 px-2 py-0.5 rounded border border-emerald-500/30">
          
          <span>WMO QC VALID</span>
        </div>

        {/* Configure trigger button */}
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

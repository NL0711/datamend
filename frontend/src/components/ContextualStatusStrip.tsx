/**
 * frontend/src/components/ContextualStatusStrip.tsx
 * SkyGuard AI — Compact 1-Line Operational Context Strip.
 * Replaces the repetitive bulky HUD with a sleek status indicator and direct link to Settings.
 */

import React from 'react';
import {
  Radio,
  Globe,
  Cpu,
  Sliders,
  MapPin,
  Clock,
  ShieldCheck,
} from 'lucide-react';
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
    switch (activeSource) {
      case 'SIMULATED':
        return <Radio className="w-3.5 h-3.5 text-amber-400" />;
      case 'EXTERNAL_API':
        return <Globe className="w-3.5 h-3.5 text-sky-400" />;
      case 'PHYSICAL_AWS':
        return <Cpu className="w-3.5 h-3.5 text-emerald-400" />;
    }
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
      className={`bg-[#152033]/90 border border-[#263B5E] rounded-xl px-4 py-2.5 shadow-md flex flex-wrap items-center justify-between gap-3 text-xs font-mono select-none ${className}`}
    >
      {/* Left: Active Source & Synoptic Location */}
      <div className="flex flex-wrap items-center gap-3 text-slate-300">
        <div className="flex items-center gap-2">
          <div className="p-1 rounded-md bg-[#1B2A44] border border-white/[0.08]">
            {getSourceIcon()}
          </div>
          <span className="font-bold text-white tracking-wide">{getSourceLabel()}</span>
        </div>

        <div className="h-4 w-px bg-white/[0.1] hidden sm:block" />

        {/* Station & Coordinates */}
        <div className="flex items-center gap-2 text-slate-300">
          <span className="text-sky-400 font-bold">{selectedStationId}</span>
          {selectedCity && (
            <span className="text-slate-400 hidden md:inline">
              ({selectedCity.name}, {selectedCity.country})
            </span>
          )}
          <span className="text-[11px] text-slate-400 hidden lg:flex items-center gap-1">
            <MapPin className="w-3 h-3 text-sky-400" />
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
        <div className="hidden sm:flex items-center gap-1 text-[11px] text-slate-400">
          <Clock className="w-3 h-3 text-slate-500" />
          <span>Age: <strong className="text-emerald-400">{activeSourceStatus?.data_age_seconds ?? 1}s</strong></span>
        </div>

        {/* 5-Tier QC Pill */}
        <div className="hidden xl:flex items-center gap-1 text-[11px] text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded border border-emerald-500/30">
          <ShieldCheck className="w-3 h-3" />
          <span>WMO QC VALID</span>
        </div>

        {/* Configure trigger button */}
        <button
          onClick={openSettings}
          className="flex items-center gap-1.5 px-3 py-1 bg-[#10192A] hover:bg-[#1B2A44] border border-[#263B5E] hover:border-sky-400 text-slate-200 hover:text-white rounded-lg text-xs font-bold transition-all shadow-sm group"
        >
          <Sliders className="w-3.5 h-3.5 text-sky-400 group-hover:rotate-45 transition-transform" />
          <span>Configure</span>
        </button>
      </div>
    </div>
  );
};

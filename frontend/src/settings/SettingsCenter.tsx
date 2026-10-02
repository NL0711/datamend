/**
 * frontend/src/settings/SettingsCenter.tsx
 * SkyGuard AI — Centralized Global System Configuration & Operations Drawer.
 * 6-Section Configuration Center for Ingestion, Climate Synoptic Sites, Display, and Diagnostics.
 */

import React, { useState } from 'react';
import {
  X,
  Radio,
  Globe,
  Cpu,
  RefreshCw,
  Sliders,
  Activity,
  Check,
  MapPin,
  Play,
  Square,
  AlertCircle,
  Laptop,
} from 'lucide-react';
import { useSystemConfiguration } from '../context/SystemConfigurationContext';
import { CITY_PRESETS, DataSourceType, DisplayDensity } from '../types';
import { StatusBadge } from '../design-system/components/StatusBadge';
import { startSimulation, stopSimulation, getSimulationStatus } from '../services/api';

export const SettingsCenter: React.FC = () => {
  const {
    activeSource,
    selectedCityId,
    isSettingsOpen,
    isConfiguringCity,
    isSwitchingSource,
    error,
    preferences,
    systemHealth,
    closeSettings,
    changeSource,
    changeCity,
    updatePreferences,
    clearError,
  } = useSystemConfiguration();

  const [activeTabSection, setActiveTabSection] = useState<'source' | 'display' | 'diagnostics'>('source');
  const [simLoading, setSimLoading] = useState<boolean>(false);
  const [simRunning, setSimRunning] = useState<boolean>(true);

  if (!isSettingsOpen) return null;

  const handleToggleSimulation = async () => {
    setSimLoading(true);
    try {
      if (simRunning) {
        await stopSimulation();
        setSimRunning(false);
      } else {
        await startSimulation();
        setSimRunning(true);
      }
      const st = await getSimulationStatus();
      setSimRunning(st.running);
    } catch {
      // Ignore
    } finally {
      setSimLoading(false);
    }
  };

  const getSourceIcon = (type: DataSourceType) => {
    switch (type) {
      case 'SIMULATED':
        return <Radio className="w-4 h-4 text-amber-400" />;
      case 'EXTERNAL_API':
        return <Globe className="w-4 h-4 text-sky-400" />;
      case 'PHYSICAL_AWS':
        return <Cpu className="w-4 h-4 text-emerald-400" />;
    }
  };

  return (
    <div className="fixed inset-0 z-50 overflow-hidden select-none">
      {/* Backdrop overlay */}
      <div
        onClick={closeSettings}
        className="absolute inset-0 bg-black/75 backdrop-blur-sm transition-opacity animate-fadeIn"
      />

      {/* Slide-out Settings Drawer */}
      <div className="absolute inset-y-0 right-0 max-w-full flex pl-10">
        <div className="w-screen max-w-xl bg-[#131E30] border-l border-[#263B5E] shadow-2xl flex flex-col justify-between text-slate-100 font-sans animate-slideLeft">
          {/* Drawer Header */}
          <div className="p-5 border-b border-[#263B5E] bg-[#152033] flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="p-2 rounded-lg bg-[#1B2A44] border border-sky-500/40 text-sky-400">
                <Sliders className="w-5 h-5" />
              </div>
              <div>
                <h2 className="text-sm font-bold text-white uppercase tracking-wider font-mono">
                  SYSTEM CONFIGURATION CENTER
                </h2>
                <p className="text-[11px] text-slate-400">
                  Global Ingest Provenance, Climate Sites & Operational Preferences
                </p>
              </div>
            </div>

            <button
              onClick={closeSettings}
              className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-[#1B2A44] transition-colors"
              title="Close Settings (Esc)"
            >
              <X className="w-5 h-5" />
            </button>
          </div>

          {/* Section Navigation Tabs */}
          <div className="px-5 pt-3 pb-0 bg-[#152033] border-b border-[#263B5E] flex items-center gap-2 font-mono text-xs">
            <button
              onClick={() => setActiveTabSection('source')}
              className={`pb-2.5 px-2 border-b-2 font-bold transition-all ${
                activeTabSection === 'source'
                  ? 'border-sky-400 text-white'
                  : 'border-transparent text-slate-400 hover:text-slate-200'
              }`}
            >
              Data Ingestion & Location
            </button>
            <button
              onClick={() => setActiveTabSection('display')}
              className={`pb-2.5 px-2 border-b-2 font-bold transition-all ${
                activeTabSection === 'display'
                  ? 'border-sky-400 text-white'
                  : 'border-transparent text-slate-400 hover:text-slate-200'
              }`}
            >
              Display & Preferences
            </button>
            <button
              onClick={() => setActiveTabSection('diagnostics')}
              className={`pb-2.5 px-2 border-b-2 font-bold transition-all ${
                activeTabSection === 'diagnostics'
                  ? 'border-sky-400 text-white'
                  : 'border-transparent text-slate-400 hover:text-slate-200'
              }`}
            >
              System Health Diagnostics
            </button>
          </div>

          {/* Scrollable Content Body */}
          <div className="flex-1 overflow-y-auto p-5 space-y-6">
            {/* Global Error Banner if any */}
            {error && (
              <div className="p-3 bg-rose-500/15 border border-rose-500/40 rounded-xl text-rose-200 text-xs flex items-center justify-between font-mono">
                <div className="flex items-center gap-2">
                  <AlertCircle className="w-4 h-4 flex-shrink-0" />
                  <span>{error}</span>
                </div>
                <button onClick={clearError} className="text-rose-400 hover:text-white text-xs underline">
                  Dismiss
                </button>
              </div>
            )}

            {/* TAB 1: INGESTION & LOCATION */}
            {activeTabSection === 'source' && (
              <div className="space-y-6">
                {/* 1. Ingestion Source Selector */}
                <div className="space-y-3">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-bold uppercase tracking-wider text-slate-300 font-mono">
                      1. Telemetry Ingestion Source
                    </span>
                    <span className="text-[10px] font-mono text-slate-400">
                      {isSwitchingSource ? 'Switching Ingest Stream...' : 'Click card to activate'}
                    </span>
                  </div>

                  <div className="space-y-2.5">
                    {/* Simulated AWS */}
                    <div
                      onClick={() => changeSource('SIMULATED')}
                      className={`p-3.5 rounded-xl border cursor-pointer transition-all ${
                        activeSource === 'SIMULATED'
                          ? 'bg-[#152033] border-amber-500/60 ring-1 ring-amber-500/40 shadow-lg'
                          : 'bg-[#10192A] border-[#263B5E] hover:border-slate-500'
                      }`}
                    >
                      <div className="flex items-start justify-between">
                        <div className="flex items-center gap-2.5">
                          <div className="p-1.5 rounded-lg bg-[#1B2A44] border border-amber-500/40">
                            {getSourceIcon('SIMULATED')}
                          </div>
                          <div>
                            <div className="flex items-center gap-2">
                              <span className="text-xs font-bold text-white font-mono">Simulated AWS Engine</span>
                              {activeSource === 'SIMULATED' && (
                                <span className="text-[10px] font-mono px-2 py-0.2 bg-amber-500/20 text-amber-300 border border-amber-500/40 rounded font-bold">
                                  ACTIVE
                                </span>
                              )}
                            </div>
                            <p className="text-[11px] text-slate-400 mt-0.5">
                              Deterministic diurnal solar generator with WMO-compliant boundary physics
                            </p>
                          </div>
                        </div>
                        <StatusBadge
                          label={activeSource === 'SIMULATED' ? 'RUNNING' : 'STANDBY'}
                          variant={activeSource === 'SIMULATED' ? 'warning' : 'neutral'}
                          size="sm"
                        />
                      </div>
                    </div>

                    {/* Open-Meteo Live Feed */}
                    <div
                      onClick={() => changeSource('EXTERNAL_API')}
                      className={`p-3.5 rounded-xl border cursor-pointer transition-all ${
                        activeSource === 'EXTERNAL_API'
                          ? 'bg-[#152033] border-sky-400 ring-1 ring-sky-400/40 shadow-lg'
                          : 'bg-[#10192A] border-[#263B5E] hover:border-slate-500'
                      }`}
                    >
                      <div className="flex items-start justify-between">
                        <div className="flex items-center gap-2.5">
                          <div className="p-1.5 rounded-lg bg-[#1B2A44] border border-sky-500/40">
                            {getSourceIcon('EXTERNAL_API')}
                          </div>
                          <div>
                            <div className="flex items-center gap-2">
                              <span className="text-xs font-bold text-white font-mono">Open-Meteo Live Feed</span>
                              {activeSource === 'EXTERNAL_API' && (
                                <span className="text-[10px] font-mono px-2 py-0.2 bg-sky-500/20 text-sky-300 border border-sky-500/40 rounded font-bold">
                                  ACTIVE
                                </span>
                              )}
                            </div>
                            <p className="text-[11px] text-slate-400 mt-0.5">
                              Live surface synoptic weather observation queried from global atmospheric reanalysis
                            </p>
                          </div>
                        </div>
                        <StatusBadge
                          label={activeSource === 'EXTERNAL_API' ? 'LIVE SYNC' : 'READY'}
                          variant={activeSource === 'EXTERNAL_API' ? 'nominal' : 'neutral'}
                          size="sm"
                        />
                      </div>
                    </div>

                    {/* Physical ESP32 Hardware */}
                    <div
                      onClick={() => changeSource('PHYSICAL_AWS')}
                      className={`p-3.5 rounded-xl border cursor-pointer transition-all ${
                        activeSource === 'PHYSICAL_AWS'
                          ? 'bg-[#152033] border-emerald-400 ring-1 ring-emerald-400/40 shadow-lg'
                          : 'bg-[#10192A] border-[#263B5E] hover:border-slate-500'
                      }`}
                    >
                      <div className="flex items-start justify-between">
                        <div className="flex items-center gap-2.5">
                          <div className="p-1.5 rounded-lg bg-[#1B2A44] border border-emerald-500/40">
                            {getSourceIcon('PHYSICAL_AWS')}
                          </div>
                          <div>
                            <div className="flex items-center gap-2">
                              <span className="text-xs font-bold text-white font-mono">Physical ESP32 Transceiver</span>
                              {activeSource === 'PHYSICAL_AWS' && (
                                <span className="text-[10px] font-mono px-2 py-0.2 bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 rounded font-bold">
                                  ACTIVE
                                </span>
                              )}
                            </div>
                            <p className="text-[11px] text-slate-400 mt-0.5">
                              Hardware serial transceiver & virtual packet ingestion socket (:8899)
                            </p>
                          </div>
                        </div>
                        <StatusBadge
                          label={activeSource === 'PHYSICAL_AWS' ? 'CONNECTED' : 'STANDBY'}
                          variant={activeSource === 'PHYSICAL_AWS' ? 'nominal' : 'neutral'}
                          size="sm"
                        />
                      </div>
                    </div>
                  </div>
                </div>

                {/* 2. Synoptic Station Climate Site Presets (Open-Meteo) */}
                <div className="space-y-3 pt-3 border-t border-[#263B5E]">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-bold uppercase tracking-wider text-slate-300 font-mono flex items-center gap-1.5">
                      <MapPin className="w-3.5 h-3.5 text-sky-400" />
                      2. Synoptic Observation Location
                    </span>
                    {isConfiguringCity && (
                      <span className="text-[11px] text-sky-400 font-mono flex items-center gap-1">
                        <RefreshCw className="w-3 h-3 animate-spin" /> Fetching Live Coordinates...
                      </span>
                    )}
                  </div>
                  <p className="text-[11px] text-slate-400">
                    Selecting a location configures backend coordinates, triggers an immediate Open-Meteo live query, and centers the 3D Earth digital twin.
                  </p>

                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
                    {CITY_PRESETS.map((city) => {
                      const isSelected = selectedCityId === city.id;
                      return (
                        <button
                          key={city.id}
                          onClick={() => changeCity(city.id)}
                          disabled={isConfiguringCity}
                          className={`p-3 rounded-xl border text-left transition-all relative ${
                            isSelected
                              ? 'bg-sky-500/20 border-sky-400 text-white shadow-md ring-1 ring-sky-400/40'
                              : 'bg-[#10192A] border-[#263B5E] text-slate-300 hover:bg-[#1B2A44] hover:text-white'
                          }`}
                        >
                          <div className="flex items-center justify-between">
                            <span className="font-bold text-xs font-mono">{city.name}</span>
                            <span className="text-[10px] font-mono text-slate-400">{city.country}</span>
                          </div>
                          <div className="text-[10px] font-mono text-slate-400 mt-1">
                            {city.latitude.toFixed(4)}°N, {city.longitude.toFixed(4)}°E
                          </div>
                          <div className="text-[10px] text-slate-400 truncate mt-1" title={city.description}>
                            {city.description}
                          </div>
                          {isSelected && (
                            <div className="absolute top-2.5 right-2 text-sky-400">
                              <Check className="w-4 h-4" />
                            </div>
                          )}
                        </button>
                      );
                    })}
                  </div>
                </div>

                {/* 3. Mode Specific Details */}
                {activeSource === 'SIMULATED' && (
                  <div className="p-4 bg-[#10192A] border border-[#263B5E] rounded-xl space-y-3 text-xs font-mono">
                    <div className="flex items-center justify-between">
                      <span className="font-bold text-white uppercase">Simulation Stream Controls</span>
                      <span className="text-amber-400">Interval: 1.5s</span>
                    </div>
                    <div className="flex items-center gap-3">
                      <button
                        onClick={handleToggleSimulation}
                        disabled={simLoading}
                        className="px-3 py-1.5 bg-amber-500/20 hover:bg-amber-500/30 border border-amber-500/40 text-amber-200 rounded-lg font-bold transition-all flex items-center gap-1.5"
                      >
                        {simRunning ? (
                          <>
                            <Square className="w-3.5 h-3.5 fill-current" /> Pause Generator
                          </>
                        ) : (
                          <>
                            <Play className="w-3.5 h-3.5 fill-current" /> Start Generator
                          </>
                        )}
                      </button>
                      <span className="text-slate-400 text-[11px]">Cycles continuous diurnal cycles</span>
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* TAB 2: DISPLAY & OPERATOR PREFERENCES */}
            {activeTabSection === 'display' && (
              <div className="space-y-6">
                {/* Display Density */}
                <div className="space-y-3">
                  <span className="text-xs font-bold uppercase tracking-wider text-slate-300 font-mono flex items-center gap-1.5">
                    <Laptop className="w-3.5 h-3.5 text-sky-400" />
                    Display Density Mode
                  </span>
                  <div className="grid grid-cols-3 gap-2 text-xs font-mono">
                    {(['comfortable', 'compact', 'operator'] as DisplayDensity[]).map((d) => (
                      <button
                        key={d}
                        onClick={() => updatePreferences({ displayDensity: d })}
                        className={`p-3 rounded-xl border capitalize text-center transition-all ${
                          preferences.displayDensity === d
                            ? 'bg-sky-500/20 border-sky-400 text-white font-bold ring-1 ring-sky-400/40'
                            : 'bg-[#10192A] border-[#263B5E] text-slate-400 hover:text-slate-200'
                        }`}
                      >
                        {d}
                      </button>
                    ))}
                  </div>
                  <p className="text-[11px] text-slate-400 font-sans">
                    <strong>Comfortable:</strong> Generous whitespace for multi-monitor operations (Recommended).
                  </p>
                </div>

                {/* Animation Preferences */}
                <div className="space-y-3 pt-3 border-t border-[#263B5E]">
                  <span className="text-xs font-bold uppercase tracking-wider text-slate-300 font-mono">
                    Motion & Transitions
                  </span>
                  <div className="flex items-center justify-between p-3 bg-[#10192A] border border-[#263B5E] rounded-xl text-xs font-mono">
                    <div>
                      <span className="text-white font-bold block">Reduced Motion</span>
                      <span className="text-slate-400 text-[11px]">Minimize UI transitions and 3D Earth auto-spin</span>
                    </div>
                    <button
                      onClick={() => updatePreferences({ reducedMotion: !preferences.reducedMotion })}
                      className={`w-11 h-6 rounded-full transition-colors relative ${
                        preferences.reducedMotion ? 'bg-sky-500' : 'bg-slate-700'
                      }`}
                    >
                      <span
                        className={`w-4 h-4 rounded-full bg-white absolute top-1 transition-transform ${
                          preferences.reducedMotion ? 'left-6' : 'left-1'
                        }`}
                      />
                    </button>
                  </div>
                </div>

                {/* Default Operational View */}
                <div className="space-y-3 pt-3 border-t border-[#263B5E]">
                  <span className="text-xs font-bold uppercase tracking-wider text-slate-300 font-mono">
                    Default Landing View
                  </span>
                  <select
                    value={preferences.defaultView}
                    onChange={(e) => updatePreferences({ defaultView: e.target.value as any })}
                    className="w-full bg-[#10192A] border border-[#263B5E] text-slate-200 text-xs rounded-xl p-2.5 font-mono focus:outline-none focus:border-sky-500 font-bold"
                  >
                    <option value="overview">Command Center (Overview)</option>
                    <option value="live">Live Telemetry Console</option>
                    <option value="alerts">Alert Incident Center</option>
                    <option value="health">Sensor Health Assessment</option>
                    <option value="events">Event Forensics</option>
                    <option value="explorer">Historical Data Explorer</option>
                  </select>
                </div>
              </div>
            )}

            {/* TAB 3: SYSTEM HEALTH DIAGNOSTICS */}
            {activeTabSection === 'diagnostics' && (
              <div className="space-y-4 text-xs font-mono">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-bold uppercase tracking-wider text-slate-300 font-mono flex items-center gap-1.5">
                    <Activity className="w-3.5 h-3.5 text-sky-400" />
                    Operational Link & Engine Diagnostics
                  </span>
                  <span className="text-[10px] text-slate-400">Continuous Sub-Second Health</span>
                </div>

                <div className="space-y-2">
                  <div className="p-3 bg-[#10192A] border border-[#263B5E] rounded-xl flex items-center justify-between">
                    <div>
                      <span className="text-white font-bold block">WebSocket Stream</span>
                      <span className="text-slate-400 text-[10px]">Endpoint: /ws/live (Bidirectional)</span>
                    </div>
                    <StatusBadge label={systemHealth.websocket} variant="nominal" size="sm" pulse={true} />
                  </div>

                  <div className="p-3 bg-[#10192A] border border-[#263B5E] rounded-xl flex items-center justify-between">
                    <div>
                      <span className="text-white font-bold block">FastAPI REST Server</span>
                      <span className="text-slate-400 text-[10px]">Port: 8899 • Async I/O Ingest</span>
                    </div>
                    <StatusBadge label={systemHealth.restApi} variant="nominal" size="sm" />
                  </div>

                  <div className="p-3 bg-[#10192A] border border-[#263B5E] rounded-xl flex items-center justify-between">
                    <div>
                      <span className="text-white font-bold block">SQLite Storage Layer</span>
                      <span className="text-slate-400 text-[10px]">WAL Mode Enabled • Zero Locking</span>
                    </div>
                    <StatusBadge label={systemHealth.databaseWal} variant="nominal" size="sm" />
                  </div>

                  <div className="p-3 bg-[#10192A] border border-[#263B5E] rounded-xl flex items-center justify-between">
                    <div>
                      <span className="text-white font-bold block">5-Tier ML Inference Engine</span>
                      <span className="text-slate-400 text-[10px]">WMO QC • Isolation Forest • GRU AE</span>
                    </div>
                    <StatusBadge label={systemHealth.mlEngine} variant="nominal" size="sm" />
                  </div>

                  <div className="p-3 bg-[#10192A] border border-[#263B5E] rounded-xl flex items-center justify-between">
                    <div>
                      <span className="text-white font-bold block">Open-Meteo Synoptic API</span>
                      <span className="text-slate-400 text-[10px]">Active Synoptic Site: {selectedCityId.toUpperCase()}</span>
                    </div>
                    <StatusBadge label={systemHealth.openMeteo} variant="info" size="sm" />
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* Drawer Footer */}
          <div className="p-4 border-t border-[#263B5E] bg-[#152033] flex items-center justify-between font-mono text-xs">
            <span className="text-slate-400 text-[11px]">Preferences persisted in local storage</span>
            <button
              onClick={closeSettings}
              className="px-4 py-2 bg-sky-500 hover:bg-sky-400 text-slate-950 font-bold rounded-lg transition-all shadow"
            >
              Done
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

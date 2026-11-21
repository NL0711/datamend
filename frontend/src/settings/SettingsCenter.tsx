/**
 * frontend/src/settings/SettingsCenter.tsx
 * DataMend — display preferences and live-source drawer (restored in slice S2b from commit ab3b0b3).
 * Opened from the source chip in the header and from the Settings page. Three sections: live data source and Open-Meteo site, display
 * preferences, and link diagnostics. Changed against the original: the NOAA ISD card is gone (S1), Weather Union and ESP32 are listed
 * (S3), and the diagnostics only show what the browser can know (the socket and the data-source endpoints); the original's fixed
 * "HEALTHY / READY" rows for the API, storage and a 5-tier engine are removed because nothing measured them.
 */

import React, { useState } from 'react';
import { useSystemConfiguration } from '../context/SystemConfigurationContext';
import { CITY_PRESETS, DataSourceType, DefaultView, DisplayDensity } from '../types';
import { StatusBadge } from '../design-system/components/StatusBadge';
import { startSimulation, stopSimulation, getSimulationStatus, isNotBuilt } from '../services/api';

const SOURCES: { type: DataSourceType; code: string; title: string; text: string; ring: string }[] = [
  { type: 'EXTERNAL_API', code: 'EXT', title: 'Open-Meteo Global Weather API (live REST)', text: 'Model-based temperature, pressure and humidity polled for the chosen site.', ring: 'border-sky-500 ring-sky-500/40' },
  { type: 'WEATHER_UNION', code: 'WU', title: 'Weather Union', text: 'Gauge network answering by live field; pressure is never present and is reported as not run.', ring: 'border-cyan-500 ring-cyan-500/40' },
  { type: 'PHYSICAL_AWS', code: 'HW', title: 'Physical AWS (ESP32 over MQTT)', text: 'A hardware station that publishes its own readings.', ring: 'border-emerald-500 ring-emerald-500/40' },
];

const VIEWS: { id: DefaultView; label: string }[] = [
  { id: 'overview', label: 'Overview' },
  { id: 'live', label: 'Live' },
  { id: 'alerts', label: 'Alerts' },
  { id: 'events', label: 'Events' },
  { id: 'explorer', label: 'Explorer' },
  { id: 'review', label: 'Review' },
];

export const SettingsCenter: React.FC = () => {
  const {
    activeSource,
    selectedCityId,
    isSettingsOpen,
    isConfiguringCity,
    isSwitchingSource,
    sourcesAvailable,
    streamConnected,
    error,
    preferences,
    closeSettings,
    changeSource,
    changeCity,
    updatePreferences,
    clearError,
  } = useSystemConfiguration();

  const [activeTabSection, setActiveTabSection] = useState<'source' | 'display' | 'diagnostics'>('source');
  const [simLoading, setSimLoading] = useState<boolean>(false);
  const [simRunning, setSimRunning] = useState<boolean | null>(null);
  const [simNote, setSimNote] = useState<string | null>(null);

  if (!isSettingsOpen) return null;

  const handleToggleSimulation = async () => {
    setSimLoading(true);
    setSimNote(null);
    try {
      if (simRunning) {
        await stopSimulation();
      } else {
        await startSimulation();
      }
      const st = await getSimulationStatus();
      setSimRunning(st.running);
    } catch (err) {
      setSimNote(isNotBuilt(err) ? 'The simulator endpoints are not built yet (planned in slice S3).' : err instanceof Error ? err.message : String(err));
    } finally {
      setSimLoading(false);
    }
  };

  const tabClass = (on: boolean) =>
    `pb-2.5 px-2 border-b-2 font-bold transition-all ${on ? 'border-sky-400 text-slate-900' : 'border-transparent text-slate-500 hover:text-slate-700'}`;

  return (
    <div className="fixed inset-0 z-50 overflow-hidden select-none">
      {/* Backdrop overlay */}
      <div onClick={closeSettings} className="absolute inset-0 bg-slate-900/40 backdrop-blur-sm transition-opacity" />

      {/* Slide-out Settings Drawer */}
      <div className="absolute inset-y-0 right-0 max-w-full flex pl-10">
        <div className="w-screen max-w-xl bg-[#FFFFFF] border-l border-[#D3DCE7] shadow-2xl flex flex-col justify-between text-slate-900 font-sans">
          {/* Drawer Header */}
          <div className="p-5 border-b border-[#D3DCE7] bg-[#FFFFFF] flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="p-2 rounded-lg bg-[#EDF1F7] border border-sky-500/40 text-sky-600" />
              <div>
                <h2 className="text-sm font-bold text-slate-900 uppercase tracking-wider font-mono">
                  Display and live source
                </h2>
                <p className="text-[11px] text-slate-500">
                  Live data source, Open-Meteo site and operator preferences
                </p>
              </div>
            </div>

            <button
              onClick={closeSettings}
              className="px-2.5 py-1.5 rounded-lg text-xs font-mono text-slate-500 hover:text-slate-900 hover:bg-[#EDF1F7] transition-colors"
              title="Close"
            >
              Close
            </button>
          </div>

          {/* Section Navigation Tabs */}
          <div className="px-5 pt-3 pb-0 bg-[#FFFFFF] border-b border-[#D3DCE7] flex items-center gap-2 font-mono text-xs">
            <button onClick={() => setActiveTabSection('source')} className={tabClass(activeTabSection === 'source')}>
              Data Ingestion & Location
            </button>
            <button onClick={() => setActiveTabSection('display')} className={tabClass(activeTabSection === 'display')}>
              Display & Preferences
            </button>
            <button onClick={() => setActiveTabSection('diagnostics')} className={tabClass(activeTabSection === 'diagnostics')}>
              Link Diagnostics
            </button>
          </div>

          {/* Scrollable Content Body */}
          <div className="flex-1 overflow-y-auto p-5 space-y-6">
            {error && (
              <div className="p-3 bg-rose-500/15 border border-rose-500/40 rounded-xl text-rose-800 font-semibold text-xs flex items-center justify-between font-mono">
                <div className="flex items-center gap-2">
                  <span>{error}</span>
                </div>
                <button onClick={clearError} className="text-rose-700 hover:text-slate-900 text-xs underline font-bold">
                  Dismiss
                </button>
              </div>
            )}

            {/* TAB 1: INGESTION & LOCATION */}
            {activeTabSection === 'source' && (
              <div className="space-y-6">
                {!sourcesAvailable && (
                  <div className="p-3 bg-[#F4F6FA] border border-dashed border-[#D3DCE7] rounded-xl text-xs text-slate-700 font-sans">
                    <b className="font-mono">No live stream connected.</b> The data-source endpoints are not built yet (planned in slice S3), so
                    nothing below can be switched and no source is shown as active.
                  </div>
                )}

                {/* 1. Ingestion Source Selector */}
                <div className="space-y-3">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-bold uppercase tracking-wider text-slate-600 font-mono">
                      1. Telemetry Ingestion Source
                    </span>
                    <span className="text-[10px] font-mono text-slate-500">
                      {isSwitchingSource ? 'Switching Ingest Stream...' : 'Click card to activate'}
                    </span>
                  </div>

                  <div className="space-y-2.5">
                    {SOURCES.map((s) => {
                      const on = activeSource === s.type;
                      return (
                        <div
                          key={s.type}
                          onClick={() => changeSource(s.type)}
                          className={`p-3.5 rounded-xl border cursor-pointer transition-all ${
                            on ? `bg-[#FFFFFF] ${s.ring} ring-1 shadow-lg` : 'bg-[#F4F6FA] border-[#D3DCE7] hover:border-slate-500'
                          }`}
                        >
                          <div className="flex items-start justify-between">
                            <div className="flex items-center gap-2.5">
                              <div className="p-1.5 rounded-lg bg-[#EDF1F7] border border-[#D3DCE7]">
                                <span className="text-[10px] font-bold text-slate-600 font-mono">{s.code}</span>
                              </div>
                              <div>
                                <span className="text-xs font-bold text-slate-900 font-mono">{s.title}</span>
                                <p className="text-[11px] text-slate-500 mt-0.5">{s.text}</p>
                              </div>
                            </div>
                            <StatusBadge label={on ? 'ACTIVE STREAM' : 'AVAILABLE'} variant={on ? 'nominal' : 'neutral'} size="sm" />
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>

                {/* 2. Open-Meteo site presets */}
                <div className="space-y-3 pt-3 border-t border-[#D3DCE7]">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-bold uppercase tracking-wider text-slate-600 font-mono flex items-center gap-1.5">
                      2. Open-Meteo Observation Site
                    </span>
                    {isConfiguringCity && (
                      <span className="text-[11px] text-sky-600 font-mono flex items-center gap-1">Fetching Coordinates...</span>
                    )}
                  </div>

                  <p className="text-[11px] text-slate-500">
                    Choosing a site tells the backend which coordinates the Open-Meteo source polls (used when Open-Meteo is the active source).
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
                              ? 'bg-sky-500/20 border-sky-400 text-slate-900 shadow-md ring-1 ring-sky-400/40'
                              : 'bg-[#F4F6FA] border-[#D3DCE7] text-slate-600 hover:bg-[#EDF1F7] hover:text-slate-900'
                          }`}
                        >
                          <div className="flex items-center justify-between">
                            <span className="font-bold text-xs font-mono">{city.name}</span>
                            <span className="text-[10px] font-mono text-slate-500">{city.country}</span>
                          </div>
                          <div className="text-[10px] font-mono text-slate-500 mt-1">
                            {city.latitude.toFixed(4)}°N, {city.longitude.toFixed(4)}°E
                          </div>
                          <div className="text-[10px] text-slate-500 truncate mt-1" title={city.description}>
                            {city.description}
                          </div>
                          {isSelected && <div className="absolute top-2.5 right-2 text-sky-600 font-bold text-xs">✓</div>}
                        </button>
                      );
                    })}
                  </div>
                </div>

                {/* 3. Mode Specific Details */}
                {activeSource === 'SIMULATED' && (
                  <div className="p-4 bg-[#F4F6FA] border border-[#D3DCE7] rounded-xl space-y-3 text-xs font-mono">
                    <div className="flex items-center justify-between">
                      <span className="font-bold text-slate-900 uppercase">Simulation Stream Controls</span>
                    </div>
                    <div className="flex items-center gap-3">
                      <button
                        onClick={handleToggleSimulation}
                        disabled={simLoading}
                        className="px-3.5 py-1.5 bg-amber-500/20 hover:bg-amber-500/30 border border-amber-500/40 text-amber-800 rounded-lg font-bold transition-all flex items-center gap-1.5"
                      >
                        {simRunning ? 'Pause Generator' : 'Start Generator'}
                      </button>
                    </div>
                    {simNote && <p className="text-[11px] text-rose-700">{simNote}</p>}
                  </div>
                )}
              </div>
            )}

            {/* TAB 2: DISPLAY & OPERATOR PREFERENCES */}
            {activeTabSection === 'display' && (
              <div className="space-y-6">
                <div className="space-y-3">
                  <span className="text-xs font-bold uppercase tracking-wider text-slate-600 font-mono flex items-center gap-1.5">
                    Display Density Mode
                  </span>
                  <div className="grid grid-cols-3 gap-2 text-xs font-mono">
                    {(['comfortable', 'compact', 'operator'] as DisplayDensity[]).map((d) => (
                      <button
                        key={d}
                        onClick={() => updatePreferences({ displayDensity: d })}
                        className={`p-3 rounded-xl border capitalize text-center transition-all ${
                          preferences.displayDensity === d
                            ? 'bg-sky-500/20 border-sky-400 text-slate-900 font-bold ring-1 ring-sky-400/40'
                            : 'bg-[#F4F6FA] border-[#D3DCE7] text-slate-500 hover:text-slate-700'
                        }`}
                      >
                        {d}
                      </button>
                    ))}
                  </div>
                  <p className="text-[11px] text-slate-500 font-sans">
                    <strong>Comfortable:</strong> generous whitespace (default). <strong>Compact</strong> and <strong>operator</strong> tighten the page padding.
                  </p>
                </div>

                <div className="space-y-3 pt-3 border-t border-[#D3DCE7]">
                  <span className="text-xs font-bold uppercase tracking-wider text-slate-600 font-mono">Motion & Transitions</span>
                  <div className="flex items-center justify-between p-3 bg-[#F4F6FA] border border-[#D3DCE7] rounded-xl text-xs font-mono">
                    <div>
                      <span className="text-slate-900 font-bold block">Reduced Motion</span>
                      <span className="text-slate-500 text-[11px]">Stops the globe's auto-spin</span>
                    </div>
                    <button
                      onClick={() => updatePreferences({ reducedMotion: !preferences.reducedMotion })}
                      className={`w-11 h-6 rounded-full transition-colors relative ${preferences.reducedMotion ? 'bg-sky-500' : 'bg-slate-300'}`}
                      aria-pressed={preferences.reducedMotion}
                      aria-label="Reduced motion"
                    >
                      <span
                        className={`w-4 h-4 rounded-full bg-white absolute top-1 transition-transform ${preferences.reducedMotion ? 'left-6' : 'left-1'}`}
                      />
                    </button>
                  </div>
                </div>

                <div className="space-y-3 pt-3 border-t border-[#D3DCE7]">
                  <span className="text-xs font-bold uppercase tracking-wider text-slate-600 font-mono">Default Landing View</span>
                  <select
                    value={preferences.defaultView}
                    onChange={(e) => updatePreferences({ defaultView: e.target.value as DefaultView })}
                    className="w-full bg-[#F4F6FA] border border-[#D3DCE7] text-slate-700 text-xs rounded-xl p-2.5 font-mono focus:outline-none focus:border-sky-500 font-bold"
                  >
                    {VIEWS.map((v) => (
                      <option key={v.id} value={v.id}>{v.label}</option>
                    ))}
                  </select>
                  <p className="text-[11px] text-slate-500 font-sans">Opens when the dashboard is started without a page in the address.</p>
                </div>
              </div>
            )}

            {/* TAB 3: LINK DIAGNOSTICS */}
            {activeTabSection === 'diagnostics' && (
              <div className="space-y-4 text-xs font-mono">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-bold uppercase tracking-wider text-slate-600 font-mono flex items-center gap-1.5">
                    What this browser can see
                  </span>
                </div>

                <div className="space-y-2">
                  <div className="p-3 bg-[#F4F6FA] border border-[#D3DCE7] rounded-xl flex items-center justify-between">
                    <div>
                      <span className="text-slate-900 font-bold block">WebSocket Stream</span>
                      <span className="text-slate-500 text-[10px]">Endpoint: /ws/live (built in slice S3)</span>
                    </div>
                    <StatusBadge label={streamConnected ? 'CONNECTED' : 'NOT CONNECTED'} variant={streamConnected ? 'nominal' : 'neutral'} size="sm" pulse={streamConnected} />
                  </div>

                  <div className="p-3 bg-[#F4F6FA] border border-[#D3DCE7] rounded-xl flex items-center justify-between">
                    <div>
                      <span className="text-slate-900 font-bold block">Data-source endpoints</span>
                      <span className="text-slate-500 text-[10px]">GET /api/data-sources (built in slice S3)</span>
                    </div>
                    <StatusBadge label={sourcesAvailable ? 'ANSWERING' : 'NOT BUILT YET'} variant={sourcesAvailable ? 'nominal' : 'neutral'} size="sm" />
                  </div>
                </div>

                <p className="text-[11px] text-slate-500 font-sans">
                  The server's own health (database, checks, scorer) is not reported here: there is no health endpoint that measures them yet.
                </p>
              </div>
            )}
          </div>

          {/* Drawer Footer */}
          <div className="p-4 border-t border-[#D3DCE7] bg-[#FFFFFF] flex items-center justify-between font-mono text-xs">
            <span className="text-slate-500 text-[11px]">Preferences are kept in this browser's local storage</span>
            <button onClick={closeSettings} className="px-4 py-2 bg-sky-500 hover:bg-sky-400 text-slate-950 font-bold rounded-lg transition-all shadow">
              Done
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

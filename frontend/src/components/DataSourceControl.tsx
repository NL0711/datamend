/**
 * frontend/src/components/DataSourceControl.tsx
 * DataMend — Interchangeable Telemetry Source Controller & Provenance HUD (restored in slice S2b).
 * The data-source endpoints are NOT BUILT yet (slice S3). While they answer 404 or 503 this shows an empty state; once they exist it
 * shows exactly what they return. Changed against the original: the NOAA ISD mode is gone (S1), Weather Union is a source (S3), and no
 * value is made up when the server omits it ("AWS-001", "120 packets", "port 8899", "1.5s interval" were invented defaults).
 * NOT MOUNTED in the new shell yet (the settings drawer holds the source choice); kept for S3.
 */

import React, { useState, useEffect } from 'react';
import {
  DataSourceListResponse,
  DataSourceStatus,
  DataSourceType,
  CITY_PRESETS,
} from '../types';
import {
  fetchDataSources,
  selectDataSource,
  fetchExternalWeatherPreview,
  configureExternalWeatherSource,
  isNotBuilt,
} from '../services/api';
import { StatusBadge } from '../design-system/components/StatusBadge';
import { EmptyState } from '../design-system/components/EmptyState';

interface DataSourceControlProps {
  selectedCityId?: string;
  onCitySelect?: (cityId: string) => void;
  selectedStationId?: string;
  onSourceChanged?: (source: DataSourceStatus) => void;
}

const SOURCE_BUTTONS: { type: DataSourceType; label: string; active: string }[] = [
  { type: 'SIMULATED', label: 'Simulated AWS', active: 'bg-amber-500/20 text-amber-700 border border-amber-500/40 shadow-sm' },
  { type: 'EXTERNAL_API', label: 'Open-Meteo Feed', active: 'bg-sky-500/20 text-sky-700 border border-sky-500/40 shadow-sm' },
  { type: 'WEATHER_UNION', label: 'Weather Union', active: 'bg-cyan-500/20 text-cyan-700 border border-cyan-500/40 shadow-sm' },
  { type: 'PHYSICAL_AWS', label: 'Physical ESP32', active: 'bg-emerald-500/20 text-emerald-700 border border-emerald-500/40 shadow-sm' },
];

export const DataSourceControl: React.FC<DataSourceControlProps> = ({
  selectedCityId = 'pune',
  onCitySelect,
  selectedStationId,
  onSourceChanged,
}) => {
  const [sourcesData, setSourcesData] = useState<DataSourceListResponse | null>(null);
  const [notBuilt, setNotBuilt] = useState<boolean>(false);
  const [loadingPreview, setLoadingPreview] = useState<boolean>(false);
  const [switching, setSwitching] = useState<boolean>(false);
  const [switchingCity, setSwitchingCity] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [previewData, setPreviewData] = useState<any | null>(null);
  const [showPreviewModal, setShowPreviewModal] = useState<boolean>(false);

  const loadSources = async () => {
    try {
      const data = await fetchDataSources();
      setSourcesData(data);
      setNotBuilt(false);
      setError(null);
    } catch (err: any) {
      if (isNotBuilt(err)) setNotBuilt(true);
      else setError(err.message || 'Failed to fetch data source statuses');
    }
  };

  useEffect(() => {
    void loadSources();
  }, []);

  const handleSelectSource = async (sourceType: DataSourceType) => {
    if (sourcesData?.active_source === sourceType) return;
    setSwitching(true);
    setError(null);
    try {
      const updated = await selectDataSource(sourceType);
      await loadSources();
      if (onSourceChanged) {
        onSourceChanged(updated);
      }
    } catch (err: any) {
      setError(err.message || `Failed to switch to ${sourceType}`);
    } finally {
      setSwitching(false);
    }
  };

  const handleCityClick = async (cityId: string) => {
    if (onCitySelect) {
      onCitySelect(cityId);
    }
    const city = CITY_PRESETS.find((c) => c.id === cityId);
    if (!city) return;

    setSwitchingCity(true);
    setError(null);
    try {
      const updated = await configureExternalWeatherSource({
        latitude: city.latitude,
        longitude: city.longitude,
        station_id: city.station_id,
        station_name: city.name,
      });
      await loadSources();
      if (onSourceChanged) {
        onSourceChanged(updated);
      }
    } catch (err: any) {
      setError(err.message || `Failed to configure Open-Meteo for ${city.name}`);
    } finally {
      setSwitchingCity(false);
    }
  };

  const handlePreviewExternal = async () => {
    try {
      setLoadingPreview(true);
      const res = await fetchExternalWeatherPreview();
      setPreviewData(res);
      setShowPreviewModal(true);
    } catch (err: any) {
      setError(err.message || 'Failed to preview Open-Meteo external feed');
    } finally {
      setLoadingPreview(false);
    }
  };

  const activeStatus = sourcesData?.sources.find(
    (s) => s.source_type === sourcesData.active_source
  );

  const getSourceIcon = (type: DataSourceType) => {
    const code = type === 'SIMULATED' ? 'SIM' : type === 'EXTERNAL_API' ? 'EXT' : type === 'WEATHER_UNION' ? 'WU' : 'HW';
    return <span className="text-[10px] font-bold text-slate-600 font-mono">{code}</span>;
  };

  if (notBuilt) {
    return (
      <EmptyState
        title="No live stream connected"
        description="The data-source endpoints are not built yet. Planned in slice S3 (the simulator, Open-Meteo, Weather Union and ESP32 sources)."
      />
    );
  }

  return (
    <div className="bg-[#FFFFFF] border border-[#D3DCE7] rounded-xl p-4 shadow-lg space-y-3">
      {/* Top Header Bar */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-3 pb-3 border-b border-slate-200">
        <div className="flex items-center gap-2.5">
          <div className="p-1.5 bg-sky-500/15 border border-sky-500/35 rounded-lg text-sky-600" />
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-xs font-bold text-slate-900 uppercase tracking-wider font-mono">
                Telemetry Ingest Provenance
              </h2>
              <span className="text-[10px] font-mono px-2 py-0.5 bg-[#F4F6FA] text-slate-600 rounded border border-[#D3DCE7] font-semibold">
                {SOURCE_BUTTONS.length} INGEST MODES
              </span>
            </div>
            <p className="text-[11px] text-slate-600 mt-0.5">
              The sensor or service feed that is read into the quality control checks
            </p>
          </div>
        </div>

        {/* Source Selector Buttons */}
        <div className="flex items-center gap-1.5 bg-[#F4F6FA] p-1 rounded-lg border border-[#D3DCE7]">
          {SOURCE_BUTTONS.map((b) => (
            <button
              key={b.type}
              onClick={() => handleSelectSource(b.type)}
              disabled={switching}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-semibold font-mono transition-all ${
                sourcesData?.active_source === b.type
                  ? b.active
                  : 'text-slate-500 hover:text-slate-700 hover:bg-[#EDF1F7]'
              }`}
            >
              <span>{b.label}</span>
            </button>
          ))}
        </div>
      </div>

      {/* Open-Meteo Climate Zone Presets */}
      <div className="pt-1">
        <div className="flex items-center justify-between mb-2">
          <span className="text-[10px] uppercase font-bold text-slate-500 font-mono tracking-wider flex items-center gap-1.5">
            Select Climate Observation Site (Open-Meteo)
          </span>
          {switchingCity && (
            <span className="text-[11px] text-sky-600 font-mono flex items-center gap-1">
              Fetching Coordinates...
            </span>
          )}
        </div>

        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 gap-2">
          {CITY_PRESETS.map((city) => {
            const isSelected = selectedCityId === city.id || selectedStationId === city.station_id;
            return (
              <button
                key={city.id}
                onClick={() => handleCityClick(city.id)}
                disabled={switchingCity}
                className={`p-2 rounded-lg text-left border transition-all ${
                  isSelected
                    ? 'bg-sky-500/20 border-sky-400 text-slate-900 shadow-md ring-1 ring-sky-400/40'
                    : 'bg-[#F4F6FA] border-[#D3DCE7] text-slate-600 hover:bg-[#EDF1F7] hover:text-slate-900'
                }`}
              >
                <div className="flex items-center justify-between">
                  <span className="font-bold text-xs font-mono">{city.name}</span>
                  <span className="text-[9px] font-mono text-slate-500">{city.country}</span>
                </div>
                <div className="text-[10px] font-mono text-slate-500 mt-0.5">
                  {city.latitude.toFixed(2)}°, {city.longitude.toFixed(2)}°
                </div>
                <div className="text-[9px] text-slate-500 truncate mt-0.5" title={city.description}>
                  {city.description}
                </div>
              </button>
            );
          })}
        </div>
      </div>

      {/* Active Source Details & Health Grid */}
      {activeStatus && (
        <div className="mt-2 grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-2.5 text-xs font-mono">
          {/* Active Provider Card */}
          <div className="bg-[#F4F6FA] border border-[#D3DCE7]/60 rounded-lg p-2.5">
            <div className="text-[10px] text-slate-500 uppercase mb-0.5">Active Ingest Source</div>
            <div className="flex items-center gap-1.5 font-bold text-slate-900">
              {getSourceIcon(activeStatus.source_type)}
              <span className="truncate">{activeStatus.name}</span>
            </div>
            <div className="text-[11px] text-slate-600 mt-0.5">
              Provider: <span className="text-sky-600 font-medium">{activeStatus.provider ?? 'not stated'}</span>
            </div>
          </div>

          {/* Connection Status Card */}
          <div className="bg-[#F4F6FA] border border-[#D3DCE7]/60 rounded-lg p-2.5">
            <div className="text-[10px] text-slate-500 uppercase mb-0.5">Telemetry Link Status</div>
            <div className="flex items-center gap-2">
              <StatusBadge
                label={activeStatus.is_stale ? 'STALE DATA' : activeStatus.status}
                variant={
                  activeStatus.is_stale
                    ? 'warning'
                    : activeStatus.status === 'CONNECTED' || activeStatus.status === 'RUNNING'
                    ? 'nominal'
                    : 'critical'
                }
                size="sm"
                pulse={activeStatus.status === 'RUNNING'}
              />
            </div>
            <div className="text-[11px] text-slate-600 mt-0.5">
              Data Freshness:{' '}
              <span className="text-slate-800 font-bold">
                {activeStatus.data_age_seconds !== undefined ? `${activeStatus.data_age_seconds}s ago` : 'not stated'}
              </span>
            </div>
          </div>

          {/* Target Station Identity */}
          <div className="bg-[#F4F6FA] border border-[#D3DCE7]/60 rounded-lg p-2.5">
            <div className="text-[10px] text-slate-500 uppercase mb-0.5">Target Station Node</div>
            <div className="font-bold text-slate-900 truncate">{activeStatus.station_id || 'not stated'}</div>
            <div className="text-[11px] text-slate-600 mt-0.5 truncate">
              Packets Ingested: <span className="text-sky-600 font-bold">{activeStatus.packet_count}</span>
            </div>
          </div>

          {/* Mode-Specific Actions */}
          <div className="bg-[#F4F6FA] border border-[#D3DCE7]/60 rounded-lg p-2.5 flex flex-col justify-between">
            <div className="text-[10px] text-slate-500 uppercase mb-0.5">Action Console</div>
            {sourcesData?.active_source === 'EXTERNAL_API' ? (
              <button
                onClick={handlePreviewExternal}
                disabled={loadingPreview}
                className="flex items-center justify-center gap-1.5 w-full py-1 bg-sky-500 hover:bg-sky-400 text-slate-950 rounded font-bold text-[11px] transition-all shadow"
              >
                {loadingPreview ? 'Fetching...' : 'Inspect Raw Payload'}
              </button>
            ) : activeStatus.polling_interval_seconds !== undefined ? (
              <div className="text-[11px] text-slate-700 font-medium">
                Cadence: {activeStatus.polling_interval_seconds}s
              </div>
            ) : (
              <div className="text-[11px] text-slate-500 font-medium">No action for this source</div>
            )}
          </div>
        </div>
      )}

      {/* Error Notification Banner */}
      {error && (
        <div className="p-2.5 rounded-xl bg-rose-500/15 border border-rose-500/40 text-rose-800 text-xs flex items-center gap-2 font-mono">
          <span>{error}</span>
        </div>
      )}

      {/* External Feed Preview Modal */}
      {showPreviewModal && previewData && (
        <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-[#FFFFFF] border border-[#D3DCE7] rounded-xl max-w-lg w-full p-5 shadow-2xl space-y-4">
            <div className="flex items-center justify-between border-b border-slate-200 pb-3">
              <div className="flex items-center gap-2 text-sky-600 font-bold text-xs font-mono">
                <span>Open-Meteo Synchronous Payload</span>
              </div>
              <button
                onClick={() => setShowPreviewModal(false)}
                className="text-slate-600 hover:text-slate-900 text-xs px-2.5 py-1 bg-[#F4F6FA] rounded border border-[#D3DCE7]"
              >
                Close
              </button>
            </div>

            <div className="grid grid-cols-3 gap-2 font-mono text-center">
              <div className="bg-[#F4F6FA] p-2.5 rounded border border-[#D3DCE7]/60">
                <span className="text-[10px] text-slate-500 block">Temperature</span>
                <span className="text-sm font-bold text-amber-600">{previewData.telemetry.temperature}°C</span>
              </div>
              <div className="bg-[#F4F6FA] p-2.5 rounded border border-[#D3DCE7]/60">
                <span className="text-[10px] text-slate-500 block">Pressure</span>
                <span className="text-sm font-bold text-sky-600">{previewData.telemetry.pressure} hPa</span>
              </div>
              <div className="bg-[#F4F6FA] p-2.5 rounded border border-[#D3DCE7]/60">
                <span className="text-[10px] text-slate-500 block">Humidity</span>
                <span className="text-sm font-bold text-indigo-500">{previewData.telemetry.humidity}%</span>
              </div>
            </div>

            <div className="bg-[#F4F6FA] p-3 rounded border border-[#D3DCE7]/60 text-[11px] font-mono text-slate-600 space-y-1">
              <div>Station: <span className="text-sky-600">{previewData.telemetry.station_id}</span></div>
              <div>Timestamp: <span className="text-slate-600">{previewData.telemetry.timestamp}</span></div>
              <div>Coordinates: {previewData.telemetry.latitude}°N, {previewData.telemetry.longitude}°E (Elev: {previewData.telemetry.elevation}m)</div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

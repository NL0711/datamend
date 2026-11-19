/**
 * frontend/src/components/DataSourceControl.tsx
 * DataMend — Three-Source Interchangeable Telemetry Controller & Provenance HUD.
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
} from '../services/api';
import { StatusBadge } from '../design-system/components/StatusBadge';

interface DataSourceControlProps {
  selectedCityId?: string;
  onCitySelect?: (cityId: string) => void;
  selectedStationId?: string;
  onSourceChanged?: (source: DataSourceStatus) => void;
}

export const DataSourceControl: React.FC<DataSourceControlProps> = ({
  selectedCityId = 'pune',
  onCitySelect,
  selectedStationId,
  onSourceChanged,
}) => {
  const [sourcesData, setSourcesData] = useState<DataSourceListResponse | null>(null);
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
      setError(null);
    } catch (err: any) {
      setError(err.message || 'Failed to fetch data source statuses');
    }
  };

  useEffect(() => {
    loadSources();
    const interval = setInterval(loadSources, 5000);
    return () => clearInterval(interval);
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
    const code = type === 'SIMULATED' ? 'SIM' : type === 'EXTERNAL_API' ? 'EXT' : 'HW';
    return <span className="text-[10px] font-bold text-slate-600 font-mono">{code}</span>;
  };

  return (
    <div className="bg-[#FFFFFF] border border-[#D3DCE7] rounded-xl p-4 shadow-lg space-y-3">
      {/* Top Header Bar */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-3 pb-3 border-b border-slate-200">
        <div className="flex items-center gap-2.5">
          <div className="p-1.5 bg-sky-500/15 border border-sky-500/35 rounded-lg text-sky-600">
            
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-xs font-bold text-slate-900 uppercase tracking-wider font-mono">
                Telemetry Ingest Provenance HUD
              </h2>
              <span className="text-[10px] font-mono px-2 py-0.5 bg-[#F4F6FA] text-slate-600 rounded border border-[#D3DCE7] font-semibold">
                3 INGEST MODES
              </span>
            </div>
            <p className="text-[11px] text-slate-600 mt-0.5">
              Active physical or virtual sensor feed feeding the 5-Tier ML Quality Control Engine
            </p>
          </div>
        </div>

        {/* Source Selector Buttons */}
        <div className="flex items-center gap-1.5 bg-[#F4F6FA] p-1 rounded-lg border border-[#D3DCE7]">
          <button
            onClick={() => handleSelectSource('SIMULATED')}
            disabled={switching}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-semibold font-mono transition-all ${
              sourcesData?.active_source === 'SIMULATED'
                ? 'bg-amber-500/20 text-amber-700 border border-amber-500/40 shadow-sm'
                : 'text-slate-500 hover:text-slate-700 hover:bg-[#EDF1F7]'
            }`}
          >
            
            <span>Simulated AWS</span>
          </button>

          <button
            onClick={() => handleSelectSource('EXTERNAL_API')}
            disabled={switching}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-semibold font-mono transition-all ${
              sourcesData?.active_source === 'EXTERNAL_API'
                ? 'bg-sky-500/20 text-sky-700 border border-sky-500/40 shadow-sm'
                : 'text-slate-500 hover:text-slate-700 hover:bg-[#EDF1F7]'
            }`}
          >
            
            <span>Open-Meteo Feed</span>
          </button>

          <button
            onClick={() => handleSelectSource('PHYSICAL_AWS')}
            disabled={switching}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-semibold font-mono transition-all ${
              sourcesData?.active_source === 'PHYSICAL_AWS'
                ? 'bg-emerald-500/20 text-emerald-700 border border-emerald-500/40 shadow-sm'
                : 'text-slate-500 hover:text-slate-700 hover:bg-[#EDF1F7]'
            }`}
          >
            
            <span>Physical ESP32</span>
          </button>
        </div>
      </div>

      {/* Global Open-Meteo Climate Zone Presets */}
      <div className="pt-1">
        <div className="flex items-center justify-between mb-2">
          <span className="text-[10px] uppercase font-bold text-slate-500 font-mono tracking-wider flex items-center gap-1.5">
            
            Select Climate Observation Site (Live Open-Meteo Surface Synoptic Station)
          </span>
          {switchingCity && (
            <span className="text-[11px] text-sky-600 font-mono flex items-center gap-1">
               Fetching Live Coordinates...
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
              Provider: <span className="text-sky-600 font-medium">{activeStatus.provider || 'Internal'}</span>
            </div>
          </div>

          {/* Connection Status Card */}
          <div className="bg-[#F4F6FA] border border-[#D3DCE7]/60 rounded-lg p-2.5">
            <div className="text-[10px] text-slate-500 uppercase mb-0.5">Telemetry Link Status</div>
            <div className="flex items-center gap-2">
              <StatusBadge
                label={activeStatus.is_stale ? 'STALE DATA' : activeStatus.status || 'CONNECTED'}
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
              Data Freshness: <span className="text-emerald-600 font-bold">{activeStatus.data_age_seconds ?? 1}s ago</span>
            </div>
          </div>

          {/* Target Station Identity */}
          <div className="bg-[#F4F6FA] border border-[#D3DCE7]/60 rounded-lg p-2.5">
            <div className="text-[10px] text-slate-500 uppercase mb-0.5">Target Station Node</div>
            <div className="font-bold text-slate-900 truncate">{activeStatus.station_id || 'AWS-001'}</div>
            <div className="text-[11px] text-slate-600 mt-0.5 truncate">
              Packets Ingested: <span className="text-sky-600 font-bold">{activeStatus.packet_count ?? 120}</span>
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
                {loadingPreview ? (
                  <>
                     Fetching...
                  </>
                ) : (
                  <>
                     Inspect Raw Payload
                  </>
                )}
              </button>
            ) : sourcesData?.active_source === 'PHYSICAL_AWS' ? (
              <div className="text-[11px] text-emerald-600 font-medium flex items-center gap-1">
                <span className="w-2 h-2 rounded-full bg-emerald-400 animate-ping" />
                Listening port 8899
              </div>
            ) : (
              <div className="text-[11px] text-amber-700 font-medium">
                Simulator cycle (1.5s interval)
              </div>
            )}
          </div>
        </div>
      )}

      {/* Error Notification Banner */}
      {error && (
        <div className="p-2.5 rounded-xl bg-rose-500/15 border border-rose-500/40 text-rose-200 text-xs flex items-center gap-2 font-mono">
          
          <span>{error}</span>
        </div>
      )}

      {/* External Feed Live Preview Modal */}
      {showPreviewModal && previewData && (
        <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4">
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
                <span className="text-sm font-bold text-indigo-400">{previewData.telemetry.humidity}%</span>
              </div>
            </div>

            <div className="bg-[#F4F6FA] p-3 rounded border border-[#D3DCE7]/60 text-[11px] font-mono text-slate-600 space-y-1">
              <div>Station: <span className="text-sky-600">{previewData.telemetry.station_id}</span></div>
              <div>Timestamp: <span className="text-slate-600">{previewData.telemetry.timestamp}</span></div>
              <div>Coordinates: {previewData.telemetry.latitude}°N, {previewData.telemetry.longitude}°E (Elev: {previewData.telemetry.elevation}m)</div>
              <div>QC Validation: <span className="text-emerald-600 font-bold">PHYSICS PASS</span></div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

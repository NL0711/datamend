/**
 * frontend/src/components/DataSourceControl.tsx
 * DataMend — telemetry source controller and provenance panel (restored in slice S2b, wired in the frontend pass after S3b).
 * Mounted on the Live page. It shows exactly what GET /api/data-sources returns: the four sources, which one is active, its link state,
 * the station set, the call counters and the status metadata. Choosing a source is POST /api/data-sources/select (admin only: a 401 or
 * 403 shows a sign-in prompt), the Open-Meteo site is POST /api/data-sources/external/configure, the raw preview is one live call.
 * Changed against the original: the NOAA ISD mode is gone, Weather Union is a source, and no value is made up when the server omits it.
 */

import React, { useState, useEffect, useCallback } from 'react';
import { DataSourceListResponse, DataSourceStatus, DataSourceType, CITY_PRESETS } from '../types';
import {
  fetchDataSources,
  selectDataSource,
  fetchExternalWeatherPreview,
  configureExternalWeatherSource,
  isNotBuilt,
  isAuthError,
  errorText,
} from '../services/api';
import { describeStream, fmtAge, fmtValue } from '../services/stream';
import { StatusBadge } from '../design-system/components/StatusBadge';
import { EmptyState } from '../design-system/components/EmptyState';
import { useSystemConfiguration } from '../context/SystemConfigurationContext';
import { AuthNotice } from './AuthNotice';
import { SimulatorControls } from './SimulatorControls';

const SOURCE_BUTTONS: { type: DataSourceType; label: string; active: string }[] = [
  { type: 'SIMULATED', label: 'Simulator', active: 'bg-amber-500/20 text-amber-700 border border-amber-500/40 shadow-sm' },
  { type: 'EXTERNAL_API', label: 'Open-Meteo', active: 'bg-sky-500/20 text-sky-700 border border-sky-500/40 shadow-sm' },
  { type: 'WEATHER_UNION', label: 'Weather Union', active: 'bg-cyan-500/20 text-cyan-700 border border-cyan-500/40 shadow-sm' },
  { type: 'PHYSICAL_AWS', label: 'ESP32', active: 'bg-emerald-500/20 text-emerald-700 border border-emerald-500/40 shadow-sm' },
];

const HIDDEN_METADATA = new Set(['station_ids', 'station_set', 'stale_since']);
const short = (v: unknown): string => {
  if (v === null || v === undefined) return '—';
  if (typeof v === 'object') return JSON.stringify(v);
  return String(v);
};

/** "Bengaluru (cap 5)", "all 580 gauges", "3 chosen stations" ... from the station_set the API returns; null when it states none. */
export function stationSetWords(meta: Record<string, any> | undefined): string | null {
  const set = meta?.station_set;
  if (!set || typeof set !== 'object') return null;
  if (set.mode === 'city') return `${set.city ?? 'a city'}${set.cap ? ` (cap ${set.cap})` : ''}`;
  if (set.mode === 'all') return `all gauges${set.cap ? ` (cap ${set.cap})` : ''}`;
  if (set.mode === 'ids') return `chosen stations${set.station_ids ? ` (${set.station_ids.length})` : ''}`;
  if (set.mode === 'point') return `point ${set.station_id ?? ''}`.trim();
  return null;
}

export const DataSourceControl: React.FC = () => {
  const { streamConnected, streamStatus, refreshSources, selectedCityId } = useSystemConfiguration();
  const [sourcesData, setSourcesData] = useState<DataSourceListResponse | null>(null);
  const [notBuilt, setNotBuilt] = useState<boolean>(false);
  const [loadingPreview, setLoadingPreview] = useState<boolean>(false);
  const [switching, setSwitching] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [needsAuth, setNeedsAuth] = useState<boolean>(false);
  const [previewData, setPreviewData] = useState<any | null>(null);
  const [showPreviewModal, setShowPreviewModal] = useState<boolean>(false);
  const stream = describeStream(streamConnected, streamStatus);

  const loadSources = useCallback(async () => {
    try {
      const data = await fetchDataSources();
      setSourcesData(data);
      setNotBuilt(false);
    } catch (err) {
      if (isNotBuilt(err)) setNotBuilt(true);
      else setError(errorText(err));
    }
  }, []);

  useEffect(() => {
    void loadSources();
    const t = setInterval(() => { void loadSources(); }, 5000);
    return () => clearInterval(t);
  }, [loadSources]);

  const fail = (err: unknown) => {
    if (isAuthError(err)) setNeedsAuth(true);
    else setError(errorText(err));
  };

  const handleSelectSource = async (sourceType: DataSourceType) => {
    if (sourcesData?.active_source === sourceType) return;
    setSwitching(true); setError(null); setNeedsAuth(false);
    try {
      await selectDataSource(sourceType);
      await loadSources();
      void refreshSources();
    } catch (err) {
      fail(err);
    } finally {
      setSwitching(false);
    }
  };

  const handleCityClick = async (cityId: string) => {
    const city = CITY_PRESETS.find((c) => c.id === cityId);
    if (!city) return;
    setError(null); setNeedsAuth(false);
    try {
      await configureExternalWeatherSource({ latitude: city.latitude, longitude: city.longitude, station_id: city.station_id, station_name: city.name });
      await loadSources();
      void refreshSources();
    } catch (err) {
      fail(err);
    }
  };

  const handlePreviewExternal = async () => {
    setLoadingPreview(true); setError(null); setNeedsAuth(false);
    try {
      const res = await fetchExternalWeatherPreview();
      setPreviewData(res);
      setShowPreviewModal(true);
    } catch (err) {
      fail(err);
    } finally {
      setLoadingPreview(false);
    }
  };

  const activeStatus: DataSourceStatus | undefined = sourcesData?.sources.find((s) => s.source_type === sourcesData.active_source);
  const meta = activeStatus?.metadata ?? {};
  const stationIds: string[] = Array.isArray(meta.station_ids) ? meta.station_ids : [];

  if (notBuilt) {
    return (
      <EmptyState title="Data sources not available" description="GET /api/data-sources did not answer (404, 501, 502 or 503). No source can be chosen from here." />
    );
  }

  return (
    <div className="bg-[#FFFFFF] border border-[#D3DCE7] rounded-xl p-4 shadow-lg space-y-3">
      {/* Top header bar and the source selector */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-3 pb-3 border-b border-slate-200">
        <div>
          <h2 className="text-xs font-bold text-slate-900 uppercase tracking-wider font-mono">Telemetry source</h2>
          <p className="text-[11px] text-slate-600 mt-0.5">The feed that is read into the checks. One source runs at a time; choosing one needs an admin sign-in.</p>
        </div>

        <div className="flex flex-wrap items-center gap-1.5 bg-[#F4F6FA] p-1 rounded-lg border border-[#D3DCE7]">
          {SOURCE_BUTTONS.map((b) => {
            const entry = sourcesData?.sources.find((s) => s.source_type === b.type);
            const unavailable = entry ? !entry.is_available : false;
            return (
              <button
                key={b.type}
                onClick={() => handleSelectSource(b.type)}
                disabled={switching || unavailable}
                title={entry?.description}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-semibold font-mono transition-all disabled:opacity-50 ${
                  sourcesData?.active_source === b.type ? b.active : 'text-slate-500 hover:text-slate-700 hover:bg-[#EDF1F7]'
                }`}
              >
                <span>{b.label}</span>
              </button>
            );
          })}
        </div>
      </div>

      {needsAuth && <AuthNotice text="Choosing a source or an Open-Meteo site needs an admin sign-in." />}
      {error && (
        <div className="p-2.5 rounded-xl bg-rose-500/15 border border-rose-500/40 text-rose-800 text-xs flex items-center gap-2 font-mono">
          <span>{error}</span>
        </div>
      )}

      {/* Simulator controls */}
      <div className="p-3 bg-[#F4F6FA] border border-[#D3DCE7]/60 rounded-lg space-y-2">
        <div className="text-[10px] text-slate-500 uppercase font-mono font-bold tracking-wider">Simulator (started by the server; choose the source above)</div>
        <SimulatorControls />
      </div>

      {/* Active source details */}
      {activeStatus ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-2.5 text-xs font-mono">
          <div className="bg-[#F4F6FA] border border-[#D3DCE7]/60 rounded-lg p-2.5">
            <div className="text-[10px] text-slate-500 uppercase mb-0.5">Active source</div>
            <div className="font-bold text-slate-900 truncate" title={activeStatus.description}>{activeStatus.name}</div>
            <div className="text-[11px] text-slate-600 mt-0.5">id <span className="text-sky-600 font-medium">{activeStatus.source_id}</span></div>
            <div className="text-[11px] text-slate-600">Provider: <span className="font-medium">{activeStatus.provider ?? 'not stated'}</span></div>
          </div>

          <div className="bg-[#F4F6FA] border border-[#D3DCE7]/60 rounded-lg p-2.5">
            <div className="text-[10px] text-slate-500 uppercase mb-0.5">Link state</div>
            <StatusBadge label={stream.label} variant={stream.tone === 'nominal' ? 'nominal' : stream.tone === 'warning' ? 'warning' : stream.tone === 'critical' ? 'critical' : 'neutral'} size="sm" pulse={stream.live} />
            <div className="text-[11px] text-slate-600 mt-1">Source says: <span className="font-bold text-slate-800">{activeStatus.status}</span></div>
            <div className="text-[11px] text-slate-600">Data age: <span className="font-bold text-slate-800">{fmtAge(activeStatus.data_age_seconds)}</span></div>
          </div>

          <div className="bg-[#F4F6FA] border border-[#D3DCE7]/60 rounded-lg p-2.5">
            <div className="text-[10px] text-slate-500 uppercase mb-0.5">Counters</div>
            <div className="text-[11px] text-slate-600">Packets read: <span className="text-sky-600 font-bold">{activeStatus.packet_count}</span></div>
            <div className="text-[11px] text-slate-600">Cadence: <span className="text-slate-800 font-bold">{activeStatus.polling_interval_seconds !== undefined ? `${activeStatus.polling_interval_seconds} s` : 'not stated'}</span></div>
            {meta.calls_used_today !== undefined && (
              <div className="text-[11px] text-slate-600">API calls today: <span className="text-slate-800 font-bold">{meta.calls_used_today}</span>{meta.calls_remaining_today !== undefined && <> ({meta.calls_remaining_today} left)</>}</div>
            )}
          </div>

          <div className="bg-[#F4F6FA] border border-[#D3DCE7]/60 rounded-lg p-2.5">
            <div className="text-[10px] text-slate-500 uppercase mb-0.5">Station set</div>
            <div className="text-[11px] text-slate-800 font-bold">{stationIds.length} stations{stationSetWords(meta) ? ` · ${stationSetWords(meta)}` : ''}</div>
            <div className="text-[10px] text-slate-500 break-words mt-0.5" title={stationIds.join(', ')}>
              {stationIds.slice(0, 8).join(', ')}{stationIds.length > 8 ? ` … +${stationIds.length - 8}` : ''}
            </div>
            {activeStatus.source_type === 'EXTERNAL_API' && (
              <button onClick={handlePreviewExternal} disabled={loadingPreview} className="mt-1.5 w-full py-1 bg-sky-500 hover:bg-sky-400 text-slate-950 rounded font-bold text-[11px] shadow disabled:opacity-60">
                {loadingPreview ? 'Fetching…' : 'Preview one live call'}
              </button>
            )}
          </div>
        </div>
      ) : (
        <div className="p-3 border border-dashed border-[#D3DCE7] rounded-lg text-xs text-slate-600 font-sans">
          No source is running. Choose one above, or start the simulator.
        </div>
      )}

      {activeStatus?.error_message && (
        <div className="p-2.5 rounded-xl bg-amber-500/10 border border-amber-500/40 text-amber-900 text-xs font-mono">Source error: {activeStatus.error_message}</div>
      )}

      {/* Status metadata exactly as returned */}
      {activeStatus && Object.keys(meta).some((k) => !HIDDEN_METADATA.has(k)) && (
        <details className="text-[11px] font-mono text-slate-600">
          <summary className="cursor-pointer font-bold text-slate-700">Status metadata the API returned</summary>
          <dl className="mt-1.5 grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-0.5">
            {Object.entries(meta).filter(([k]) => !HIDDEN_METADATA.has(k)).map(([k, v]) => (
              <div key={k} className="flex gap-2 min-w-0"><dt className="text-slate-500 shrink-0">{k}:</dt><dd className="truncate" title={short(v)}>{short(v)}</dd></div>
            ))}
          </dl>
        </details>
      )}

      {/* Sources the server lists but does not run for this deployment */}
      {sourcesData?.sources.some((s) => !s.is_available) && (
        <ul className="text-[11px] text-slate-500 font-sans space-y-0.5">
          {sourcesData.sources.filter((s) => !s.is_available).map((s) => <li key={s.source_id}><b className="font-mono">{s.name}</b>: {s.description}</li>)}
        </ul>
      )}

      {/* Open-Meteo site presets */}
      <div className="pt-1">
        <div className="text-[10px] uppercase font-bold text-slate-500 font-mono tracking-wider mb-2">Open-Meteo observation site (used when Open-Meteo is the running source)</div>
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 gap-2">
          {CITY_PRESETS.map((city) => (
            <button
              key={city.id}
              onClick={() => handleCityClick(city.id)}
              className={`p-2 rounded-lg text-left border transition-all ${
                selectedCityId === city.id && activeStatus?.source_type === 'EXTERNAL_API'
                  ? 'bg-sky-500/20 border-sky-400 text-slate-900 shadow-md ring-1 ring-sky-400/40'
                  : 'bg-[#F4F6FA] border-[#D3DCE7] text-slate-600 hover:bg-[#EDF1F7] hover:text-slate-900'
              }`}
            >
              <div className="flex items-center justify-between">
                <span className="font-bold text-xs font-mono">{city.name}</span>
                <span className="text-[9px] font-mono text-slate-500">{city.country}</span>
              </div>
              <div className="text-[10px] font-mono text-slate-500 mt-0.5">{city.latitude.toFixed(2)}°, {city.longitude.toFixed(2)}°</div>
            </button>
          ))}
        </div>
      </div>

      {/* External feed preview */}
      {showPreviewModal && previewData && (
        <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-[#FFFFFF] border border-[#D3DCE7] rounded-xl max-w-lg w-full p-5 shadow-2xl space-y-4">
            <div className="flex items-center justify-between border-b border-slate-200 pb-3">
              <div className="text-sky-600 font-bold text-xs font-mono">Open-Meteo, one live call (nothing stored)</div>
              <button onClick={() => setShowPreviewModal(false)} className="text-slate-600 hover:text-slate-900 text-xs px-2.5 py-1 bg-[#F4F6FA] rounded border border-[#D3DCE7]">Close</button>
            </div>
            <div className="grid grid-cols-3 gap-2 font-mono text-center">
              <div className="bg-[#F4F6FA] p-2.5 rounded border border-[#D3DCE7]/60"><span className="text-[10px] text-slate-500 block">Temperature</span><span className="text-sm font-bold text-amber-600">{fmtValue(previewData.telemetry?.temperature, 1, ' °C')}</span></div>
              <div className="bg-[#F4F6FA] p-2.5 rounded border border-[#D3DCE7]/60"><span className="text-[10px] text-slate-500 block">Pressure</span><span className="text-sm font-bold text-sky-600">{fmtValue(previewData.telemetry?.pressure, 1, ' hPa')}</span></div>
              <div className="bg-[#F4F6FA] p-2.5 rounded border border-[#D3DCE7]/60"><span className="text-[10px] text-slate-500 block">Humidity</span><span className="text-sm font-bold text-indigo-500">{fmtValue(previewData.telemetry?.humidity, 0, ' %')}</span></div>
            </div>
            <div className="bg-[#F4F6FA] p-3 rounded border border-[#D3DCE7]/60 text-[11px] font-mono text-slate-600 space-y-1">
              <div>Station: <span className="text-sky-600">{short(previewData.telemetry?.station_id)}</span></div>
              <div>Timestamp: {short(previewData.telemetry?.timestamp)}</div>
              <div>Position: {short(previewData.telemetry?.latitude)}, {short(previewData.telemetry?.longitude)}</div>
              {previewData.telemetry?.model_estimate && <div className="text-amber-700">Model estimate, not a measurement.</div>}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

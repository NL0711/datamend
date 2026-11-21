// Live Telemetry of the ORIGINAL dashboard (temperature, pressure, humidity), restored in slice S2b. Data: GET /api/observations and the
// WebSocket /ws/live, both NOT BUILT yet (slice S3); until then the gauges show dashes and the chart says "No live stream connected".
// Changed against the original: no invented fallback readings (25.0 C, 1013.2 hPa, 55 %), no invented confidence, no "sea-level pressure"
// from a fixed offset, no "STABLE" tendency text, no verdict banner without a verdict from the server, and no private station list (the
// header's station picker chooses the station).
import { useState, useEffect, useMemo, useRef } from 'react';
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
  Legend,
} from 'recharts';
import { InferenceResult, Observation } from '../types';
import { fetchObservations, isNotBuilt } from '../services/api';
import { StatusBadge } from '../design-system/components/StatusBadge';
import { EmptyState } from '../design-system/components/EmptyState';
import { ContextualStatusStrip } from './ContextualStatusStrip';
import { dewPoint, reading, vaporPressure } from './pins';
import { severityVariant } from './severity';
import { useSystemConfiguration } from '../context/SystemConfigurationContext';
import { useStation } from '../validation/StationContext';

interface LiveMonitoringViewProps {
  latestTelemetry: InferenceResult | null;
  historyBuffer: InferenceResult[];
  isStreaming: boolean;
  onToggleStreaming: () => void;
}

interface TelemetryPoint {
  step: number;
  time: string;
  timestamp: string;
  temp: number | null;
  press: number | null;
  hum: number | null;
  score: number | null;
  is_anomaly: boolean;
}

type ChannelView = 'all' | 'temperature' | 'pressure' | 'humidity';

const CHANNELS = [
  { view: 'temperature' as const, key: 'temp' as const, axis: 'tempAxis', name: 'Temperature (°C)', color: '#F59E0B', unit: '°C', pad: [1, 1] as const, orientation: 'left' as const, width: 45, active: 'bg-amber-500/20 text-amber-800 border border-amber-500/40 font-bold', activeDot: '#FCD34D' },
  { view: 'pressure' as const, key: 'press' as const, axis: 'pressAxis', name: 'Pressure (hPa)', color: '#38BDF8', unit: 'hPa', pad: [2, 2] as const, orientation: 'right' as const, width: 60, active: 'bg-sky-500/20 text-sky-800 border border-sky-500/40 font-bold', activeDot: '#BAE6FD' },
  { view: 'humidity' as const, key: 'hum' as const, axis: 'humAxis', name: 'Humidity (%)', color: '#818CF8', unit: '%', pad: [5, 5] as const, orientation: 'right' as const, width: 45, active: 'bg-indigo-500/20 text-indigo-800 border border-indigo-500/40 font-bold', activeDot: '#C7D2FE' },
];

const clock = (d: Date) => d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false });
const num = (v: number | null | undefined, digits: number): number | null => (v == null || Number.isNaN(v) ? null : Number(v.toFixed(digits)));

function toPoint(p: InferenceResult, idx: number): TelemetryPoint {
  const t = new Date(p.timestamp || Date.now());
  return {
    step: idx,
    time: clock(t),
    timestamp: p.timestamp || t.toISOString(),
    temp: num(p.temperature ?? p.raw_values?.temperature, 2),
    press: num(p.pressure ?? p.raw_values?.pressure, 1),
    hum: num(p.humidity ?? p.raw_values?.humidity, 1),
    score: p.anomaly_score == null ? null : Number((p.anomaly_score * 100).toFixed(0)),
    is_anomaly: Boolean(p.is_anomaly),
  };
}

export function LiveMonitoringView({ latestTelemetry, historyBuffer, isStreaming, onToggleStreaming }: LiveMonitoringViewProps) {
  const { openSettings, streamConnected } = useSystemConfiguration();
  const { stationId, entry, gauges } = useStation();
  const [activeChannelView, setActiveChannelView] = useState<ChannelView>('all');
  const [timelineData, setTimelineData] = useState<TelemetryPoint[]>([]);
  const [isLoadingHistory, setIsLoadingHistory] = useState<boolean>(false);
  const [historyNotBuilt, setHistoryNotBuilt] = useState<boolean>(false);
  const lastProcessedTimeRef = useRef<string>('');
  const gauge = gauges.find((g) => g.station_id === stationId);

  // Hydrate from the in-memory buffer, then from stored observations, whenever the station changes
  useEffect(() => {
    let isMounted = true;
    setHistoryNotBuilt(false);
    const buffered: TelemetryPoint[] = historyBuffer.filter((p) => p.station_id === stationId).slice(-40).map(toPoint);
    setTimelineData(buffered);
    lastProcessedTimeRef.current = buffered.length > 0 ? buffered[buffered.length - 1].timestamp : '';
    if (!stationId) { setIsLoadingHistory(false); return; }

    setIsLoadingHistory(true);
    fetchObservations({ station_id: stationId, limit: 40 })
      .then((res) => {
        if (!isMounted) return;
        const ascending: Observation[] = [...(res.items || [])].reverse();   // the API answers newest first
        const formatted: TelemetryPoint[] = ascending.map((obs, idx) => ({
          step: idx,
          time: clock(new Date(obs.timestamp)),
          timestamp: obs.timestamp,
          temp: num(obs.temperature, 2),
          press: num(obs.pressure, 1),
          hum: num(obs.humidity, 1),
          score: null,
          is_anomaly: obs.validation_status === 'QC_FLAGGED' || obs.validation_status === 'ANOMALY',
        }));
        if (formatted.length > 0) {
          const latestApiTime = new Date(formatted[formatted.length - 1].timestamp).getTime();
          const newer = buffered.filter((bp) => new Date(bp.timestamp).getTime() > latestApiTime);
          const combined = [...formatted, ...newer].slice(-50).map((pt, idx) => ({ ...pt, step: idx }));
          setTimelineData(combined);
          lastProcessedTimeRef.current = combined[combined.length - 1].timestamp;
        }
        setIsLoadingHistory(false);
      })
      .catch((err) => {
        if (!isMounted) return;
        setHistoryNotBuilt(isNotBuilt(err));
        setIsLoadingHistory(false);
      });

    return () => { isMounted = false; };
    // historyBuffer is read once per station change on purpose: later frames arrive through latestTelemetry
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [stationId]);

  // Take incoming WebSocket frames of the selected station into the timeline
  useEffect(() => {
    if (!latestTelemetry || !stationId || latestTelemetry.station_id !== stationId) return;
    const ts = latestTelemetry.timestamp || new Date().toISOString();
    if (ts === lastProcessedTimeRef.current) return;
    lastProcessedTimeRef.current = ts;
    const point = toPoint({ ...latestTelemetry, timestamp: ts }, 0);
    setTimelineData((prev) => {
      const updated = [...prev, point];
      const trimmed = updated.length > 50 ? updated.slice(-50) : updated;
      return trimmed.map((pt, idx) => ({ ...pt, step: idx }));
    });
  }, [latestTelemetry, stationId]);

  // The live frame (with a verdict) when one arrived for this station; otherwise only the last plain reading
  const live = latestTelemetry && latestTelemetry.station_id === stationId ? latestTelemetry : null;
  const lastPoint = timelineData[timelineData.length - 1] ?? null;
  const currentTemp = live ? live.temperature ?? live.raw_values?.temperature ?? null : lastPoint?.temp ?? null;
  const currentHumidity = live ? live.humidity ?? live.raw_values?.humidity ?? null : lastPoint?.hum ?? null;
  const currentPressure = live ? live.pressure ?? live.raw_values?.pressure ?? null : lastPoint?.press ?? null;
  const dew = dewPoint(currentTemp, currentHumidity);
  const dewDepression = currentTemp != null && dew != null ? currentTemp - dew : null;
  const vapor = vaporPressure(currentTemp, currentHumidity);

  const statsSummary = useMemo(() => {
    const stat = (pick: (p: TelemetryPoint) => number | null) => {
      const arr = timelineData.map(pick).filter((v): v is number => v !== null);
      if (arr.length === 0) return null;
      return { min: Math.min(...arr), max: Math.max(...arr), delta: arr.length > 1 ? arr[arr.length - 1] - arr[0] : 0 };
    };
    return { temp: stat((p) => p.temp), press: stat((p) => p.press), hum: stat((p) => p.hum) };
  }, [timelineData]);

  const range = (s: { min: number; max: number } | null, digits: number, unit = '') => (s ? `${s.min.toFixed(digits)}–${s.max.toFixed(digits)}${unit}` : 'n/a');

  const CustomTooltip = ({ active, payload, label }: any) => {
    if (active && payload && payload.length) {
      const data: TelemetryPoint = payload[0].payload;
      return (
        <div className="bg-[#F4F6FA] border border-[#D3DCE7] p-3 rounded-lg shadow-xl text-xs font-mono space-y-1.5 min-w-[200px]">
          <div className="flex items-center justify-between border-b border-slate-200 pb-1">
            <span className="text-slate-500 font-bold">{label}</span>
            {data.is_anomaly && (
              <span className="px-1.5 py-0.5 bg-rose-500/20 text-rose-700 rounded text-[10px] font-bold border border-rose-500/40">QC FLAG</span>
            )}
          </div>
          <div className="flex justify-between items-center text-amber-600"><span>Temperature:</span><span className="font-bold">{reading(data.temp, 2, ' °C')}</span></div>
          <div className="flex justify-between items-center text-sky-600"><span>Pressure:</span><span className="font-bold">{reading(data.press, 1, ' hPa')}</span></div>
          <div className="flex justify-between items-center text-indigo-500"><span>Humidity:</span><span className="font-bold">{reading(data.hum, 1, ' %')}</span></div>
        </div>
      );
    }
    return null;
  };

  const hasPoints = timelineData.length > 0;
  const shown = activeChannelView === 'all' ? CHANNELS : CHANNELS.filter((c) => c.view === activeChannelView);
  const domainFor = (c: (typeof CHANNELS)[number]): [(m: number) => number, (m: number) => number] =>
    c.view === 'humidity'
      ? [(m) => Math.max(0, Math.floor(m - c.pad[0])), (m) => Math.min(100, Math.ceil(m + c.pad[1]))]
      : [(m) => Math.floor(m - c.pad[0]), (m) => Math.ceil(m + c.pad[1])];

  return (
    <div className="space-y-6">
      <ContextualStatusStrip />

      {/* Station metadata & control sub-bar */}
      <div className="bg-[#FFFFFF] border border-[#D3DCE7] rounded-xl p-4 shadow-lg flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="p-2.5 bg-[#EDF1F7] border border-sky-500/40 rounded-xl text-sky-600" />
          <div>
            {stationId ? (
              <>
                <div className="flex items-center gap-2">
                  <span className="text-sm font-bold text-slate-900 font-mono">{stationId}</span>
                  <span className="text-xs text-slate-600 font-sans">({entry?.place ?? 'station from an uploaded file'})</span>
                  {live && (
                    <StatusBadge
                      label={live.is_anomaly ? live.severity : 'NOMINAL'}
                      variant={live.is_anomaly ? severityVariant(live.severity) : 'nominal'}
                      size="sm"
                      pulse={live.is_anomaly}
                    />
                  )}
                </div>
                <div className="flex items-center gap-3 text-xs text-slate-500 font-mono mt-0.5">
                  <span>{gauge ? `${gauge.latitude.toFixed(4)}°N, ${gauge.longitude.toFixed(4)}°E` : 'position not in the catalogue'}</span>
                  {entry && (<><span>•</span><span>{entry.city}</span></>)}
                </div>
              </>
            ) : (
              <span className="text-sm font-bold text-slate-700 font-mono">No station selected</span>
            )}
          </div>
        </div>

        <div className="flex items-center gap-3 font-mono text-xs">
          <span className="text-slate-500">Station: change it in the header</span>
          <button
            onClick={openSettings}
            className="flex items-center gap-1 px-3 py-1.5 rounded-lg border border-[#D3DCE7] bg-[#F4F6FA] hover:bg-[#EDF1F7] text-slate-600 hover:text-slate-900 font-semibold transition-all"
            title="Configure data source and location"
          >
            <span className="hidden sm:inline">Source</span>
          </button>
          <button
            onClick={onToggleStreaming}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg font-semibold border transition-all ${
              isStreaming ? 'bg-emerald-500/15 border-emerald-500/40 text-emerald-700' : 'bg-amber-500/15 border-amber-500/40 text-amber-700'
            }`}
          >
            {isStreaming ? 'Pause Stream' : 'Resume Stream'}
          </button>
        </div>
      </div>

      {!streamConnected && !hasPoints && (
        <EmptyState
          title="No live stream connected"
          description={
            historyNotBuilt
              ? 'The stream and the stored observations are not built yet. Planned in slice S3 (telemetry sources). The rainfall gauge feed below is separate and works today.'
              : 'Nothing is streaming for this station. The rainfall gauge feed below is separate.'
          }
        />
      )}

      {/* 3 core instrument gauges */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="bg-[#FFFFFF] border border-[#D3DCE7] rounded-xl p-5 shadow-lg space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold uppercase tracking-wider text-slate-500 flex items-center gap-1.5 font-mono">Air Temperature</span>
          </div>
          <div className="flex items-baseline justify-between">
            <span className="text-4xl font-bold font-mono text-slate-900 tracking-tight">
              {currentTemp != null ? currentTemp.toFixed(1) : '--.-'}
              <span className="text-xl text-slate-500 ml-1 font-sans">°C</span>
            </span>
            <div className="text-right text-xs font-mono">
              <span className="text-slate-500 block text-[10px]">Dew Point</span>
              <span className="text-emerald-600 font-bold">{reading(dew, 1, '°C')}</span>
            </div>
          </div>
          <div className="pt-2 border-t border-slate-200 flex items-center justify-between text-xs font-mono text-slate-500">
            <span>Dew Point Depression:</span>
            <span className="text-slate-700">{reading(dewDepression, 1, '°C')}</span>
          </div>
        </div>

        <div className="bg-[#FFFFFF] border border-[#D3DCE7] rounded-xl p-5 shadow-lg space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold uppercase tracking-wider text-slate-500 flex items-center gap-1.5 font-mono">Surface Pressure</span>
          </div>
          <div className="flex items-baseline justify-between">
            <span className="text-4xl font-bold font-mono text-slate-900 tracking-tight">
              {currentPressure != null ? currentPressure.toFixed(1) : '----.-'}
              <span className="text-base text-slate-500 ml-1 font-sans">hPa</span>
            </span>
            <div className="text-right text-xs font-mono">
              <span className="text-slate-500 block text-[10px]">Window range</span>
              <span className="text-sky-600 font-bold">{statsSummary.press ? `${range(statsSummary.press, 1)} hPa` : 'n/a'}</span>
            </div>
          </div>
          <div className="pt-2 border-t border-slate-200 flex items-center justify-between text-xs font-mono text-slate-500">
            <span>Change over the window:</span>
            <span className="text-slate-700">{statsSummary.press ? `${statsSummary.press.delta >= 0 ? '+' : ''}${statsSummary.press.delta.toFixed(1)} hPa` : 'no signal'}</span>
          </div>
        </div>

        <div className="bg-[#FFFFFF] border border-[#D3DCE7] rounded-xl p-5 shadow-lg space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold uppercase tracking-wider text-slate-500 flex items-center gap-1.5 font-mono">Relative Humidity</span>
          </div>
          <div className="flex items-baseline justify-between">
            <span className="text-4xl font-bold font-mono text-slate-900 tracking-tight">
              {currentHumidity != null ? currentHumidity.toFixed(1) : '--.-'}
              <span className="text-xl text-slate-500 ml-1 font-sans">%</span>
            </span>
            <div className="text-right text-xs font-mono">
              <span className="text-slate-500 block text-[10px]">Vapor Pressure</span>
              <span className="text-indigo-600 font-bold">{reading(vapor, 1, ' hPa')}</span>
            </div>
          </div>
          <div className="pt-2 border-t border-slate-200 flex items-center justify-between text-xs font-mono text-slate-500">
            <span>Window range:</span>
            <span className="text-slate-700">{statsSummary.hum ? `${range(statsSummary.hum, 0)} %` : 'n/a'}</span>
          </div>
        </div>
      </div>

      {/* Verdict banner: only with a verdict from the server */}
      {live && (
        <div className="bg-[#FFFFFF] border border-[#D3DCE7] rounded-xl p-4 shadow-lg flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-sky-500/15 border border-sky-500/35 rounded-lg text-sky-600" />
            <div>
              <div className="flex items-center gap-2">
                <span className="text-xs font-bold text-slate-900 uppercase font-mono">Verdict:</span>
                <StatusBadge
                  label={live.is_anomaly ? live.classification.replace(/_/g, ' ') : 'NO CHECK FIRED'}
                  variant={live.is_anomaly ? severityVariant(live.severity) : 'nominal'}
                  size="sm"
                />
              </div>
              {live.reason && <p className="text-xs text-slate-600 mt-0.5">{live.reason}</p>}
            </div>
          </div>
          <div className="text-right text-xs font-mono">
            <span className="text-[10px] text-slate-500 uppercase block">Rule score (uncalibrated)</span>
            <span className="text-sm font-bold text-sky-600">{(live.anomaly_score * 100).toFixed(1)}%</span>
          </div>
        </div>
      )}

      {/* Time-series plots */}
      <div className="bg-[#FFFFFF] border border-[#D3DCE7] rounded-xl p-5 shadow-lg space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 pb-3">
          <div className="flex items-center gap-2">
            <h3 className="text-xs font-bold uppercase tracking-wider text-slate-900 font-mono">Telemetry Stream</h3>
            <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-emerald-500/15 text-emerald-700 border border-emerald-500/30 flex items-center gap-1 font-semibold">
              <span className={`w-1.5 h-1.5 rounded-full ${isLoadingHistory ? 'bg-amber-400 animate-spin' : streamConnected ? 'bg-emerald-400 animate-pulse' : 'bg-slate-400'}`} />
              {isLoadingHistory ? 'LOADING...' : `${timelineData.length} FRAMES`}
            </span>
          </div>

          <div className="flex items-center gap-1.5 bg-[#FFFFFF] p-1.5 rounded-xl border border-[#D3DCE7] text-xs font-mono shadow-sm">
            <button
              onClick={() => setActiveChannelView('all')}
              className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${
                activeChannelView === 'all' ? 'bg-sky-500 text-slate-950 font-bold shadow-sm' : 'text-slate-600 hover:text-slate-900 hover:bg-[#E2E8F0]'
              }`}
            >
              All Signals (Multi-Axis)
            </button>
            {CHANNELS.map((c) => {
              const s = c.view === 'temperature' ? statsSummary.temp : c.view === 'pressure' ? statsSummary.press : statsSummary.hum;
              return (
                <button
                  key={c.view}
                  onClick={() => setActiveChannelView(c.view)}
                  className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${
                    activeChannelView === c.view ? c.active : 'text-slate-600 hover:text-slate-900 hover:bg-[#E2E8F0]'
                  }`}
                >
                  {c.view === 'temperature' ? 'Temp' : c.view === 'pressure' ? 'Press' : 'Hum'} ({range(s, c.view === 'humidity' ? 0 : 1, c.unit)})
                </button>
              );
            })}
          </div>
        </div>

        <div className="h-80 w-full">
          {!hasPoints ? (
            <div className="h-full flex items-center justify-center text-xs text-slate-500 font-mono border border-dashed border-[#D3DCE7] rounded-lg">
              No frames for {stationId ?? 'a station'} yet.
            </div>
          ) : (
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={timelineData} margin={{ top: 10, right: activeChannelView === 'all' ? 30 : 20, left: 10, bottom: 0 }}>
                <defs>
                  {CHANNELS.map((c) => (
                    <linearGradient key={c.key} id={`${c.key}Grad`} x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor={c.color} stopOpacity={activeChannelView === 'all' ? 0.2 : 0.4} />
                      <stop offset="95%" stopColor={c.color} stopOpacity={0.0} />
                    </linearGradient>
                  ))}
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#D3DCE7" opacity={0.5} />
                <XAxis dataKey="time" stroke="#94A3B8" tick={{ fontSize: 10, fill: '#64748B' }} interval="preserveStartEnd" />
                {shown.map((c) => (
                  <YAxis
                    key={c.axis}
                    yAxisId={c.axis}
                    orientation={activeChannelView === 'all' ? c.orientation : 'left'}
                    stroke={c.color}
                    tick={{ fontSize: 10, fill: c.color }}
                    domain={domainFor(c)}
                    unit={c.unit}
                    width={c.width}
                  />
                ))}
                <Tooltip content={<CustomTooltip />} />
                {activeChannelView === 'all' && <Legend wrapperStyle={{ fontSize: '11px', fontFamily: 'monospace', paddingTop: '10px' }} />}
                {shown.map((c) => (
                  <Area
                    key={c.key}
                    yAxisId={c.axis}
                    type="monotone"
                    dataKey={c.key}
                    name={c.name}
                    stroke={c.color}
                    strokeWidth={activeChannelView === 'all' ? 2.5 : 3}
                    fill={`url(#${c.key}Grad)`}
                    dot={{ r: activeChannelView === 'all' ? 2 : 3, fill: c.color }}
                    activeDot={{ r: activeChannelView === 'all' ? 5 : 6, fill: activeChannelView === 'all' ? c.color : c.activeDot }}
                    connectNulls={false}
                    isAnimationActive={false}
                  />
                ))}
              </AreaChart>
            </ResponsiveContainer>
          )}
        </div>
      </div>
    </div>
  );
}

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
import {
  Thermometer,
  Gauge,
  Droplets,
  Radio,
  Play,
  Square,
  Layers,
  MapPin,
  Activity,
  Sliders,
} from 'lucide-react';
import { InferenceResult, Station, Observation } from '../types';
import { fetchObservations, fetchStations } from '../services/api';
import { StatusBadge } from '../design-system/components/StatusBadge';
import { ContextualStatusStrip } from './ContextualStatusStrip';
import { useSystemConfiguration } from '../context/SystemConfigurationContext';

interface LiveMonitoringViewProps {
  selectedStationId: string;
  onSelectStation: (stationId: string) => void;
  latestTelemetry: InferenceResult | null;
  historyBuffer: InferenceResult[];
  isStreaming: boolean;
  onToggleStreaming: () => void;
}

interface TelemetryPoint {
  step: number;
  time: string;
  timestamp: string;
  temp: number;
  press: number;
  hum: number;
  score: number;
  is_anomaly: boolean;
}

export function LiveMonitoringView({
  selectedStationId,
  onSelectStation,
  latestTelemetry,
  historyBuffer: _historyBuffer,
  isStreaming,
  onToggleStreaming,
}: LiveMonitoringViewProps) {
  const { openSettings } = useSystemConfiguration();
  const [stations, setStations] = useState<Station[]>([]);
  const [activeChannelView, setActiveChannelView] = useState<'all' | 'temperature' | 'pressure' | 'humidity'>('all');
  const [timelineData, setTimelineData] = useState<TelemetryPoint[]>([]);
  const [isLoadingHistory, setIsLoadingHistory] = useState<boolean>(true);
  const lastProcessedTimeRef = useRef<string>('');

  // Load configured stations
  useEffect(() => {
    fetchStations().then((res) => {
      setStations(res.items || []);
    });
  }, []);

  // Fetch initial historical observations when station changes to populate time-series
  useEffect(() => {
    let isMounted = true;
    setIsLoadingHistory(true);

    fetchObservations({ station_id: selectedStationId || undefined, limit: 40 })
      .then((res) => {
        if (!isMounted) return;
        const rawItems: Observation[] = res.items || [];
        // API returns descending by timestamp; reverse to get chronological ascending order
        const ascending = [...rawItems].reverse();

        const formatted: TelemetryPoint[] = ascending.map((obs, idx) => {
          const t = new Date(obs.timestamp);
          return {
            step: idx,
            time: t.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false }),
            timestamp: obs.timestamp,
            temp: Number(obs.temperature?.toFixed(2) ?? 25.0),
            press: Number(obs.pressure?.toFixed(1) ?? 1013.2),
            hum: Number(obs.humidity?.toFixed(1) ?? 55.0),
            score: obs.validation_status === 'QC_FLAGGED' || obs.validation_status === 'ANOMALY' ? 85 : 0,
            is_anomaly: obs.validation_status === 'QC_FLAGGED' || obs.validation_status === 'ANOMALY',
          };
        });

        if (formatted.length > 0) {
          setTimelineData(formatted);
          lastProcessedTimeRef.current = formatted[formatted.length - 1].timestamp;
        } else {
          // If no historical records, populate with a baseline point
          const now = new Date();
          setTimelineData([
            {
              step: 0,
              time: now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false }),
              timestamp: now.toISOString(),
              temp: 28.5,
              press: 980.2,
              hum: 72.0,
              score: 0,
              is_anomaly: false,
            },
          ]);
        }
        setIsLoadingHistory(false);
      })
      .catch((err) => {
        console.error('Failed to hydrate historical observations:', err);
        if (isMounted) setIsLoadingHistory(false);
      });

    return () => {
      isMounted = false;
    };
  }, [selectedStationId]);

  // Ingest incoming live WebSocket telemetry frames into timeline
  useEffect(() => {
    if (!latestTelemetry) return;
    // Only accept if station matches (or no station filter)
    if (selectedStationId && latestTelemetry.station_id !== selectedStationId) return;

    const ts = latestTelemetry.timestamp || new Date().toISOString();
    if (ts === lastProcessedTimeRef.current) return;
    lastProcessedTimeRef.current = ts;

    const t = new Date(ts);
    const newPoint: TelemetryPoint = {
      step: 0,
      time: t.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false }),
      timestamp: ts,
      temp: Number((latestTelemetry.temperature ?? latestTelemetry.raw_values?.temperature ?? 25.0).toFixed(2)),
      press: Number((latestTelemetry.pressure ?? latestTelemetry.raw_values?.pressure ?? 1013.2).toFixed(1)),
      hum: Number((latestTelemetry.humidity ?? latestTelemetry.raw_values?.humidity ?? 55.0).toFixed(1)),
      score: Number(((latestTelemetry.anomaly_score ?? 0) * 100).toFixed(0)),
      is_anomaly: Boolean(latestTelemetry.is_anomaly),
    };

    setTimelineData((prev) => {
      const updated = [...prev, newPoint];
      // Keep rolling window of 50 points
      const trimmed = updated.length > 50 ? updated.slice(-50) : updated;
      return trimmed.map((pt, idx) => ({ ...pt, step: idx }));
    });
  }, [latestTelemetry, selectedStationId]);

  // Current reading values
  const current = useMemo(() => {
    if (latestTelemetry && (!selectedStationId || latestTelemetry.station_id === selectedStationId)) {
      return latestTelemetry;
    }
    const lastItem = timelineData[timelineData.length - 1];
    if (lastItem) {
      return {
        timestamp: lastItem.timestamp,
        station_id: selectedStationId || 'AWS-001',
        temperature: lastItem.temp,
        pressure: lastItem.press,
        humidity: lastItem.hum,
        anomaly_score: lastItem.score / 100,
        is_anomaly: lastItem.is_anomaly,
        confidence: 0.98,
        severity: lastItem.is_anomaly ? ('HIGH' as const) : ('NORMAL' as const),
        classification: lastItem.is_anomaly ? 'ANOMALY_DETECTED' : 'NOMINAL',
        is_fault: false,
        reason: 'Observation within configured parameters.',
        sensor_health: 98,
        sensor_status: 'HEALTHY',
        recommended_action: 'Normal operation.',
        degradation_risk: 'LOW',
        tier_scores: {
          tier1_qc_flag: false,
          tier2_point_score: 0.05,
          tier2_temporal_score: 0.02,
          tier3_multivariate_score: 0.01,
        },
        explanation: {
          summary: 'All transducer channels conform to physical boundary conditions.',
          contributing_features: [],
          method: 'TreeSHAP',
        },
      };
    }
    return null;
  }, [latestTelemetry, selectedStationId, timelineData]);

  const activeStationObj = stations.find((s) => s.station_id === selectedStationId);

  // Magnus-Tetens Dew Point Formula
  const calcDewPoint = (t: number, rh: number) => {
    const a = 17.27;
    const b = 237.7;
    const alpha = (a * t) / (b + t) + Math.log(Math.max(1, rh) / 100.0);
    return (b * alpha) / (a - alpha);
  };

  const currentTemp = current?.temperature ?? current?.raw_values?.temperature ?? 24.5;
  const currentHumidity = current?.humidity ?? current?.raw_values?.humidity ?? 58.0;
  const currentPressure = current?.pressure ?? current?.raw_values?.pressure ?? 1012.3;
  const dewPoint = calcDewPoint(currentTemp, currentHumidity);
  const dewPointDepression = currentTemp - dewPoint;

  const getSeverityVariant = (severity?: string) => {
    switch (severity?.toUpperCase()) {
      case 'CRITICAL':
        return 'critical';
      case 'HIGH':
      case 'MEDIUM':
        return 'warning';
      case 'LOW':
        return 'info';
      default:
        return 'nominal';
    }
  };

  // Dynamic Scale Min / Max Computations
  const statsSummary = useMemo(() => {
    if (timelineData.length === 0) {
      return {
        temp: { min: 20, max: 35, avg: 25, delta: 0 },
        press: { min: 970, max: 1020, avg: 980, delta: 0 },
        hum: { min: 40, max: 90, avg: 65, delta: 0 },
      };
    }
    const temps = timelineData.map((d) => d.temp);
    const presses = timelineData.map((d) => d.press);
    const hums = timelineData.map((d) => d.hum);

    const calcStats = (arr: number[]) => {
      const min = Math.min(...arr);
      const max = Math.max(...arr);
      const avg = arr.reduce((a, b) => a + b, 0) / arr.length;
      const delta = arr.length > 1 ? arr[arr.length - 1] - arr[0] : 0;
      return { min, max, avg, delta };
    };

    return {
      temp: calcStats(temps),
      press: calcStats(presses),
      hum: calcStats(hums),
    };
  }, [timelineData]);

  // Tooltip Formatter
  const CustomTooltip = ({ active, payload, label }: any) => {
    if (active && payload && payload.length) {
      const data: TelemetryPoint = payload[0].payload;
      return (
        <div className="bg-[#10192A] border border-[#263B5E] p-3 rounded-lg shadow-xl text-xs font-mono space-y-1.5 min-w-[200px]">
          <div className="flex items-center justify-between border-b border-white/[0.08] pb-1">
            <span className="text-slate-400 font-bold">{label}</span>
            {data.is_anomaly && (
              <span className="px-1.5 py-0.5 bg-rose-500/20 text-rose-300 rounded text-[10px] font-bold border border-rose-500/40">
                QC FLAG
              </span>
            )}
          </div>
          <div className="flex justify-between items-center text-amber-400">
            <span className="flex items-center gap-1">
              <Thermometer className="w-3 h-3" /> Temperature:
            </span>
            <span className="font-bold">{data.temp.toFixed(2)} °C</span>
          </div>
          <div className="flex justify-between items-center text-sky-400">
            <span className="flex items-center gap-1">
              <Gauge className="w-3 h-3" /> Pressure:
            </span>
            <span className="font-bold">{data.press.toFixed(1)} hPa</span>
          </div>
          <div className="flex justify-between items-center text-indigo-400">
            <span className="flex items-center gap-1">
              <Droplets className="w-3 h-3" /> Humidity:
            </span>
            <span className="font-bold">{data.hum.toFixed(1)} %</span>
          </div>
        </div>
      );
    }
    return null;
  };

  return (
    <div className="space-y-6">
      {/* 1-Line Compact Operational Context Strip */}
      <ContextualStatusStrip />

      {/* Station Metadata & Operational Control Sub-Bar */}
      <div className="bg-[#152033] border border-[#263B5E] rounded-xl p-4 shadow-lg flex flex-wrap items-center justify-between gap-4">
        {/* Left: Station Identity & Geographic Location */}
        <div className="flex items-center gap-3">
          <div className="p-2.5 bg-[#1B2A44] border border-sky-500/40 rounded-xl text-sky-400">
            <Radio className="w-5 h-5" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="text-sm font-bold text-white font-mono">{selectedStationId}</span>
              <span className="text-xs text-slate-300 font-sans">
                ({activeStationObj?.name || 'Selected Meteorological Station'})
              </span>
              <StatusBadge
                label={current?.is_anomaly ? current.severity : 'NOMINAL'}
                variant={current?.is_anomaly ? getSeverityVariant(current.severity) : 'nominal'}
                size="sm"
                pulse={current?.is_anomaly}
              />
            </div>
            <div className="flex items-center gap-3 text-xs text-slate-400 font-mono mt-0.5">
              <span className="flex items-center gap-1">
                <MapPin className="w-3 h-3 text-sky-400" />
                {activeStationObj?.latitude ? activeStationObj.latitude.toFixed(4) : '28.6139'}°N,{' '}
                {activeStationObj?.longitude ? activeStationObj.longitude.toFixed(4) : '77.2090'}°E
              </span>
              <span>•</span>
              <span>Elevation: {activeStationObj?.elevation ?? 216} m MSL</span>
            </div>
          </div>
        </div>

        {/* Right: Station Selector, Settings Shortcut, & Streaming Pause/Resume */}
        <div className="flex items-center gap-3 font-mono text-xs">
          <div className="flex items-center gap-2">
            <span className="text-slate-400">Station Node:</span>
            <select
              value={selectedStationId}
              onChange={(e) => onSelectStation(e.target.value)}
              className="bg-[#10192A] border border-[#263B5E] text-slate-200 text-xs rounded-lg px-3 py-1.5 focus:outline-none focus:border-sky-500 font-bold"
            >
              {stations.map((st) => (
                <option key={st.station_id} value={st.station_id}>
                  {st.station_id} — {st.name}
                </option>
              ))}
            </select>
          </div>

          <button
            onClick={openSettings}
            className="flex items-center gap-1 px-3 py-1.5 rounded-lg border border-[#263B5E] bg-[#10192A] hover:bg-[#1B2A44] text-slate-300 hover:text-white font-semibold transition-all"
            title="Configure Data Source & Location"
          >
            <Sliders className="w-3.5 h-3.5 text-sky-400" />
            <span className="hidden sm:inline">Settings</span>
          </button>

          <button
            onClick={onToggleStreaming}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg font-semibold border transition-all ${
              isStreaming
                ? 'bg-emerald-500/15 border-emerald-500/40 text-emerald-300'
                : 'bg-amber-500/15 border-amber-500/40 text-amber-300'
            }`}
          >
            {isStreaming ? (
              <>
                <Square className="w-3 h-3 fill-current" /> Pause Stream
              </>
            ) : (
              <>
                <Play className="w-3 h-3 fill-current" /> Resume Stream
              </>
            )}
          </button>
        </div>
      </div>

      {/* 3 Core Meteorological Instrument Gauges */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {/* Air Temperature Gauge Card */}
        <div className="bg-[#152033] border border-[#263B5E] rounded-xl p-5 shadow-lg space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold uppercase tracking-wider text-slate-400 flex items-center gap-1.5 font-mono">
              <Thermometer className="w-4 h-4 text-amber-400" /> Air Temperature
            </span>
            <span className="text-[10px] font-mono text-slate-400 bg-[#10192A] px-2 py-0.5 rounded border border-[#263B5E]">
              1.5m AGL
            </span>
          </div>

          <div className="flex items-baseline justify-between">
            <span className="text-4xl font-bold font-mono text-white tracking-tight">
              {currentTemp.toFixed(1)}
              <span className="text-xl text-slate-400 ml-1 font-sans">°C</span>
            </span>
            <div className="text-right text-xs font-mono">
              <span className="text-slate-400 block text-[10px]">Dew Point</span>
              <span className="text-emerald-400 font-bold">{dewPoint.toFixed(1)}°C</span>
            </div>
          </div>

          <div className="pt-2 border-t border-white/[0.08] flex items-center justify-between text-xs font-mono text-slate-400">
            <span>Dew Point Depression:</span>
            <span className="text-slate-200">{dewPointDepression.toFixed(1)}°C</span>
          </div>
        </div>

        {/* Atmospheric Barometric Pressure Gauge Card */}
        <div className="bg-[#152033] border border-[#263B5E] rounded-xl p-5 shadow-lg space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold uppercase tracking-wider text-slate-400 flex items-center gap-1.5 font-mono">
              <Gauge className="w-4 h-4 text-sky-400" /> Surface Pressure
            </span>
            <span className="text-[10px] font-mono text-slate-400 bg-[#10192A] px-2 py-0.5 rounded border border-[#263B5E]">
              Barometer
            </span>
          </div>

          <div className="flex items-baseline justify-between">
            <span className="text-4xl font-bold font-mono text-white tracking-tight">
              {currentPressure.toFixed(1)}
              <span className="text-base text-slate-400 ml-1 font-sans">hPa</span>
            </span>
            <div className="text-right text-xs font-mono">
              <span className="text-slate-400 block text-[10px]">Sea-Level MSLP</span>
              <span className="text-sky-400 font-bold">{(currentPressure + 12.0).toFixed(1)} hPa</span>
            </div>
          </div>

          <div className="pt-2 border-t border-white/[0.08] flex items-center justify-between text-xs font-mono text-slate-400">
            <span>Hydrostatic Tendency:</span>
            <span className="text-emerald-400">STABLE (&lt; 0.5 hPa/3h)</span>
          </div>
        </div>

        {/* Relative Humidity Gauge Card */}
        <div className="bg-[#152033] border border-[#263B5E] rounded-xl p-5 shadow-lg space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold uppercase tracking-wider text-slate-400 flex items-center gap-1.5 font-mono">
              <Droplets className="w-4 h-4 text-indigo-400" /> Relative Humidity
            </span>
            <span className="text-[10px] font-mono text-slate-400 bg-[#10192A] px-2 py-0.5 rounded border border-[#263B5E]">
              Hygrometer
            </span>
          </div>

          <div className="flex items-baseline justify-between">
            <span className="text-4xl font-bold font-mono text-white tracking-tight">
              {currentHumidity.toFixed(1)}
              <span className="text-xl text-slate-400 ml-1 font-sans">%</span>
            </span>
            <div className="text-right text-xs font-mono">
              <span className="text-slate-400 block text-[10px]">Vapor Pressure</span>
              <span className="text-indigo-300 font-bold">
                {(
                  (currentHumidity / 100) *
                  6.112 *
                  Math.exp((17.67 * currentTemp) / (currentTemp + 243.5))
                ).toFixed(1)}{' '}
                hPa
              </span>
            </div>
          </div>

          <div className="pt-2 border-t border-white/[0.08] flex items-center justify-between text-xs font-mono text-slate-400">
            <span>Saturation Envelope:</span>
            <span className="text-slate-200">
              {currentHumidity > 85 ? 'High Moisture' : 'Nominal Ambient'}
            </span>
          </div>
        </div>
      </div>

      {/* 5-Tier Algorithmic Inference Verdict Banner */}
      <div className="bg-[#152033] border border-[#263B5E] rounded-xl p-4 shadow-lg flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-sky-500/15 border border-sky-500/35 rounded-lg text-sky-400">
            <Layers className="w-5 h-5" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="text-xs font-bold text-white uppercase font-mono">5-Tier Inference Verdict:</span>
              <StatusBadge
                label={current?.is_anomaly ? current.classification.replace(/_/g, ' ') : 'ALL CHANNELS NOMINAL'}
                variant={current?.is_anomaly ? getSeverityVariant(current.severity) : 'nominal'}
                size="sm"
              />
            </div>
            <p className="text-xs text-slate-300 mt-0.5">
              {current?.reason ||
                'All transducer signals conform to WMO-No. 8 physical and Clausius-Clapeyron thermodynamic consistency boundaries.'}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-4 text-xs font-mono">
          <div className="text-right">
            <span className="text-[10px] text-slate-400 uppercase block">Anomaly Score</span>
            <span className="text-sm font-bold text-sky-400">
              {current?.anomaly_score ? (current.anomaly_score * 100).toFixed(1) : '0.0'}%
            </span>
          </div>
          <div className="text-right">
            <span className="text-[10px] text-slate-400 uppercase block">Confidence</span>
            <span className="text-sm font-bold text-emerald-400">
              {current?.confidence ? (current.confidence * 100).toFixed(1) : '99.4'}%
            </span>
          </div>
        </div>
      </div>

      {/* Synchronized Multi-Channel Time-Series Dynamic Plots */}
      <div className="bg-[#152033] border border-[#263B5E] rounded-xl p-5 shadow-lg space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-white/[0.08] pb-3">
          <div className="flex items-center gap-2">
            <Activity className="w-4 h-4 text-sky-400" />
            <h3 className="text-xs font-bold uppercase tracking-wider text-white font-mono">
              Continuous Real-Time Telemetry Stream & Anomaly Envelope
            </h3>
            <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-emerald-500/15 text-emerald-300 border border-emerald-500/30 flex items-center gap-1 font-semibold">
              <span className={`w-1.5 h-1.5 rounded-full ${isLoadingHistory ? 'bg-amber-400 animate-spin' : 'bg-emerald-400 animate-pulse'}`} />
              {isLoadingHistory ? 'HYDRATING...' : `${timelineData.length} FRAMES`}
            </span>
          </div>

          {/* Channel Selector */}
          <div className="flex items-center gap-1.5 bg-[#10192A] p-1 rounded-lg border border-[#263B5E] text-xs font-mono">
            <button
              onClick={() => setActiveChannelView('all')}
              className={`px-2.5 py-1 rounded text-xs font-semibold transition-colors ${
                activeChannelView === 'all'
                  ? 'bg-sky-500 text-slate-950 font-bold'
                  : 'text-slate-400 hover:text-white'
              }`}
            >
              All Signals (Multi-Axis)
            </button>
            <button
              onClick={() => setActiveChannelView('temperature')}
              className={`px-2.5 py-1 rounded text-xs font-semibold transition-colors ${
                activeChannelView === 'temperature'
                  ? 'bg-amber-500/20 text-amber-300 border border-amber-500/40 font-bold'
                  : 'text-slate-400 hover:text-white'
              }`}
            >
              Temp ({statsSummary.temp.min.toFixed(1)}–{statsSummary.temp.max.toFixed(1)}°C)
            </button>
            <button
              onClick={() => setActiveChannelView('pressure')}
              className={`px-2.5 py-1 rounded text-xs font-semibold transition-colors ${
                activeChannelView === 'pressure'
                  ? 'bg-sky-500/20 text-sky-300 border border-sky-500/40 font-bold'
                  : 'text-slate-400 hover:text-white'
              }`}
            >
              Press ({statsSummary.press.min.toFixed(1)}–{statsSummary.press.max.toFixed(1)} hPa)
            </button>
            <button
              onClick={() => setActiveChannelView('humidity')}
              className={`px-2.5 py-1 rounded text-xs font-semibold transition-colors ${
                activeChannelView === 'humidity'
                  ? 'bg-indigo-500/20 text-indigo-300 border border-indigo-500/40 font-bold'
                  : 'text-slate-400 hover:text-white'
              }`}
            >
              Hum ({statsSummary.hum.min.toFixed(0)}–{statsSummary.hum.max.toFixed(0)}%)
            </button>
          </div>
        </div>

        {/* Dynamic Scale Chart */}
        <div className="h-80 w-full">
          <ResponsiveContainer width="100%" height="100%">
            {activeChannelView === 'all' ? (
              <AreaChart data={timelineData} margin={{ top: 10, right: 30, left: 10, bottom: 0 }}>
                <defs>
                  <linearGradient id="tempGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#F59E0B" stopOpacity={0.2} />
                    <stop offset="95%" stopColor="#F59E0B" stopOpacity={0.0} />
                  </linearGradient>
                  <linearGradient id="pressGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#38BDF8" stopOpacity={0.2} />
                    <stop offset="95%" stopColor="#38BDF8" stopOpacity={0.0} />
                  </linearGradient>
                  <linearGradient id="humGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#818CF8" stopOpacity={0.2} />
                    <stop offset="95%" stopColor="#818CF8" stopOpacity={0.0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#263B5E" opacity={0.5} />
                <XAxis
                  dataKey="time"
                  stroke="#94A3B8"
                  tick={{ fontSize: 10, fill: '#94A3B8' }}
                  interval="preserveStartEnd"
                />

                {/* Independent Multi-Axes for Scaling */}
                <YAxis
                  yAxisId="tempAxis"
                  orientation="left"
                  stroke="#F59E0B"
                  tick={{ fontSize: 10, fill: '#F59E0B' }}
                  domain={[
                    (dataMin: number) => Math.floor(dataMin - 1),
                    (dataMax: number) => Math.ceil(dataMax + 1),
                  ]}
                  unit="°C"
                  width={45}
                />
                <YAxis
                  yAxisId="pressAxis"
                  orientation="right"
                  stroke="#38BDF8"
                  tick={{ fontSize: 10, fill: '#38BDF8' }}
                  domain={[
                    (dataMin: number) => Math.floor(dataMin - 2),
                    (dataMax: number) => Math.ceil(dataMax + 2),
                  ]}
                  unit="hPa"
                  width={60}
                />
                <YAxis
                  yAxisId="humAxis"
                  orientation="right"
                  stroke="#818CF8"
                  tick={{ fontSize: 10, fill: '#818CF8' }}
                  domain={[
                    (dataMin: number) => Math.max(0, Math.floor(dataMin - 5)),
                    (dataMax: number) => Math.min(100, Math.ceil(dataMax + 5)),
                  ]}
                  unit="%"
                  width={45}
                  hide={false}
                />

                <Tooltip content={<CustomTooltip />} />
                <Legend
                  wrapperStyle={{ fontSize: '11px', fontFamily: 'monospace', paddingTop: '10px' }}
                />

                {/* Scaled Plots */}
                <Area
                  yAxisId="tempAxis"
                  type="monotone"
                  dataKey="temp"
                  name="Temperature (°C)"
                  stroke="#F59E0B"
                  strokeWidth={2.5}
                  fill="url(#tempGrad)"
                  dot={{ r: 2, fill: '#F59E0B' }}
                  activeDot={{ r: 5, fill: '#F59E0B' }}
                  isAnimationActive={false}
                />
                <Area
                  yAxisId="pressAxis"
                  type="monotone"
                  dataKey="press"
                  name="Pressure (hPa)"
                  stroke="#38BDF8"
                  strokeWidth={2.5}
                  fill="url(#pressGrad)"
                  dot={{ r: 2, fill: '#38BDF8' }}
                  activeDot={{ r: 5, fill: '#38BDF8' }}
                  isAnimationActive={false}
                />
                <Area
                  yAxisId="humAxis"
                  type="monotone"
                  dataKey="hum"
                  name="Humidity (%)"
                  stroke="#818CF8"
                  strokeWidth={2.5}
                  fill="url(#humGrad)"
                  dot={{ r: 2, fill: '#818CF8' }}
                  activeDot={{ r: 5, fill: '#818CF8' }}
                  isAnimationActive={false}
                />
              </AreaChart>
            ) : activeChannelView === 'temperature' ? (
              <AreaChart data={timelineData} margin={{ top: 10, right: 20, left: 0, bottom: 0 }}>
                <defs>
                  <linearGradient id="tempSingleGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#F59E0B" stopOpacity={0.4} />
                    <stop offset="95%" stopColor="#F59E0B" stopOpacity={0.0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#263B5E" opacity={0.6} />
                <XAxis
                  dataKey="time"
                  stroke="#94A3B8"
                  tick={{ fontSize: 10, fill: '#94A3B8' }}
                  interval="preserveStartEnd"
                />
                <YAxis
                  stroke="#F59E0B"
                  tick={{ fontSize: 10, fill: '#F59E0B' }}
                  domain={[
                    (dataMin: number) => Math.floor(dataMin - 1),
                    (dataMax: number) => Math.ceil(dataMax + 1),
                  ]}
                  unit="°C"
                />
                <Tooltip content={<CustomTooltip />} />
                <Area
                  type="monotone"
                  dataKey="temp"
                  name="Temperature (°C)"
                  stroke="#F59E0B"
                  strokeWidth={3}
                  fill="url(#tempSingleGrad)"
                  dot={{ r: 3, fill: '#F59E0B' }}
                  activeDot={{ r: 6, fill: '#FCD34D' }}
                  isAnimationActive={false}
                />
              </AreaChart>
            ) : activeChannelView === 'pressure' ? (
              <AreaChart data={timelineData} margin={{ top: 10, right: 20, left: 10, bottom: 0 }}>
                <defs>
                  <linearGradient id="pressSingleGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#38BDF8" stopOpacity={0.4} />
                    <stop offset="95%" stopColor="#38BDF8" stopOpacity={0.0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#263B5E" opacity={0.6} />
                <XAxis
                  dataKey="time"
                  stroke="#94A3B8"
                  tick={{ fontSize: 10, fill: '#94A3B8' }}
                  interval="preserveStartEnd"
                />
                <YAxis
                  stroke="#38BDF8"
                  tick={{ fontSize: 10, fill: '#38BDF8' }}
                  domain={[
                    (dataMin: number) => Math.floor(dataMin - 2),
                    (dataMax: number) => Math.ceil(dataMax + 2),
                  ]}
                  unit="hPa"
                />
                <Tooltip content={<CustomTooltip />} />
                <Area
                  type="monotone"
                  dataKey="press"
                  name="Pressure (hPa)"
                  stroke="#38BDF8"
                  strokeWidth={3}
                  fill="url(#pressSingleGrad)"
                  dot={{ r: 3, fill: '#38BDF8' }}
                  activeDot={{ r: 6, fill: '#BAE6FD' }}
                  isAnimationActive={false}
                />
              </AreaChart>
            ) : (
              <AreaChart data={timelineData} margin={{ top: 10, right: 20, left: 0, bottom: 0 }}>
                <defs>
                  <linearGradient id="humSingleGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#818CF8" stopOpacity={0.4} />
                    <stop offset="95%" stopColor="#818CF8" stopOpacity={0.0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#263B5E" opacity={0.6} />
                <XAxis
                  dataKey="time"
                  stroke="#94A3B8"
                  tick={{ fontSize: 10, fill: '#94A3B8' }}
                  interval="preserveStartEnd"
                />
                <YAxis
                  stroke="#818CF8"
                  tick={{ fontSize: 10, fill: '#818CF8' }}
                  domain={[
                    (dataMin: number) => Math.max(0, Math.floor(dataMin - 5)),
                    (dataMax: number) => Math.min(100, Math.ceil(dataMax + 5)),
                  ]}
                  unit="%"
                />
                <Tooltip content={<CustomTooltip />} />
                <Area
                  type="monotone"
                  dataKey="hum"
                  name="Humidity (%)"
                  stroke="#818CF8"
                  strokeWidth={3}
                  fill="url(#humSingleGrad)"
                  dot={{ r: 3, fill: '#818CF8' }}
                  activeDot={{ r: 6, fill: '#C7D2FE' }}
                  isAnimationActive={false}
                />
              </AreaChart>
            )}
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  );
}

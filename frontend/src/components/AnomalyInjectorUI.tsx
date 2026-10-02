import { useState, useEffect } from 'react';
import {
  FlaskConical,
  Zap,
  TrendingUp,
  Snowflake,
  AlertOctagon,
  Shuffle,
  CloudLightning,
  Radio,
  CheckCircle2,
  AlertTriangle,
  Sliders,
  Loader2,
  Sparkles,
} from 'lucide-react';
import { injectAnomaly, fetchStations } from '../services/api';
import { Station } from '../types';
import { StatusBadge } from '../design-system/components/StatusBadge';

interface AnomalyInjectorUIProps {
  selectedStationId?: string;
  onSelectStation?: (stationId: string) => void;
  onNavigateToLive: () => void;
}

export function AnomalyInjectorUI({ selectedStationId, onSelectStation, onNavigateToLive }: AnomalyInjectorUIProps) {
  const [stations, setStations] = useState<Station[]>([]);
  const [selectedStation, setSelectedStation] = useState<string>(selectedStationId || 'KTLX');
  const [selectedParameter, setSelectedParameter] = useState<string>('temperature');
  const [customType, setCustomType] = useState<string>('SPIKE');
  const [customMagnitude, setCustomMagnitude] = useState<number>(25.0);
  const [customDuration, setCustomDuration] = useState<number>(5);
  const [customDecay] = useState<boolean>(true);
  const [lastMessage, setLastMessage] = useState<{ text: string; isError?: boolean } | null>(null);
  const [isInjecting, setIsInjecting] = useState<boolean>(false);

  useEffect(() => {
    if (selectedStationId) {
      setSelectedStation(selectedStationId);
    }
  }, [selectedStationId]);

  useEffect(() => {
    fetchStations().then((res) => {
      setStations(res.items);
      if (res.items.length > 0) {
        const exists = res.items.some((s) => s.station_id === selectedStation);
        if (!exists) {
          setSelectedStation(selectedStationId || res.items[0].station_id);
        }
      }
    });
  }, []);

  const triggerInjection = async (
    anomalyType: string,
    param: string = 'temperature',
    mag: number = 25.0,
    dur: number = 5,
    decay: boolean = false
  ) => {
    setIsInjecting(true);
    try {
      const res = await injectAnomaly({
        anomaly_type: anomalyType,
        station_id: selectedStation || undefined,
        parameter: param,
        magnitude: mag,
        duration_steps: dur,
        decay: decay,
      });
      setLastMessage({
        text: res.message || `Injected synthetic ${anomalyType} on ${selectedStation || 'ALL stations'} (${param}, magnitude: ${mag})`,
        isError: false,
      });
    } catch (err: any) {
      setLastMessage({ text: `Failed to inject disturbance: ${err.message}`, isError: true });
    } finally {
      setIsInjecting(false);
    }
  };

  const presets = [
    {
      id: 'SPIKE',
      title: 'Sudden Thermal Spike',
      icon: <Zap className="w-4 h-4 text-rose-500" />,
      badgeVariant: 'critical' as const,
      description: 'Rapid transient temperature surge (+25°C) to test Tier 1 rate-of-change and Tier 2 point anomaly response.',
      action: () => triggerInjection('SPIKE', 'temperature', 25.0, 3, true),
    },
    {
      id: 'DRIFT',
      title: 'Sensor Calibration Drift',
      icon: <TrendingUp className="w-4 h-4 text-amber-500" />,
      badgeVariant: 'warning' as const,
      description: 'Gradual linear deviation (+0.25°C/step) testing sensor health EMA degradation and slow anomaly detection.',
      action: () => triggerInjection('DRIFT', 'temperature', 10.0, 20, false),
    },
    {
      id: 'FROZEN',
      title: 'Frozen / Stuck Transducer',
      icon: <Snowflake className="w-4 h-4 text-sky-500" />,
      badgeVariant: 'info' as const,
      description: 'Zero variance constant value across consecutive timestamps to test persistence and frozen value quality checks.',
      action: () => triggerInjection('FROZEN', 'temperature', 0.0, 15, false),
    },
    {
      id: 'DROPOUT',
      title: 'Sensor Channel Dropout',
      icon: <AlertOctagon className="w-4 h-4 text-rose-500" />,
      badgeVariant: 'critical' as const,
      description: 'Sudden drop to near-zero or impossible baseline to test dropout and boundary violation rules.',
      action: () => triggerInjection('DROPOUT', 'humidity', -50.0, 5, false),
    },
    {
      id: 'MULTIVARIATE_INCONSISTENCY',
      title: 'Thermodynamic Inconsistency',
      icon: <Shuffle className="w-4 h-4 text-amber-500" />,
      badgeVariant: 'warning' as const,
      description: 'Simultaneous high temperature (+38°C) and 99% RH violating Clausius-Clapeyron thermodynamic consistency.',
      action: () => triggerInjection('MULTIVARIATE_INCONSISTENCY', 'humidity', 50.0, 8, false),
    },
    {
      id: 'METEOROLOGICAL_EXTREME',
      title: 'Severe Storm Front (Met Extreme)',
      icon: <CloudLightning className="w-4 h-4 text-purple-500" />,
      badgeVariant: 'extremeMet' as const,
      description: 'Deep barometric pressure plunge (-22 hPa) with correlated temperature drops, classified as METEOROLOGICAL_EXTREME rather than fault.',
      action: () => triggerInjection('METEOROLOGICAL_EXTREME', 'pressure', -22.0, 10, false),
    },
  ];

  return (
    <div className="space-y-6">
      {/* Simulation Lab Header */}
      <div className="bg-[#FFFFFF] border border-[#D3DCE7] rounded-xl p-4.5 shadow-lg flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="p-2.5 bg-amber-500/15 border border-amber-500/35 rounded-xl text-amber-600">
            <FlaskConical className="w-5 h-5 text-amber-500" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-sm font-bold text-slate-900 uppercase font-mono tracking-wide">
                Anomaly Simulation Laboratory
              </h2>
              <span className="text-[10px] font-mono px-2 py-0.2 rounded bg-amber-500/15 text-amber-700 border border-amber-500/30 font-bold flex items-center gap-1">
                <Sparkles className="w-3 h-3 text-amber-600" /> TESTBED ENVIRONMENT
              </span>
            </div>
            <p className="text-xs text-slate-600 mt-0.5">
              Inject synthetic disturbances, hardware faults, and atmospheric phenomena into the live telemetry stream
            </p>
          </div>
        </div>

        <div className="flex items-center gap-3 font-mono">
          <div className="flex items-center gap-2">
            <span className="text-xs text-slate-600 font-sans font-medium">Target Station:</span>
            <select
              value={selectedStation}
              onChange={(e) => {
                setSelectedStation(e.target.value);
                if (onSelectStation && e.target.value) {
                  onSelectStation(e.target.value);
                }
              }}
              className="bg-[#F4F6FA] border border-[#D3DCE7] text-slate-800 text-xs rounded-lg px-3 py-1.5 focus:outline-none focus:border-sky-500 font-bold shadow-sm"
            >
              <option value="">ALL STATIONS (Network-Wide)</option>
              {stations.map((st) => (
                <option key={st.station_id} value={st.station_id}>
                  {st.station_id} — {st.name}
                </option>
              ))}
            </select>
          </div>

          <button
            onClick={onNavigateToLive}
            className="flex items-center gap-1.5 px-3.5 py-1.5 bg-sky-500 hover:bg-sky-400 text-slate-950 rounded-lg text-xs font-bold transition-all shadow"
          >
            <Radio className="w-3.5 h-3.5" /> Watch Live Response →
          </button>
        </div>
      </div>

      {/* Notification Toast */}
      {lastMessage && (
        <div
          className={`p-3.5 rounded-xl text-xs font-mono flex items-center justify-between border ${
            lastMessage.isError
              ? 'bg-rose-500/15 border-rose-500/40 text-rose-700'
              : 'bg-emerald-500/15 border-emerald-500/40 text-emerald-700'
          }`}
        >
          <div className="flex items-center gap-2">
            {lastMessage.isError ? (
              <AlertTriangle className="w-4 h-4 text-rose-600 shrink-0" />
            ) : (
              <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0" />
            )}
            <span>{lastMessage.text}</span>
          </div>
          <button
            onClick={() => setLastMessage(null)}
            className="text-slate-500 hover:text-slate-900 text-xs font-bold ml-4"
          >
            Dismiss
          </button>
        </div>
      )}

      {/* 6 Disturbance Preset Cards Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {presets.map((preset) => {
          return (
            <div
              key={preset.id}
              className="bg-[#FFFFFF] border border-[#D3DCE7] p-5 rounded-xl shadow-lg hover:border-[#38BDF8]/50 transition-all flex flex-col justify-between"
            >
              <div>
                <div className="flex items-center justify-between mb-3">
                  <div className="p-2 rounded-lg bg-[#F4F6FA] border border-[#D3DCE7]/60 text-slate-600 flex items-center gap-1.5 font-mono text-xs font-bold">
                    {preset.icon}
                    <span>{preset.id}</span>
                  </div>
                  <StatusBadge
                    label={preset.id}
                    variant={preset.badgeVariant}
                    size="sm"
                  />
                </div>
                <h4 className="text-sm font-bold text-slate-900 mb-1.5 font-mono">{preset.title}</h4>
                <p className="text-xs text-slate-600 leading-relaxed font-sans">{preset.description}</p>
              </div>

              <div className="mt-4 pt-3 border-t border-slate-200">
                <button
                  onClick={preset.action}
                  disabled={isInjecting}
                  className="w-full py-2 bg-[#F4F6FA] hover:bg-[#EDF1F7] text-slate-700 hover:text-slate-900 border border-[#D3DCE7] rounded-lg text-xs font-mono font-semibold flex items-center justify-center gap-2 transition-all shadow-sm disabled:opacity-50"
                >
                  {isInjecting ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : preset.icon}
                  Inject {preset.id}
                </button>
              </div>
            </div>
          );
        })}
      </div>

      {/* Parametric Custom Disturbance Generator */}
      <div className="bg-[#FFFFFF] border border-[#D3DCE7] rounded-xl p-5 shadow-lg space-y-4">
        <div className="flex items-center gap-2">
          <Sliders className="w-4 h-4 text-sky-500" />
          <h3 className="text-xs font-bold uppercase tracking-wider text-slate-900 font-mono">
            Parametric Disturbance Generator
          </h3>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-4 gap-4 text-xs font-mono">
          <div>
            <label className="text-slate-600 block mb-1.5 font-sans">Anomaly Model Type</label>
            <select
              value={customType}
              onChange={(e) => setCustomType(e.target.value)}
              className="w-full bg-[#F4F6FA] border border-[#D3DCE7] text-slate-700 rounded-lg p-2.5"
            >
              <option value="SPIKE">Spike (Transient Jump)</option>
              <option value="DRIFT">Linear Calibration Drift</option>
              <option value="FROZEN">Frozen Transducer (Zero Var)</option>
              <option value="DROPOUT">Channel Dropout</option>
              <option value="NOISE_BURST">Noise Burst (Turbulence)</option>
              <option value="MULTIVARIATE_INCONSISTENCY">Multivariate Inconsistency</option>
              <option value="METEOROLOGICAL_EXTREME">Meteorological Extreme</option>
              <option value="DATA_CORRUPTION">Data Corruption</option>
            </select>
          </div>

          <div>
            <label className="text-slate-600 block mb-1.5 font-sans">Target Channel</label>
            <select
              value={selectedParameter}
              onChange={(e) => setSelectedParameter(e.target.value)}
              className="w-full bg-[#F4F6FA] border border-[#D3DCE7] text-slate-700 rounded-lg p-2.5"
            >
              <option value="temperature">Temperature (°C)</option>
              <option value="pressure">Pressure (hPa)</option>
              <option value="humidity">Relative Humidity (%)</option>
            </select>
          </div>

          <div>
            <label className="text-slate-600 block mb-1.5 font-sans">Magnitude Offset</label>
            <input
              type="number"
              value={customMagnitude}
              onChange={(e) => setCustomMagnitude(Number(e.target.value))}
              className="w-full bg-[#F4F6FA] border border-[#D3DCE7] text-slate-700 rounded-lg p-2.5"
            />
          </div>

          <div>
            <label className="text-slate-600 block mb-1.5 font-sans">Duration (Steps)</label>
            <input
              type="number"
              min={1}
              max={100}
              value={customDuration}
              onChange={(e) => setCustomDuration(Number(e.target.value))}
              className="w-full bg-[#F4F6FA] border border-[#D3DCE7] text-slate-700 rounded-lg p-2.5"
            />
          </div>
        </div>

        <div className="pt-3 border-t border-slate-200 flex items-center justify-between">
          <div className="flex items-center gap-2 text-xs text-slate-500 font-mono">
            <Radio className="w-3.5 h-3.5 text-sky-500" />
            <span className="text-[11px]">Dispatches immediately to WebSocket `/ws/live` simulation stream.</span>
          </div>

          <button
            onClick={() => triggerInjection(customType, selectedParameter, customMagnitude, customDuration, customDecay)}
            disabled={isInjecting}
            className="px-4 py-2 bg-sky-500 hover:bg-sky-400 text-slate-950 font-mono font-bold text-xs rounded-lg transition-all shadow flex items-center gap-1.5 disabled:opacity-50"
          >
            {isInjecting ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Zap className="w-3.5 h-3.5" />}
            Dispatch Parametric Anomaly
          </button>
        </div>
      </div>
    </div>
  );
}

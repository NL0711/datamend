import { useState, useEffect } from 'react';
import {
  Zap,
  Flame,
  TrendingUp,
  Snowflake,
  RadioTower,
  Activity,
  CloudLightning,
  AlertOctagon,
  Play,
  Info,
  Sliders,
  CheckCircle2,
} from 'lucide-react';
import { injectAnomaly, fetchStations } from '../services/api';
import { Station } from '../types';
import { StatusBadge } from '../design-system/components/StatusBadge';

interface AnomalyInjectorUIProps {
  onNavigateToLive: () => void;
}

export function AnomalyInjectorUI({ onNavigateToLive }: AnomalyInjectorUIProps) {
  const [stations, setStations] = useState<Station[]>([]);
  const [selectedStation, setSelectedStation] = useState<string>('AWS-001');
  const [selectedParameter, setSelectedParameter] = useState<string>('temperature');
  const [customType, setCustomType] = useState<string>('SPIKE');
  const [customMagnitude, setCustomMagnitude] = useState<number>(25.0);
  const [customDuration, setCustomDuration] = useState<number>(5);
  const [customDecay] = useState<boolean>(true);
  const [lastMessage, setLastMessage] = useState<{ text: string; isError?: boolean } | null>(null);
  const [isInjecting, setIsInjecting] = useState<boolean>(false);

  useEffect(() => {
    fetchStations().then((res) => {
      setStations(res.items);
      if (res.items.length > 0 && !selectedStation) {
        setSelectedStation(res.items[0].station_id);
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
      await injectAnomaly({
        anomaly_type: anomalyType,
        station_id: selectedStation || undefined,
        parameter: param,
        magnitude: mag,
        duration_steps: dur,
        decay: decay,
      });
      setLastMessage({
        text: `Injected synthetic ${anomalyType} on ${selectedStation || 'all stations'} (${param}, magnitude: ${mag})`,
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
      icon: Flame,
      badgeVariant: 'critical' as const,
      description: 'Rapid transient temperature surge (+25°C) to test Tier 1 rate-of-change and Tier 2 point anomaly response.',
      action: () => triggerInjection('SPIKE', 'temperature', 25.0, 3, true),
    },
    {
      id: 'DRIFT',
      title: 'Sensor Calibration Drift',
      icon: TrendingUp,
      badgeVariant: 'warning' as const,
      description: 'Gradual linear deviation (+0.25°C/step) testing sensor health EMA degradation and slow anomaly detection.',
      action: () => triggerInjection('DRIFT', 'temperature', 10.0, 20, false),
    },
    {
      id: 'FROZEN',
      title: 'Frozen / Stuck Transducer',
      icon: Snowflake,
      badgeVariant: 'info' as const,
      description: 'Zero variance constant value across consecutive timestamps to test persistence and frozen value quality checks.',
      action: () => triggerInjection('FROZEN', 'temperature', 0.0, 15, false),
    },
    {
      id: 'DROPOUT',
      title: 'Sensor Channel Dropout',
      icon: RadioTower,
      badgeVariant: 'critical' as const,
      description: 'Sudden drop to near-zero or impossible baseline to test dropout and boundary violation rules.',
      action: () => triggerInjection('DROPOUT', 'humidity', -50.0, 5, false),
    },
    {
      id: 'MULTIVARIATE_INCONSISTENCY',
      title: 'Thermodynamic Inconsistency',
      icon: AlertOctagon,
      badgeVariant: 'warning' as const,
      description: 'Simultaneous high temperature (+38°C) and 99% RH violating Clausius-Clapeyron thermodynamic consistency.',
      action: () => triggerInjection('MULTIVARIATE_INCONSISTENCY', 'humidity', 50.0, 8, false),
    },
    {
      id: 'METEOROLOGICAL_EXTREME',
      title: 'Severe Storm Front (Met Extreme)',
      icon: CloudLightning,
      badgeVariant: 'extremeMet' as const,
      description: 'Deep barometric pressure plunge (-22 hPa) with correlated temperature drops, classified as METEOROLOGICAL_EXTREME rather than fault.',
      action: () => triggerInjection('METEOROLOGICAL_EXTREME', 'pressure', -22.0, 10, false),
    },
  ];

  return (
    <div className="space-y-6">
      {/* Simulation Lab Header */}
      <div className="bg-[#152033] border border-[#263B5E] rounded-xl p-4.5 shadow-lg flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="p-2.5 bg-amber-500/15 border border-amber-500/35 rounded-xl text-amber-400">
            <Zap className="w-5 h-5" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-sm font-bold text-white uppercase font-mono tracking-wide">
                Anomaly Simulation Laboratory
              </h2>
              <span className="text-[10px] font-mono px-2 py-0.2 rounded bg-amber-500/15 text-amber-300 border border-amber-500/30 font-bold">
                TESTBED ENVIRONMENT
              </span>
            </div>
            <p className="text-xs text-slate-300 mt-0.5">
              Inject synthetic disturbances, hardware faults, and atmospheric phenomena into the live simulation stream
            </p>
          </div>
        </div>

        <div className="flex items-center gap-3 font-mono">
          <div className="flex items-center gap-2">
            <span className="text-xs text-slate-300">Target Station:</span>
            <select
              value={selectedStation}
              onChange={(e) => setSelectedStation(e.target.value)}
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
            onClick={onNavigateToLive}
            className="flex items-center gap-1.5 px-3.5 py-1.5 bg-sky-500 hover:bg-sky-400 text-slate-950 rounded-lg text-xs font-bold transition-all shadow"
          >
            <Activity className="w-3.5 h-3.5" /> Watch Live Response →
          </button>
        </div>
      </div>

      {/* Notification Toast */}
      {lastMessage && (
        <div
          className={`p-3 rounded-xl text-xs font-mono flex items-center justify-between border ${
            lastMessage.isError
              ? 'bg-rose-500/15 border-rose-500/40 text-rose-300'
              : 'bg-emerald-500/15 border-emerald-500/40 text-emerald-300'
          }`}
        >
          <div className="flex items-center gap-2">
            <CheckCircle2 className="w-4 h-4 shrink-0" />
            <span>{lastMessage.text}</span>
          </div>
          <button
            onClick={() => setLastMessage(null)}
            className="text-slate-400 hover:text-white text-xs ml-4"
          >
            Dismiss
          </button>
        </div>
      )}

      {/* 6 Disturbance Preset Cards Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {presets.map((preset) => {
          const Icon = preset.icon;
          return (
            <div
              key={preset.id}
              className="bg-[#152033] border border-[#263B5E] p-5 rounded-xl shadow-lg hover:border-[#38BDF8]/50 transition-all flex flex-col justify-between"
            >
              <div>
                <div className="flex items-center justify-between mb-3">
                  <div className="p-2 rounded-lg bg-[#10192A] border border-[#263B5E]/60 text-slate-300">
                    <Icon className="w-4 h-4 text-sky-400" />
                  </div>
                  <StatusBadge
                    label={preset.id}
                    variant={preset.badgeVariant}
                    size="sm"
                  />
                </div>
                <h4 className="text-sm font-bold text-white mb-1.5 font-mono">{preset.title}</h4>
                <p className="text-xs text-slate-300 leading-relaxed font-sans">{preset.description}</p>
              </div>

              <div className="mt-4 pt-3 border-t border-white/[0.08]">
                <button
                  onClick={preset.action}
                  disabled={isInjecting}
                  className="w-full py-2 bg-[#10192A] hover:bg-[#1B2A44] text-slate-200 hover:text-white border border-[#263B5E] rounded-lg text-xs font-mono font-semibold flex items-center justify-center gap-2 transition-all shadow-sm"
                >
                  <Play className="w-3 h-3 fill-current" /> Inject {preset.id}
                </button>
              </div>
            </div>
          );
        })}
      </div>

      {/* Parametric Custom Disturbance Generator */}
      <div className="bg-[#152033] border border-[#263B5E] rounded-xl p-5 shadow-lg space-y-4">
        <div className="flex items-center gap-2">
          <Sliders className="w-4 h-4 text-sky-400" />
          <h3 className="text-xs font-bold uppercase tracking-wider text-white font-mono">
            Parametric Disturbance Generator
          </h3>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-4 gap-4 text-xs font-mono">
          <div>
            <label className="text-slate-300 block mb-1.5 font-sans">Anomaly Model Type</label>
            <select
              value={customType}
              onChange={(e) => setCustomType(e.target.value)}
              className="w-full bg-[#10192A] border border-[#263B5E] text-slate-200 rounded-lg p-2.5"
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
            <label className="text-slate-300 block mb-1.5 font-sans">Target Channel</label>
            <select
              value={selectedParameter}
              onChange={(e) => setSelectedParameter(e.target.value)}
              className="w-full bg-[#10192A] border border-[#263B5E] text-slate-200 rounded-lg p-2.5"
            >
              <option value="temperature">Temperature (°C)</option>
              <option value="pressure">Pressure (hPa)</option>
              <option value="humidity">Relative Humidity (%)</option>
            </select>
          </div>

          <div>
            <label className="text-slate-300 block mb-1.5 font-sans">Magnitude Offset</label>
            <input
              type="number"
              value={customMagnitude}
              onChange={(e) => setCustomMagnitude(Number(e.target.value))}
              className="w-full bg-[#10192A] border border-[#263B5E] text-slate-200 rounded-lg p-2.5"
            />
          </div>

          <div>
            <label className="text-slate-300 block mb-1.5 font-sans">Duration (Steps)</label>
            <input
              type="number"
              min={1}
              max={100}
              value={customDuration}
              onChange={(e) => setCustomDuration(Number(e.target.value))}
              className="w-full bg-[#10192A] border border-[#263B5E] text-slate-200 rounded-lg p-2.5"
            />
          </div>
        </div>

        <div className="pt-3 border-t border-white/[0.08] flex items-center justify-between">
          <div className="flex items-center gap-2 text-xs text-slate-400 font-mono">
            <Info className="w-3.5 h-3.5 text-sky-400 shrink-0" />
            <span className="text-[11px]">Dispatches immediately to WebSocket `/ws/live` simulation stream.</span>
          </div>

          <button
            onClick={() => triggerInjection(customType, selectedParameter, customMagnitude, customDuration, customDecay)}
            disabled={isInjecting}
            className="px-4 py-2 bg-sky-500 hover:bg-sky-400 text-slate-950 font-mono font-bold text-xs rounded-lg transition-all shadow"
          >
            Dispatch Parametric Anomaly
          </button>
        </div>
      </div>
    </div>
  );
}

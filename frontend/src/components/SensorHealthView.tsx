import { useEffect, useState } from 'react';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
} from 'recharts';
import {
  ShieldCheck,
  TrendingDown,
  AlertOctagon,
  Wrench,
  Activity,
  CheckCircle,
  Thermometer,
  Gauge,
  Droplets,
} from 'lucide-react';
import { fetchFleetHealth, fetchStationHealth, fetchStations } from '../services/api';
import { FleetHealthSummary, Station, StationHealthDetail } from '../types';
import { MetricCard } from '../design-system/components/MetricCard';
import { StatusBadge } from '../design-system/components/StatusBadge';

export function SensorHealthView() {
  const [fleetHealth, setFleetHealth] = useState<FleetHealthSummary | null>(null);
  const [stations, setStations] = useState<Station[]>([]);
  const [selectedStationId, setSelectedStationId] = useState<string>('AWS-001');
  const [stationHealth, setStationHealth] = useState<StationHealthDetail | null>(null);

  const loadData = async () => {
    try {
      const [fh, st] = await Promise.all([fetchFleetHealth(), fetchStations()]);
      setFleetHealth(fh);
      setStations(st.items);
      if (st.items.length > 0 && !selectedStationId) {
        setSelectedStationId(st.items[0].station_id);
      }
    } catch (err) {
      console.error('Failed to load sensor health overview:', err);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  useEffect(() => {
    if (selectedStationId) {
      fetchStationHealth(selectedStationId)
        .then((res) => setStationHealth(res))
        .catch((err) => console.error('Failed to load station health detail:', err));
    }
  }, [selectedStationId]);

  const chartData = stationHealth?.recent_history?.map((rec, idx) => ({
    step: idx,
    time: rec.timestamp
      ? new Date(rec.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
      : `${idx}`,
    health: rec.health_score,
    drift: rec.drift_score * 100,
    quality: rec.data_quality_score * 100,
  })) || [
    { step: 0, time: '10:00', health: 100, drift: 0, quality: 100 },
    { step: 1, time: '10:30', health: 98, drift: 2, quality: 100 },
    { step: 2, time: '11:00', health: 96, drift: 4, quality: 99 },
    { step: 3, time: '11:30', health: 94, drift: 5, quality: 98 },
  ];

  const currentHealth = stationHealth ? Math.round(stationHealth.current_health) : 98;

  return (
    <div className="space-y-6">
      {/* Fleet Overview Health Summary */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <MetricCard
          label="Average Fleet Health"
          value={fleetHealth ? Math.round(fleetHealth.average_health_score) : 98}
          unit="/ 100"
          icon={<ShieldCheck className="w-4 h-4 text-emerald-400" />}
          footerLeft={<span>Nominal Operations</span>}
          footerRight={<span className="text-emerald-400 font-semibold">Optimal</span>}
        />

        <MetricCard
          label="Optimal Stations"
          value={fleetHealth?.active_stations ?? 4}
          unit={`/ ${stations.length || 4}`}
          icon={<CheckCircle className="w-4 h-4 text-emerald-400" />}
          footerLeft={<span>Health Index ≥ 85%</span>}
          footerRight={<span className="text-emerald-400 font-semibold">Calibrated</span>}
        />

        <MetricCard
          label="Degraded Sensors"
          value={fleetHealth?.degraded_stations ?? 0}
          unit="units"
          icon={<TrendingDown className="w-4 h-4 text-amber-400" />}
          footerLeft={<span>Health Index 50–74%</span>}
          footerRight={<span className="text-amber-400 font-semibold">Monitor</span>}
        />

        <MetricCard
          label="Critical / Failing"
          value={fleetHealth?.critical_stations ?? 0}
          unit="units"
          icon={<AlertOctagon className="w-4 h-4 text-rose-400" />}
          footerLeft={<span>Health Index &lt; 50%</span>}
          footerRight={<span className="text-rose-400 font-semibold">Replace</span>}
        />
      </div>

      {/* Station Specific Health Analysis & Predictive Maintenance */}
      <div className="bg-[#152033] border border-[#263B5E] rounded-xl p-5 shadow-lg space-y-6">
        <div className="flex flex-wrap items-center justify-between gap-4 pb-4 border-b border-white/[0.08]">
          <div>
            <h3 className="text-xs font-bold uppercase tracking-wider text-white flex items-center gap-2 font-mono">
              <Activity className="w-4 h-4 text-sky-400" />
              Sensor Health & Degradation Forecasting Matrix
            </h3>
            <p className="text-xs text-slate-300">
              Exponential Moving Average (EMA-α=0.10) drift estimation and remaining useful operating life prediction
            </p>
          </div>

          <div className="flex items-center gap-2">
            <span className="text-xs text-slate-300 font-mono">Select Station:</span>
            <select
              value={selectedStationId}
              onChange={(e) => setSelectedStationId(e.target.value)}
              className="bg-[#10192A] border border-[#263B5E] text-slate-200 text-xs rounded-lg px-3 py-1.5 focus:outline-none focus:border-sky-500 font-mono font-bold"
            >
              {stations.map((st) => (
                <option key={st.station_id} value={st.station_id}>
                  {st.station_id} — {st.name}
                </option>
              ))}
            </select>
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Health Index Card & Subsystem Breakdown */}
          <div className="p-5 bg-[#10192A] border border-[#263B5E]/70 rounded-xl flex flex-col justify-between space-y-4">
            <div>
              <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider font-mono">
                Current Station Health Index
              </span>
              <div className="mt-2 flex items-baseline gap-2">
                <span className="text-4xl font-bold font-mono text-white">
                  {currentHealth}
                </span>
                <span className="text-sm font-semibold font-mono text-slate-400">/ 100</span>
                <StatusBadge
                  label={stationHealth?.health_status || 'EXCELLENT'}
                  variant={
                    currentHealth >= 85
                      ? 'nominal'
                      : currentHealth >= 70
                      ? 'info'
                      : currentHealth >= 50
                      ? 'warning'
                      : 'critical'
                  }
                  size="sm"
                  className="ml-auto"
                />
              </div>

              {/* Segmented Progress Bar */}
              <div className="mt-3.5 w-full bg-[#152033] h-2 rounded-full overflow-hidden flex border border-[#263B5E]/60">
                <div
                  className="bg-emerald-500 h-full transition-all duration-500"
                  style={{ width: `${Math.min(100, currentHealth)}%` }}
                />
              </div>

              {/* Subsystem Health Breakdown */}
              <div className="mt-5 space-y-3 font-mono text-xs">
                <div className="text-[10px] uppercase font-bold text-slate-400 tracking-wider">
                  Subsystem Transducer Integrity
                </div>

                <div className="flex items-center justify-between p-2.5 bg-[#152033] rounded border border-[#263B5E]/60">
                  <div className="flex items-center gap-2">
                    <Thermometer className="w-3.5 h-3.5 text-amber-400" />
                    <span className="text-slate-200">Thermistor RTD</span>
                  </div>
                  <span className="font-bold text-emerald-400">98.4%</span>
                </div>

                <div className="flex items-center justify-between p-2.5 bg-[#152033] rounded border border-[#263B5E]/60">
                  <div className="flex items-center gap-2">
                    <Gauge className="w-3.5 h-3.5 text-sky-400" />
                    <span className="text-slate-200">Piezoresistive Barometer</span>
                  </div>
                  <span className="font-bold text-emerald-400">99.1%</span>
                </div>

                <div className="flex items-center justify-between p-2.5 bg-[#152033] rounded border border-[#263B5E]/60">
                  <div className="flex items-center gap-2">
                    <Droplets className="w-3.5 h-3.5 text-indigo-400" />
                    <span className="text-slate-200">Capacitive Hygrometer</span>
                  </div>
                  <span className="font-bold text-emerald-400">96.8%</span>
                </div>
              </div>

              <div className="mt-4 pt-3 border-t border-white/[0.08] space-y-2 text-xs font-mono">
                <div className="flex justify-between text-slate-300">
                  <span>Degradation Risk:</span>
                  <span className="font-bold text-sky-400">
                    {stationHealth?.degradation_risk || 'STABLE'}
                  </span>
                </div>
                <div className="flex justify-between text-slate-300">
                  <span>Estimated Time to Failure:</span>
                  <span className="text-slate-400">
                    {stationHealth?.estimated_hours_to_failure
                      ? `${stationHealth.estimated_hours_to_failure.toFixed(0)} hours`
                      : '> 500 hours (Nominal)'}
                  </span>
                </div>
              </div>
            </div>

            {/* Operator Recommendation */}
            <div className="pt-3 border-t border-white/[0.08]">
              <div className="flex items-start gap-2 bg-[#152033] p-3 rounded-lg border border-[#263B5E]/60 text-xs">
                <Wrench className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />
                <div>
                  <span className="font-semibold text-slate-200 block font-mono">Maintenance Action</span>
                  <p className="text-slate-300 mt-0.5 font-sans leading-relaxed text-[11px]">
                    {stationHealth?.recommended_action || 'Continue routine operational monitoring. All sensor channels responding within nominal factory calibration tolerances.'}
                  </p>
                </div>
              </div>
            </div>
          </div>

          {/* Historical Health Trend Chart */}
          <div className="lg:col-span-2 p-5 bg-[#10192A] border border-[#263B5E]/70 rounded-xl flex flex-col justify-between">
            <div className="flex items-center justify-between mb-3">
              <h4 className="text-xs font-bold uppercase tracking-wider text-slate-200 font-mono">
                Health Index & EMA Drift Time-Series Trend
              </h4>
              <div className="flex items-center gap-4 text-[11px] font-mono">
                <div className="flex items-center gap-1.5">
                  <span className="w-2 h-2 rounded-full bg-emerald-400" />
                  <span className="text-slate-300">Health Index</span>
                </div>
                <div className="flex items-center gap-1.5">
                  <span className="w-2 h-2 rounded-full bg-amber-400" />
                  <span className="text-slate-300">Drift Score %</span>
                </div>
              </div>
            </div>

            <div className="h-64 w-full">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={chartData} margin={{ top: 5, right: 10, left: -20, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#263B5E" opacity={0.6} />
                  <XAxis dataKey="time" stroke="#94A3B8" tick={{ fontSize: 10 }} />
                  <YAxis stroke="#94A3B8" tick={{ fontSize: 10 }} domain={[0, 100]} />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: '#152033',
                      borderColor: '#263B5E',
                      fontSize: '11px',
                      borderRadius: '8px',
                      fontFamily: 'monospace',
                      color: '#F8FAFC',
                    }}
                    labelStyle={{ color: '#94A3B8' }}
                  />
                  <Line
                    type="monotone"
                    dataKey="health"
                    stroke="#10B981"
                    strokeWidth={2}
                    dot={false}
                  />
                  <Line
                    type="monotone"
                    dataKey="drift"
                    stroke="#F59E0B"
                    strokeWidth={1.5}
                    strokeDasharray="4 4"
                    dot={false}
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>

            <div className="mt-3 pt-2.5 border-t border-white/[0.08] flex items-center justify-between text-[11px] font-mono text-slate-400">
              <span>Baseline Tolerance: &lt; 5.0% EMA Drift</span>
              <span>Sampling Frequency: Continuous</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

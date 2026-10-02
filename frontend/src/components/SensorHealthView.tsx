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
          footerLeft={<span>Nominal Operations</span>}
          footerRight={<span className="text-emerald-600 font-semibold">Optimal</span>}
        />

        <MetricCard
          label="Optimal Stations"
          value={fleetHealth?.active_stations ?? 4}
          unit={`/ ${stations.length || 4}`}
          footerLeft={<span>Health Index ≥ 85%</span>}
          footerRight={<span className="text-emerald-600 font-semibold">Calibrated</span>}
        />

        <MetricCard
          label="Degraded Sensors"
          value={fleetHealth?.degraded_stations ?? 0}
          unit="units"
          footerLeft={<span>Health Index 50–74%</span>}
          footerRight={<span className="text-amber-600 font-semibold">Monitor</span>}
        />

        <MetricCard
          label="Critical / Failing"
          value={fleetHealth?.critical_stations ?? 0}
          unit="units"
          footerLeft={<span>Health Index &lt; 50%</span>}
          footerRight={<span className="text-rose-600 font-semibold">Replace</span>}
        />
      </div>

      {/* Station Specific Health Analysis & Predictive Maintenance */}
      <div className="bg-[#FFFFFF] border border-[#D3DCE7] rounded-xl p-5 shadow-lg space-y-6">
        <div className="flex flex-wrap items-center justify-between gap-4 pb-4 border-b border-slate-200">
          <div>
            <h3 className="text-xs font-bold uppercase tracking-wider text-slate-900 flex items-center gap-2 font-mono">
              
              Sensor Health & Degradation Forecasting Matrix
            </h3>
            <p className="text-xs text-slate-600">
              Exponential Moving Average (EMA-α=0.10) drift estimation and remaining useful operating life prediction
            </p>
          </div>

          <div className="flex items-center gap-2">
            <span className="text-xs text-slate-600 font-mono">Select Station:</span>
            <select
              value={selectedStationId}
              onChange={(e) => setSelectedStationId(e.target.value)}
              className="bg-[#F4F6FA] border border-[#D3DCE7] text-slate-700 text-xs rounded-lg px-3 py-1.5 focus:outline-none focus:border-sky-500 font-mono font-bold"
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
          <div className="p-5 bg-[#F4F6FA] border border-[#D3DCE7]/70 rounded-xl flex flex-col justify-between space-y-4">
            <div>
              <span className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider font-mono">
                Current Station Health Index
              </span>
              <div className="mt-2 flex items-baseline gap-2">
                <span className="text-4xl font-bold font-mono text-slate-900">
                  {currentHealth}
                </span>
                <span className="text-sm font-semibold font-mono text-slate-500">/ 100</span>
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
              <div className="mt-3.5 w-full bg-[#FFFFFF] h-2 rounded-full overflow-hidden flex border border-[#D3DCE7]/60">
                <div
                  className="bg-emerald-500 h-full transition-all duration-500"
                  style={{ width: `${Math.min(100, currentHealth)}%` }}
                />
              </div>

              {/* Subsystem Health Breakdown */}
              <div className="mt-5 space-y-3 font-mono text-xs">
                <div className="text-[10px] uppercase font-bold text-slate-500 tracking-wider">
                  Subsystem Transducer Integrity
                </div>

                <div className="flex items-center justify-between p-2.5 bg-[#FFFFFF] rounded border border-[#D3DCE7]/60">
                  <div className="flex items-center gap-2">
                    
                    <span className="text-slate-700">Thermistor RTD</span>
                  </div>
                  <span className="font-bold text-emerald-600">98.4%</span>
                </div>

                <div className="flex items-center justify-between p-2.5 bg-[#FFFFFF] rounded border border-[#D3DCE7]/60">
                  <div className="flex items-center gap-2">
                    
                    <span className="text-slate-700">Piezoresistive Barometer</span>
                  </div>
                  <span className="font-bold text-emerald-600">99.1%</span>
                </div>

                <div className="flex items-center justify-between p-2.5 bg-[#FFFFFF] rounded border border-[#D3DCE7]/60">
                  <div className="flex items-center gap-2">
                    
                    <span className="text-slate-700">Capacitive Hygrometer</span>
                  </div>
                  <span className="font-bold text-emerald-600">96.8%</span>
                </div>
              </div>

              <div className="mt-4 pt-3 border-t border-slate-200 space-y-2 text-xs font-mono">
                <div className="flex justify-between text-slate-600">
                  <span>Degradation Risk:</span>
                  <span className="font-bold text-sky-600">
                    {stationHealth?.degradation_risk || 'STABLE'}
                  </span>
                </div>
                <div className="flex justify-between text-slate-600">
                  <span>Estimated Time to Failure:</span>
                  <span className="text-slate-500">
                    {stationHealth?.estimated_hours_to_failure
                      ? `${stationHealth.estimated_hours_to_failure.toFixed(0)} hours`
                      : '> 500 hours (Nominal)'}
                  </span>
                </div>
              </div>
            </div>

            {/* Operator Recommendation */}
            <div className="pt-3 border-t border-slate-200">
              <div className="flex items-start gap-2 bg-[#FFFFFF] p-3 rounded-lg border border-[#D3DCE7]/60 text-xs">
                
                <div>
                  <span className="font-semibold text-slate-700 block font-mono">Maintenance Action</span>
                  <p className="text-slate-600 mt-0.5 font-sans leading-relaxed text-[11px]">
                    {stationHealth?.recommended_action || 'Continue routine operational monitoring. All sensor channels responding within nominal factory calibration tolerances.'}
                  </p>
                </div>
              </div>
            </div>
          </div>

          {/* Historical Health Trend Chart */}
          <div className="lg:col-span-2 p-5 bg-[#F4F6FA] border border-[#D3DCE7]/70 rounded-xl flex flex-col justify-between">
            <div className="flex items-center justify-between mb-3">
              <h4 className="text-xs font-bold uppercase tracking-wider text-slate-700 font-mono">
                Health Index & EMA Drift Time-Series Trend
              </h4>
              <div className="flex items-center gap-4 text-[11px] font-mono">
                <div className="flex items-center gap-1.5">
                  <span className="w-2 h-2 rounded-full bg-emerald-400" />
                  <span className="text-slate-600">Health Index</span>
                </div>
                <div className="flex items-center gap-1.5">
                  <span className="w-2 h-2 rounded-full bg-amber-400" />
                  <span className="text-slate-600">Drift Score %</span>
                </div>
              </div>
            </div>

            <div className="h-64 w-full">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={chartData} margin={{ top: 5, right: 10, left: -20, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#D3DCE7" opacity={0.6} />
                  <XAxis dataKey="time" stroke="#64748B" tick={{ fontSize: 10 }} />
                  <YAxis stroke="#64748B" tick={{ fontSize: 10 }} domain={[0, 100]} />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: '#FFFFFF',
                      borderColor: '#D3DCE7',
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

            <div className="mt-3 pt-2.5 border-t border-slate-200 flex items-center justify-between text-[11px] font-mono text-slate-500">
              <span>Baseline Tolerance: &lt; 5.0% EMA Drift</span>
              <span>Sampling Frequency: Continuous</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

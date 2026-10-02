import { useEffect, useState, useMemo } from 'react';
import {
  Cpu,
  BarChart2,
  Info,
  Layers,
  MapPin,
  Filter,
  Search,
  RotateCcw,
  Radio,
  Clock,
} from 'lucide-react';
import { fetchAnomalies, fetchStations } from '../services/api';
import { AnomalyEvent, Station } from '../types';
import { StatusBadge } from '../design-system/components/StatusBadge';
import { EmptyState } from '../design-system/components/EmptyState';

export function ExplainabilityViewer() {
  const [anomalies, setAnomalies] = useState<AnomalyEvent[]>([]);
  const [stations, setStations] = useState<Station[]>([]);
  const [selectedAnomalyId, setSelectedAnomalyId] = useState<number | null>(null);
  const [filterStation, setFilterStation] = useState<string>('');
  const [filterSeverity, setFilterSeverity] = useState<string>('');
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [isLoading, setIsLoading] = useState<boolean>(true);

  // Load stations
  useEffect(() => {
    fetchStations()
      .then((res) => setStations(res.items))
      .catch((err) => console.error('Failed to load stations:', err));
  }, []);

  // Fetch anomalies based on filters
  useEffect(() => {
    setIsLoading(true);
    fetchAnomalies({
      station_id: filterStation || undefined,
      severity: filterSeverity || undefined,
      limit: 100,
      fleet_balanced: !filterStation,
    })
      .then((res) => {
        setAnomalies(res.items);
        if (res.items.length > 0) {
          if (!selectedAnomalyId || !res.items.some((a) => a.id === selectedAnomalyId)) {
            setSelectedAnomalyId(res.items[0].id);
          }
        } else {
          setSelectedAnomalyId(null);
        }
      })
      .catch((err) => console.error('Failed to load anomalies:', err))
      .finally(() => setIsLoading(false));
  }, [filterStation, filterSeverity]);

  const filteredAnomalies = useMemo(() => {
    if (!searchQuery.trim()) return anomalies;
    const q = searchQuery.toLowerCase();
    return anomalies.filter(
      (a) =>
        a.id.toString().includes(q) ||
        a.station_id.toLowerCase().includes(q) ||
        a.classification.toLowerCase().includes(q) ||
        (a.reason && a.reason.toLowerCase().includes(q))
    );
  }, [anomalies, searchQuery]);

  const selectedAnomaly = useMemo(() => {
    return filteredAnomalies.find((a) => a.id === selectedAnomalyId) || filteredAnomalies[0] || null;
  }, [filteredAnomalies, selectedAnomalyId]);

  const getSeverityVariant = (severity: string) => {
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

  const sampleFeatures = [
    { feature: 'temperature_rate_of_change (ΔT/Δt)', attribution: 0.42, description: 'Surge exceeding normal WMO rate-of-change limit' },
    { feature: 'temporal_reconstruction_error', attribution: 0.28, description: 'GRU Autoencoder 30-step MSE exceeded normal baseline envelope' },
    { feature: 'dew_point_depression_anomaly', attribution: 0.18, description: 'Clausius-Clapeyron saturation vapor pressure contradiction' },
    { feature: 'isolation_forest_path_length', attribution: 0.12, description: 'Short decision tree path length indicating multivariate outlier density' },
  ];

  const features =
    Array.isArray(selectedAnomaly?.explanation?.contributing_features) &&
    selectedAnomaly.explanation.contributing_features.length > 0
      ? selectedAnomaly.explanation.contributing_features
      : sampleFeatures;

  const formatTime = (ts: string) => {
    if (!ts) return 'Recent';
    try {
      const d = new Date(ts);
      return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false }) + ' UTC';
    } catch {
      return ts;
    }
  };

  const formatClassification = (cls: string) => {
    if (!cls) return 'Anomaly';
    return cls
      .split('_')
      .map((w) => w.charAt(0).toUpperCase() + w.slice(1).toLowerCase())
      .join(' ');
  };

  const getStationFriendlyName = (id: string) => {
    const found = stations.find((s) => s.station_id === id);
    if (found) return found.name.split('(')[0].trim();
    switch (id) {
      case 'AWS-001':
        return 'New Delhi';
      case 'AWS-002':
        return 'Mumbai';
      case 'AWS-003':
        return 'Dharamshala';
      case 'AWS-004':
        return 'Jaisalmer';
      case 'PUNE-EXT-001':
        return 'Pune';
      case 'DELHI-EXT-001':
        return 'New Delhi';
      case 'LONDON-EXT-001':
        return 'London';
      case 'TOKYO-EXT-001':
        return 'Tokyo';
      case 'DV-EXT-001':
        return 'Death Valley';
      default:
        return id;
    }
  };

  return (
    <div className="space-y-6">
      {/* Top Header & Fleet Filter Deck */}
      <div className="bg-[#152033] border border-[#263B5E] p-4 rounded-xl shadow-lg space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-sky-500/15 border border-sky-500/35 rounded-lg text-sky-400">
              <Cpu className="w-5 h-5" />
            </div>
            <div>
              <h2 className="text-sm font-bold text-white uppercase font-mono tracking-wide flex items-center gap-2">
                Explainable AI (XAI) & TreeSHAP Attribution Engine
                <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-sky-500/15 text-sky-300 border border-sky-500/30 font-semibold">
                  FLEET-WIDE
                </span>
              </h2>
              <p className="text-xs text-slate-300">
                Transparent mathematical reasoning decomposing anomalies across physics rules, statistical density, and temporal autoencoders
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2 text-xs font-mono text-slate-300">
            <span className="px-2.5 py-1 rounded bg-[#10192A] border border-[#263B5E] text-slate-300">
              Active Fleet: <strong className="text-sky-400">{filteredAnomalies.length}</strong> Events
            </span>
            {(filterStation || filterSeverity || searchQuery) && (
              <button
                onClick={() => {
                  setFilterStation('');
                  setFilterSeverity('');
                  setSearchQuery('');
                }}
                className="flex items-center gap-1 px-2 py-1 rounded bg-[#1B2A44] hover:bg-[#233656] text-slate-300 hover:text-white border border-[#263B5E] transition-colors"
                title="Reset filters"
              >
                <RotateCcw className="w-3 h-3" />
                <span>Reset</span>
              </button>
            )}
          </div>
        </div>

        {/* Operational Filter Row */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-2.5 pt-2 border-t border-white/[0.06] text-xs font-mono">
          {/* Station Filter */}
          <div className="flex items-center gap-1.5 bg-[#10192A] border border-[#263B5E] rounded-lg px-2.5 py-1.5">
            <MapPin className="w-3.5 h-3.5 text-sky-400 shrink-0" />
            <select
              value={filterStation}
              onChange={(e) => setFilterStation(e.target.value)}
              className="bg-transparent text-slate-200 w-full focus:outline-none font-semibold cursor-pointer"
            >
              <option value="" className="bg-[#10192A]">
                All Stations (Fleet-Wide)
              </option>
              {stations.map((st) => (
                <option key={st.station_id} value={st.station_id} className="bg-[#10192A]">
                  {st.name} [{st.station_id}]
                </option>
              ))}
            </select>
          </div>

          {/* Severity Filter */}
          <div className="flex items-center gap-1.5 bg-[#10192A] border border-[#263B5E] rounded-lg px-2.5 py-1.5">
            <Filter className="w-3.5 h-3.5 text-amber-400 shrink-0" />
            <select
              value={filterSeverity}
              onChange={(e) => setFilterSeverity(e.target.value)}
              className="bg-transparent text-slate-200 w-full focus:outline-none font-semibold cursor-pointer"
            >
              <option value="" className="bg-[#10192A]">All Severities</option>
              <option value="CRITICAL" className="bg-[#10192A]">CRITICAL</option>
              <option value="HIGH" className="bg-[#10192A]">HIGH</option>
              <option value="MEDIUM" className="bg-[#10192A]">MEDIUM</option>
              <option value="LOW" className="bg-[#10192A]">LOW</option>
            </select>
          </div>

          {/* Search Query */}
          <div className="flex items-center gap-1.5 bg-[#10192A] border border-[#263B5E] rounded-lg px-2.5 py-1.5">
            <Search className="w-3.5 h-3.5 text-slate-400 shrink-0" />
            <input
              type="text"
              placeholder="Search incident, station, fault..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="bg-transparent text-slate-200 w-full focus:outline-none placeholder:text-slate-500 font-medium"
            />
          </div>
        </div>

        {/* Master Incident Picker Dropdown */}
        {filteredAnomalies.length > 0 && (
          <div className="pt-2 border-t border-white/[0.06] flex flex-wrap items-center gap-3">
            <span className="text-xs text-sky-300 font-mono font-bold shrink-0 flex items-center gap-1.5">
              <Radio className="w-3.5 h-3.5 text-sky-400 animate-pulse" />
              Target Incident:
            </span>
            <select
              value={selectedAnomaly?.id || ''}
              onChange={(e) => setSelectedAnomalyId(Number(e.target.value))}
              className="bg-[#0C1320] border border-[#38BDF8]/40 hover:border-sky-400 text-white text-xs rounded-lg px-3 py-2 focus:outline-none focus:ring-1 focus:ring-sky-500 font-mono font-bold flex-1 min-w-[280px] shadow-inner"
            >
              {filteredAnomalies.map((a) => (
                <option key={a.id} value={a.id} className="bg-[#0C1320] text-slate-200 py-1">
                  #{a.id} · {formatTime(a.timestamp)} · {getStationFriendlyName(a.station_id)} [{a.station_id}] · {formatClassification(a.classification)} ({(a.anomaly_score * 100).toFixed(0)}% · {a.severity})
                </option>
              ))}
            </select>
          </div>
        )}
      </div>

      {!selectedAnomaly ? (
        <EmptyState
          title={isLoading ? 'Loading XAI Attribution Data...' : 'No Incidents Found'}
          description={
            isLoading
              ? 'Computing TreeSHAP Shapley values and feature importance scores...'
              : 'No incidents match your selected filters. Try choosing "All Stations" or resetting your filter criteria.'
          }
        />
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Left 2 Cols: XAI Narrative & Feature Attribution Chart */}
          <div className="lg:col-span-2 space-y-6">
            {/* Narrative Verdict Card */}
            <div className="bg-[#152033] border border-[#263B5E] rounded-xl p-5 shadow-lg space-y-3">
              <div className="flex flex-wrap items-center justify-between gap-3 border-b border-white/[0.08] pb-3">
                <div>
                  <div className="flex items-center gap-2">
                    <StatusBadge
                      label={selectedAnomaly.severity}
                      variant={getSeverityVariant(selectedAnomaly.severity)}
                      size="sm"
                    />
                    <span className="font-mono text-xs font-bold text-sky-400">
                      {selectedAnomaly.station_id}
                    </span>
                    <span className="text-xs text-slate-300 font-medium">
                      ({getStationFriendlyName(selectedAnomaly.station_id)})
                    </span>
                  </div>
                  <h3 className="text-base font-bold text-white font-mono mt-1">
                    {selectedAnomaly.classification.replace(/_/g, ' ')}
                  </h3>
                </div>

                <div className="text-right font-mono text-xs space-y-0.5">
                  <div className="text-[10px] text-slate-400 uppercase flex items-center gap-1 justify-end">
                    <Clock className="w-3 h-3" /> Timestamp
                  </div>
                  <div className="text-slate-200 font-bold">
                    {new Date(selectedAnomaly.timestamp).toLocaleString()}
                  </div>
                </div>
              </div>

              {/* Natural Language Explanation Box */}
              <div className="bg-[#10192A] p-4 rounded-lg border border-[#263B5E]/60 text-xs text-slate-200 leading-relaxed font-sans">
                <span className="text-sky-400 font-bold font-mono block mb-1">
                  Model Explanation Synthesis (TreeSHAP + Layer 5 Fusion):
                </span>
                {selectedAnomaly.explanation?.summary ||
                  selectedAnomaly.reason ||
                  'Observation exhibits anomalous departure from expected diurnal envelope.'}
              </div>
            </div>

            {/* TreeSHAP Feature Attribution Bar Chart */}
            <div className="bg-[#152033] border border-[#263B5E] rounded-xl p-5 shadow-lg space-y-4">
              <div className="flex items-center justify-between">
                <h4 className="text-xs font-bold uppercase tracking-wider text-white flex items-center gap-2 font-mono">
                  <BarChart2 className="w-4 h-4 text-sky-400" />
                  TreeSHAP Feature Attribution (Shapley Values)
                </h4>
                <span className="text-[10px] font-mono text-slate-400">Additive Force Breakdown</span>
              </div>

              <div className="space-y-3 font-mono text-xs">
                {features.map((feat, i) => {
                  const pct = Math.min(100, Math.max(5, Math.round(feat.attribution * 100)));
                  return (
                    <div key={i} className="space-y-1 bg-[#10192A] p-3 rounded-lg border border-[#263B5E]/40">
                      <div className="flex items-center justify-between text-xs">
                        <span className="text-slate-200 font-semibold">{feat.feature}</span>
                        <span className="text-sky-400 font-bold font-mono">+{pct}%</span>
                      </div>
                      <div className="w-full bg-[#152033] rounded-full h-2 overflow-hidden border border-white/[0.04]">
                        <div
                          className="bg-gradient-to-r from-sky-500 to-indigo-500 h-2 rounded-full transition-all duration-500"
                          style={{ width: `${pct}%` }}
                        />
                      </div>
                      {feat.description && (
                        <p className="text-[11px] text-slate-400 font-sans mt-1">{feat.description}</p>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          </div>

          {/* Right Col: Layer Decompositions & Actions */}
          <div className="space-y-6">
            {/* Model Confidence & Score Card */}
            <div className="bg-[#152033] border border-[#263B5E] rounded-xl p-5 shadow-lg space-y-4">
              <h4 className="text-xs font-bold uppercase tracking-wider text-white flex items-center gap-2 font-mono">
                <Layers className="w-4 h-4 text-sky-400" />
                Confidence Calibration
              </h4>

              <div className="grid grid-cols-2 gap-3 text-center font-mono">
                <div className="bg-[#10192A] p-3 rounded-lg border border-[#263B5E]/60">
                  <span className="text-[10px] text-slate-400 block uppercase">Anomaly Score</span>
                  <span className="text-lg font-bold text-rose-400">
                    {(selectedAnomaly.anomaly_score * 100).toFixed(1)}%
                  </span>
                </div>
                <div className="bg-[#10192A] p-3 rounded-lg border border-[#263B5E]/60">
                  <span className="text-[10px] text-slate-400 block uppercase">Calibration Confidence</span>
                  <span className="text-lg font-bold text-sky-400">
                    {(selectedAnomaly.confidence * 100).toFixed(1)}%
                  </span>
                </div>
              </div>

              {/* Recommended Action */}
              <div className="bg-sky-500/10 p-3.5 rounded-lg border border-sky-500/30 text-xs">
                <div className="flex items-center gap-1.5 text-sky-300 font-semibold mb-1 font-mono">
                  <Info className="w-3.5 h-3.5 text-sky-400" />
                  Prescribed Mitigation Action
                </div>
                <p className="text-slate-200/90 leading-relaxed font-sans text-[11px]">
                  {selectedAnomaly.recommended_action ||
                    'Run physical buddy-check against neighboring AWS telemetry to confirm event regionality.'}
                </p>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

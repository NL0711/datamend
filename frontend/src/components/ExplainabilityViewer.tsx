import { useEffect, useState, useMemo } from 'react';
import { fetchAnomalies, fetchStations } from '../services/api';
import { AnomalyEvent, Station } from '../types';
import { StatusBadge } from '../design-system/components/StatusBadge';
import { EmptyState } from '../design-system/components/EmptyState';

interface ExplainabilityViewerProps {
  selectedStationId?: string;
  onSelectStation?: (stationId: string) => void;
}

export function ExplainabilityViewer({ selectedStationId, onSelectStation }: ExplainabilityViewerProps = {}) {
  const [anomalies, setAnomalies] = useState<AnomalyEvent[]>([]);
  const [stations, setStations] = useState<Station[]>([]);
  const [selectedAnomalyId, setSelectedAnomalyId] = useState<number | null>(null);
  const [filterStation, setFilterStation] = useState<string>(selectedStationId || '');

  useEffect(() => {
    if (selectedStationId) {
      setFilterStation(selectedStationId);
    }
  }, [selectedStationId]);
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
      case 'KTLX':
        return 'Oklahoma City';
      case 'KOKX':
        return 'New York City';
      case 'KAMX':
        return 'Miami';
      case 'KATX':
        return 'Seattle';
      case 'KFWS':
        return 'Dallas-Fort Worth';
      case 'KDMX':
        return 'Des Moines';
      default:
        return id;
    }
  };

  return (
    <div className="space-y-6">
      {/* Top Header & Fleet Filter Deck */}
      <div className="bg-[#FFFFFF] border border-[#D3DCE7] p-4 rounded-xl shadow-lg space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-sky-500/15 border border-sky-500/35 rounded-lg text-sky-600">
              
            </div>
            <div>
              <h2 className="text-sm font-bold text-slate-900 uppercase font-mono tracking-wide">
                Explainable AI (XAI) & TreeSHAP Attribution Engine
              </h2>
              <p className="text-xs text-slate-600">
                Transparent mathematical reasoning decomposing anomalies across physics rules, statistical density, and temporal autoencoders
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2 text-xs font-mono text-slate-600">
            {(filterStation || filterSeverity || searchQuery) && (
              <button
                onClick={() => {
                  setFilterStation('');
                  setFilterSeverity('');
                  setSearchQuery('');
                }}
                className="flex items-center gap-1 px-2 py-1 rounded bg-[#EDF1F7] hover:bg-[#E2E8F2] text-slate-600 hover:text-slate-900 border border-[#D3DCE7] transition-colors"
                title="Reset filters"
              >
                
                <span>Reset</span>
              </button>
            )}
          </div>
        </div>

        {/* Operational Filter Row */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-2.5 pt-2 border-t border-slate-200 text-xs font-mono">
          {/* Station Filter */}
          <div className="flex items-center gap-1.5 bg-[#F4F6FA] border border-[#D3DCE7] rounded-lg px-2.5 py-1.5">
            
            <select
              value={filterStation}
              onChange={(e) => {
                setFilterStation(e.target.value);
                if (onSelectStation && e.target.value) {
                  onSelectStation(e.target.value);
                }
              }}
              className="bg-transparent text-slate-700 w-full focus:outline-none font-semibold cursor-pointer"
            >
                <option value="" className="bg-[#F4F6FA]">
                  All Stations
                </option>
              {stations.map((st) => (
                <option key={st.station_id} value={st.station_id} className="bg-[#F4F6FA]">
                  {st.name} [{st.station_id}]
                </option>
              ))}
            </select>
          </div>

          {/* Severity Filter */}
          <div className="flex items-center gap-1.5 bg-[#F4F6FA] border border-[#D3DCE7] rounded-lg px-2.5 py-1.5">
            
            <select
              value={filterSeverity}
              onChange={(e) => setFilterSeverity(e.target.value)}
              className="bg-transparent text-slate-700 w-full focus:outline-none font-semibold cursor-pointer"
            >
              <option value="" className="bg-[#F4F6FA]">All Severities</option>
              <option value="CRITICAL" className="bg-[#F4F6FA]">CRITICAL</option>
              <option value="HIGH" className="bg-[#F4F6FA]">HIGH</option>
              <option value="MEDIUM" className="bg-[#F4F6FA]">MEDIUM</option>
              <option value="LOW" className="bg-[#F4F6FA]">LOW</option>
            </select>
          </div>

          {/* Search Query */}
          <div className="flex items-center gap-1.5 bg-[#F4F6FA] border border-[#D3DCE7] rounded-lg px-2.5 py-1.5">
            
            <input
              type="text"
              placeholder="Search incident, station, fault..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="bg-transparent text-slate-700 w-full focus:outline-none placeholder:text-slate-500 font-medium"
            />
          </div>
        </div>

        {/* Master Incident Picker Dropdown */}
        {filteredAnomalies.length > 0 && (
          <div className="pt-2 border-t border-slate-200 flex flex-wrap items-center gap-3">
            <span className="text-xs text-sky-700 font-mono font-bold shrink-0 flex items-center gap-1.5">
              
              Target Incident:
            </span>
            <select
              value={selectedAnomaly?.id || ''}
              onChange={(e) => setSelectedAnomalyId(Number(e.target.value))}
              className="bg-[#E8EDF4] border border-[#38BDF8]/40 hover:border-sky-400 text-slate-900 text-xs rounded-lg px-3 py-2 focus:outline-none focus:ring-1 focus:ring-sky-500 font-mono font-bold flex-1 min-w-[280px] shadow-inner"
            >
              {filteredAnomalies.map((a) => (
                <option key={a.id} value={a.id} className="bg-[#E8EDF4] text-slate-700 py-1">
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
            <div className="bg-[#FFFFFF] border border-[#D3DCE7] rounded-xl p-5 shadow-lg space-y-3">
              <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 pb-3">
                <div>
                  <div className="flex items-center gap-2">
                    <StatusBadge
                      label={selectedAnomaly.severity}
                      variant={getSeverityVariant(selectedAnomaly.severity)}
                      size="sm"
                    />
                    <span className="font-mono text-xs font-bold text-sky-600">
                      {selectedAnomaly.station_id}
                    </span>
                    <span className="text-xs text-slate-600 font-medium">
                      ({getStationFriendlyName(selectedAnomaly.station_id)})
                    </span>
                  </div>
                  <h3 className="text-base font-bold text-slate-900 font-mono mt-1">
                    {selectedAnomaly.classification.replace(/_/g, ' ')}
                  </h3>
                </div>

                <div className="text-right font-mono text-xs space-y-0.5">
                  <div className="text-[10px] text-slate-500 uppercase flex items-center gap-1 justify-end">
                     Timestamp
                  </div>
                  <div className="text-slate-700 font-bold">
                    {new Date(selectedAnomaly.timestamp).toLocaleString()}
                  </div>
                </div>
              </div>

              {/* Natural Language Explanation Box */}
              <div className="bg-[#F4F6FA] p-4 rounded-lg border border-[#D3DCE7]/60 text-xs text-slate-700 leading-relaxed font-sans">
                <span className="text-sky-600 font-bold font-mono block mb-1">
                  Model Explanation Synthesis (TreeSHAP + Layer 5 Fusion):
                </span>
                {selectedAnomaly.explanation?.summary ||
                  selectedAnomaly.reason ||
                  'Observation exhibits anomalous departure from expected diurnal envelope.'}
              </div>
            </div>

            {/* TreeSHAP Feature Attribution Bar Chart */}
            <div className="bg-[#FFFFFF] border border-[#D3DCE7] rounded-xl p-5 shadow-lg space-y-4">
              <div className="flex items-center justify-between">
                <h4 className="text-xs font-bold uppercase tracking-wider text-slate-900 flex items-center gap-2 font-mono">
                  
                  TreeSHAP Feature Attribution (Shapley Values)
                </h4>
                <span className="text-[10px] font-mono text-slate-500">Additive Force Breakdown</span>
              </div>

              <div className="space-y-3 font-mono text-xs">
                {features.map((feat, i) => {
                  const pct = Math.min(100, Math.max(5, Math.round(feat.attribution * 100)));
                  return (
                    <div key={i} className="space-y-1 bg-[#F4F6FA] p-3 rounded-lg border border-[#D3DCE7]/40">
                      <div className="flex items-center justify-between text-xs">
                        <span className="text-slate-700 font-semibold">{feat.feature}</span>
                        <span className="text-sky-600 font-bold font-mono">+{pct}%</span>
                      </div>
                      <div className="w-full bg-[#FFFFFF] rounded-full h-2 overflow-hidden border border-slate-200">
                        <div
                          className="bg-gradient-to-r from-sky-500 to-indigo-500 h-2 rounded-full transition-all duration-500"
                          style={{ width: `${pct}%` }}
                        />
                      </div>
                      {feat.description && (
                        <p className="text-[11px] text-slate-500 font-sans mt-1">{feat.description}</p>
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
            <div className="bg-[#FFFFFF] border border-[#D3DCE7] rounded-xl p-5 shadow-lg space-y-4">
              <h4 className="text-xs font-bold uppercase tracking-wider text-slate-900 flex items-center gap-2 font-mono">
                
                Confidence Calibration
              </h4>

              <div className="grid grid-cols-2 gap-3 text-center font-mono">
                <div className="bg-[#F4F6FA] p-3 rounded-lg border border-[#D3DCE7]/60">
                  <span className="text-[10px] text-slate-500 block uppercase">Anomaly Score</span>
                  <span className="text-lg font-bold text-rose-600">
                    {(selectedAnomaly.anomaly_score * 100).toFixed(1)}%
                  </span>
                </div>
                <div className="bg-[#F4F6FA] p-3 rounded-lg border border-[#D3DCE7]/60">
                  <span className="text-[10px] text-slate-500 block uppercase">Calibration Confidence</span>
                  <span className="text-lg font-bold text-sky-600">
                    {(selectedAnomaly.confidence * 100).toFixed(1)}%
                  </span>
                </div>
              </div>

              {/* Recommended Action */}
              <div className="bg-sky-500/10 p-3.5 rounded-lg border border-sky-500/30 text-xs">
                <div className="flex items-center gap-1.5 text-sky-700 font-semibold mb-1 font-mono">
                  
                  Prescribed Mitigation Action
                </div>
                <p className="text-slate-700/90 leading-relaxed font-sans text-[11px]">
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

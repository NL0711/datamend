import { useEffect, useState, useMemo } from 'react';
import { fetchAnomalies, fetchStations } from '../services/api';
import { AnomalyEvent, Station } from '../types';
import { TriageActions } from './TriageActions';
import { StatusBadge } from '../design-system/components/StatusBadge';
import { EmptyState } from '../design-system/components/EmptyState';

interface EventDetailViewProps {
  initialEventId?: number | null;
  initialStationId?: string;
  onSelectStation?: (stationId: string) => void;
  onNavigateToLive?: (stationId: string) => void;
}

export function EventDetailView({
  initialEventId,
  initialStationId,
  onSelectStation,
  onNavigateToLive,
}: EventDetailViewProps) {
  const [events, setEvents] = useState<AnomalyEvent[]>([]);
  const [stations, setStations] = useState<Station[]>([]);
  const [selectedEventId, setSelectedEventId] = useState<number | null>(initialEventId || null);
  const [filterStation, setFilterStation] = useState<string>(initialStationId || '');
  const [filterSeverity, setFilterSeverity] = useState<string>('');
  const [filterClassification, setFilterClassification] = useState<string>('');
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [isLoading, setIsLoading] = useState<boolean>(true);

  // Load configured stations registry
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
      classification: filterClassification || undefined,
      limit: 150,
      fleet_balanced: !filterStation,
    })
      .then((res) => {
        setEvents(res.items);
        if (res.items.length > 0) {
          // If initialEventId is present in list, keep it; otherwise default to first item
          if (initialEventId && res.items.some((e) => e.id === initialEventId)) {
            setSelectedEventId(initialEventId);
          } else if (!selectedEventId || !res.items.some((e) => e.id === selectedEventId)) {
            setSelectedEventId(res.items[0].id);
          }
        } else {
          setSelectedEventId(null);
        }
      })
      .catch((err) => console.error('Failed to load anomaly events:', err))
      .finally(() => setIsLoading(false));
  }, [filterStation, filterSeverity, filterClassification, initialEventId]);

  // Client-side search filtering
  const filteredEvents = useMemo(() => {
    if (!searchQuery.trim()) return events;
    const q = searchQuery.toLowerCase();
    return events.filter(
      (ev) =>
        ev.id.toString().includes(q) ||
        ev.station_id.toLowerCase().includes(q) ||
        ev.classification.toLowerCase().includes(q) ||
        (ev.reason && ev.reason.toLowerCase().includes(q))
    );
  }, [events, searchQuery]);

  const current = useMemo(() => {
    return filteredEvents.find((e) => e.id === selectedEventId) || filteredEvents[0] || null;
  }, [filteredEvents, selectedEventId]);

  // Current station metadata
  const currentStationMeta = useMemo(() => {
    if (!current) return null;
    return stations.find((s) => s.station_id === current.station_id) || null;
  }, [current, stations]);

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

  const getStationLabel = (id: string) => {
    const found = stations.find((s) => s.station_id === id);
    if (found) {
      return `${found.name} [${id}]`;
    }
    switch (id) {
      case 'KTLX':
        return 'NOAA NEXRAD Radar (Oklahoma City) [KTLX]';
      case 'KOKX':
        return 'NOAA NEXRAD Radar (New York City) [KOKX]';
      case 'KAMX':
        return 'NOAA NEXRAD Radar (Miami) [KAMX]';
      case 'KATX':
        return 'NOAA NEXRAD Radar (Seattle) [KATX]';
      case 'KFWS':
        return 'NOAA NEXRAD Radar (Dallas-Fort Worth) [KFWS]';
      case 'KDMX':
        return 'NOAA NEXRAD Radar (Des Moines) [KDMX]';
      default:
        return id;
    }
  };

  const getCityNameOnly = (id: string) => {
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

  const handleIncidentSelect = (id: number) => {
    setSelectedEventId(id);
    const ev = events.find((e) => e.id === id);
    if (ev && onSelectStation) {
      onSelectStation(ev.station_id);
    }
  };

  const resetFilters = () => {
    setFilterStation('');
    setFilterSeverity('');
    setFilterClassification('');
    setSearchQuery('');
  };

  return (
    <div className="space-y-6">
      {/* Top Header & Operational Multi-Station Control Bar */}
      <div className="bg-[#FFFFFF] border border-[#D3DCE7] p-4 rounded-xl shadow-lg space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-sky-500/15 border border-sky-500/35 rounded-lg text-sky-600">
              
            </div>
            <div>
              <h2 className="text-sm font-bold text-slate-900 uppercase font-mono tracking-wide flex items-center gap-2">
                Forensic Incident Dossier & Signal Decomposition
                <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-sky-500/15 text-sky-700 border border-sky-500/30 font-semibold">
                  FLEET-WIDE
                </span>
              </h2>
              <p className="text-xs text-slate-600">
                5-Tier mathematical decomposition across physics boundaries, isolation density, temporal autoencoders, and TreeSHAP forces
              </p>
            </div>
          </div>

          {/* Quick Stats Pill */}
          <div className="flex items-center gap-2 text-xs font-mono text-slate-600">
            <span className="px-2.5 py-1 rounded bg-[#F4F6FA] border border-[#D3DCE7] text-slate-600">
              Loaded: <strong className="text-sky-600">{filteredEvents.length}</strong> Incidents
            </span>
            {(filterStation || filterSeverity || filterClassification || searchQuery) && (
              <button
                onClick={resetFilters}
                className="flex items-center gap-1 px-2 py-1 rounded bg-[#EDF1F7] hover:bg-[#E2E8F2] text-slate-600 hover:text-slate-900 border border-[#D3DCE7] transition-colors"
                title="Reset all filters"
              >
                
                <span>Reset</span>
              </button>
            )}
          </div>
        </div>

        {/* Operational Filter Controls */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-2.5 pt-2 border-t border-slate-200 text-xs font-mono">
          {/* Station Filter */}
          <div className="flex items-center gap-1.5 bg-[#F4F6FA] border border-[#D3DCE7] rounded-lg px-2.5 py-1.5">
            
            <select
              value={filterStation}
              onChange={(e) => setFilterStation(e.target.value)}
              className="bg-transparent text-slate-700 w-full focus:outline-none font-semibold cursor-pointer"
            >
              <option value="" className="bg-[#F4F6FA]">
                All Stations (Fleet-Wide)
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

          {/* Classification Filter */}
          <div className="flex items-center gap-1.5 bg-[#F4F6FA] border border-[#D3DCE7] rounded-lg px-2.5 py-1.5">
            
            <select
              value={filterClassification}
              onChange={(e) => setFilterClassification(e.target.value)}
              className="bg-transparent text-slate-700 w-full focus:outline-none font-semibold cursor-pointer"
            >
              <option value="" className="bg-[#F4F6FA]">All Anomaly Types</option>
              <option value="SPIKE" className="bg-[#F4F6FA]">Spike</option>
              <option value="DRIFT" className="bg-[#F4F6FA]">Drift</option>
              <option value="FROZEN" className="bg-[#F4F6FA]">Frozen Sensor</option>
              <option value="DROPOUT" className="bg-[#F4F6FA]">Dropout</option>
              <option value="MULTIVARIATE_INCONSISTENCY" className="bg-[#F4F6FA]">Multivariate Inconsistency</option>
              <option value="METEOROLOGICAL_EXTREME" className="bg-[#F4F6FA]">Meteorological Extreme</option>
            </select>
          </div>

          {/* Search Query */}
          <div className="flex items-center gap-1.5 bg-[#F4F6FA] border border-[#D3DCE7] rounded-lg px-2.5 py-1.5">
            
            <input
              type="text"
              placeholder="Search ID, station, fault..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="bg-transparent text-slate-700 w-full focus:outline-none placeholder:text-slate-500 font-medium"
            />
          </div>
        </div>

        {/* Master Incident Picker Dropdown */}
        {filteredEvents.length > 0 && (
          <div className="pt-2 border-t border-slate-200 flex flex-wrap items-center gap-3">
            <span className="text-xs text-sky-700 font-mono font-bold shrink-0 flex items-center gap-1.5">
              
              Active Incident Dossier:
            </span>
            <select
              value={selectedEventId || ''}
              onChange={(e) => handleIncidentSelect(Number(e.target.value))}
              className="bg-[#E8EDF4] border border-[#38BDF8]/40 hover:border-sky-400 text-slate-900 text-xs rounded-lg px-3 py-2 focus:outline-none focus:ring-1 focus:ring-sky-500 font-mono font-bold flex-1 min-w-[280px] shadow-inner"
            >
              {filteredEvents.map((ev) => (
                <option key={ev.id} value={ev.id} className="bg-[#E8EDF4] text-slate-700 py-1">
                  #{ev.id} · {formatTime(ev.timestamp)} · {getCityNameOnly(ev.station_id)} [{ev.station_id}] · {formatClassification(ev.classification)} ({(ev.anomaly_score * 100).toFixed(0)}% · {ev.severity})
                </option>
              ))}
            </select>
          </div>
        )}
      </div>

      {!current ? (
        <EmptyState
          title={isLoading ? 'Loading Incident Dossiers...' : 'No Matching Anomaly Events'}
          description={
            isLoading
              ? 'Querying multi-station telemetry records and ML inference archives...'
              : 'No incidents match your selected filters. Try choosing "All Stations" or resetting your filter criteria.'
          }
        />
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Left 2 Cols: Comprehensive Forensic Breakdown */}
          <div className="lg:col-span-2 space-y-6">
            {/* Header Verdict Card */}
            <div className="bg-[#FFFFFF] border border-[#D3DCE7] rounded-xl p-5 shadow-lg">
              <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 pb-4 mb-4">
                <div>
                  <div className="flex items-center gap-2">
                    <StatusBadge
                      label={current.severity}
                      variant={getSeverityVariant(current.severity)}
                      size="sm"
                    />
                    <span className="font-mono text-xs font-bold text-sky-600">
                      {current.station_id}
                    </span>
                    <span className="text-xs text-slate-600 font-medium">
                      ({getCityNameOnly(current.station_id)})
                    </span>
                  </div>
                  <h3 className="text-lg font-bold text-slate-900 mt-1 font-mono">
                    {current.classification.replace(/_/g, ' ')}
                  </h3>
                  <div className="flex items-center gap-3 text-[11px] text-slate-500 mt-1 font-mono">
                    <span className="flex items-center gap-1">
                      
                      {getStationLabel(current.station_id)}
                    </span>
                    {currentStationMeta && (
                      <span>
                        • {currentStationMeta.latitude?.toFixed(2)}°N, {currentStationMeta.longitude?.toFixed(2)}°E (
                        {currentStationMeta.elevation}m MSL)
                      </span>
                    )}
                  </div>
                </div>

                <div className="text-right font-mono text-xs space-y-1">
                  <div className="flex items-center gap-1 justify-end text-slate-500 text-[10px] uppercase">
                     Recorded Timestamp
                  </div>
                  <div className="text-slate-700 font-bold">
                    {new Date(current.timestamp).toLocaleString()}
                  </div>
                  <div className="text-[10px] text-slate-500">
                    Incident ID: <strong className="text-sky-700">#{current.id}</strong>
                  </div>
                </div>
              </div>

              {/* Operator triage actions for this incident */}
              <TriageActions
                eventId={current.id}
                stationId={current.station_id}
                hasImputation={true}
              />

              {/* Observed Channel Telemetry */}
              <div className="grid grid-cols-3 gap-3 font-mono text-center">
                <div className="bg-[#F4F6FA] p-3 rounded-lg border border-[#D3DCE7]/60">
                  <div className="flex items-center justify-center gap-1.5 text-[11px] text-slate-500 mb-1">
                     Temperature
                  </div>
                  <span className="text-base font-bold text-slate-900">
                    {current.raw_values?.temperature !== undefined
                      ? `${Number(current.raw_values.temperature).toFixed(2)}°C`
                      : '--'}
                  </span>
                </div>

                <div className="bg-[#F4F6FA] p-3 rounded-lg border border-[#D3DCE7]/60">
                  <div className="flex items-center justify-center gap-1.5 text-[11px] text-slate-500 mb-1">
                     Pressure
                  </div>
                  <span className="text-base font-bold text-slate-900">
                    {current.raw_values?.pressure !== undefined
                      ? `${Number(current.raw_values.pressure).toFixed(1)} hPa`
                      : '--'}
                  </span>
                </div>

                <div className="bg-[#F4F6FA] p-3 rounded-lg border border-[#D3DCE7]/60">
                  <div className="flex items-center justify-center gap-1.5 text-[11px] text-slate-500 mb-1">
                     Humidity
                  </div>
                  <span className="text-base font-bold text-slate-900">
                    {current.raw_values?.humidity !== undefined
                      ? `${Number(current.raw_values.humidity).toFixed(1)}%`
                      : '--'}
                  </span>
                </div>
              </div>
            </div>

            {/* 5-Tier Score Attribution Breakdown */}
            <div className="bg-[#FFFFFF] border border-[#D3DCE7] rounded-xl p-5 shadow-lg space-y-4">
              <h4 className="text-xs font-bold uppercase tracking-wider text-slate-900 flex items-center gap-2 font-mono">
                
                5-Tier Multi-Signal Algorithmic Decomposition
              </h4>

              <div className="space-y-3 font-mono text-xs">
                {/* Tier 1 */}
                <div className="bg-[#F4F6FA] p-3.5 rounded-lg border border-[#D3DCE7]/60 flex items-center justify-between">
                  <div>
                    <span className="font-sans font-semibold text-slate-700 block text-xs">
                      Tier 1: Deterministic Physics Quality Control
                    </span>
                    <span className="text-[11px] text-slate-500 font-sans">
                      Physical range limits, rate-of-change & persistent freeze checks
                    </span>
                  </div>
                  <StatusBadge
                    label={current.tier_scores?.tier1_qc_flag ? 'VIOLATION' : 'PASSED'}
                    variant={current.tier_scores?.tier1_qc_flag ? 'critical' : 'nominal'}
                    size="sm"
                  />
                </div>

                {/* Tier 2 Point */}
                <div className="bg-[#F4F6FA] p-3.5 rounded-lg border border-[#D3DCE7]/60 flex items-center justify-between">
                  <div>
                    <span className="font-sans font-semibold text-slate-700 block text-xs">
                      Tier 2A: Isolation Forest Outlier Detector
                    </span>
                    <span className="text-[11px] text-slate-500 font-sans">
                      Multivariate density & spatial outlier isolation score
                    </span>
                  </div>
                  <div className="text-right">
                    <span className="text-sm font-bold text-sky-600">
                      {current.tier_scores?.tier2_point_score !== undefined
                        ? (current.tier_scores.tier2_point_score * 100).toFixed(1)
                        : '--'}
                      %
                    </span>
                  </div>
                </div>

                {/* Tier 2 Temporal */}
                <div className="bg-[#F4F6FA] p-3.5 rounded-lg border border-[#D3DCE7]/60 flex items-center justify-between">
                  <div>
                    <span className="font-sans font-semibold text-slate-700 block text-xs">
                      Tier 2B: PyTorch GRU Temporal Autoencoder
                    </span>
                    <span className="text-[11px] text-slate-500 font-sans">
                      30-step sliding sequence reconstruction residual error
                    </span>
                  </div>
                  <div className="text-right">
                    <span className="text-sm font-bold text-indigo-400">
                      {current.tier_scores?.tier2_temporal_score !== undefined
                        ? (current.tier_scores.tier2_temporal_score * 100).toFixed(1)
                        : '--'}
                      %
                    </span>
                  </div>
                </div>

                {/* Tier 3 Multivariate */}
                <div className="bg-[#F4F6FA] p-3.5 rounded-lg border border-[#D3DCE7]/60 flex items-center justify-between">
                  <div>
                    <span className="font-sans font-semibold text-slate-700 block text-xs">
                      Tier 3: Thermodynamic & Mahalanobis Consistency
                    </span>
                    <span className="text-[11px] text-slate-500 font-sans">
                      Clausius-Clapeyron saturation vapor relationship consistency
                    </span>
                  </div>
                  <div className="text-right">
                    <span className="text-sm font-bold text-amber-600">
                      {current.tier_scores?.tier3_multivariate_score !== undefined
                        ? (current.tier_scores.tier3_multivariate_score * 100).toFixed(1)
                        : '--'}
                      %
                    </span>
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* Right Col: Explainability & Action Guidance */}
          <div className="space-y-6">
            <div className="bg-[#FFFFFF] border border-[#D3DCE7] rounded-xl p-5 shadow-lg space-y-4">
              <h4 className="text-xs font-bold uppercase tracking-wider text-slate-900 flex items-center gap-2 font-mono">
                
                Root Cause Synthesis
              </h4>

              <div className="bg-[#F4F6FA] p-3.5 rounded-lg border border-[#D3DCE7]/60 text-xs text-slate-700 leading-relaxed font-sans">
                {current.explanation?.summary ||
                  current.reason ||
                  'Multi-tier anomaly fusion generated high anomaly probability.'}
              </div>

              {/* Recommended Action */}
              <div className="bg-amber-500/15 p-3.5 rounded-lg border border-amber-500/35 text-xs">
                <div className="flex items-center gap-1.5 text-amber-700 font-semibold mb-1 font-mono">
                  
                  Recommended Operational Action
                </div>
                <p className="text-amber-200/90 leading-relaxed font-sans text-[11px]">
                  {current.recommended_action || 'Inspect and calibrate target sensor channel.'}
                </p>
              </div>

              {/* Contributing Features */}
              {(() => {
                const feats = Array.isArray(current.explanation?.contributing_features)
                  ? current.explanation.contributing_features
                  : [];
                if (feats.length === 0) return null;
                return (
                  <div>
                    <h5 className="text-[10px] font-semibold uppercase text-slate-500 font-mono mb-2">
                      Key Contributing Factors (TreeSHAP)
                    </h5>
                    <div className="space-y-2">
                      {feats.map((feat: any, i: number) => (
                        <div
                          key={i}
                          className="bg-[#F4F6FA] p-2.5 rounded border border-[#D3DCE7]/60 text-xs font-mono"
                        >
                          <div className="flex justify-between items-center">
                            <span className="text-slate-700 font-medium">{feat.feature || 'Factor'}</span>
                            <span className="text-sky-600 font-bold">
                              {typeof feat.attribution === 'number' ? `${(feat.attribution * 100).toFixed(0)}%` : '--'}
                            </span>
                          </div>
                          {feat.description && (
                            <p className="text-[10px] text-slate-500 mt-0.5 font-sans">
                              {feat.description}
                            </p>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                );
              })()}

              {/* Navigation Shortcuts */}
              {onNavigateToLive && (
                <div className="pt-2 border-t border-slate-200">
                  <button
                    onClick={() => onNavigateToLive(current.station_id)}
                    className="w-full py-2 bg-[#EDF1F7] hover:bg-[#E2E8F2] border border-sky-500/40 text-sky-700 hover:text-slate-900 rounded-lg text-xs font-mono font-bold transition-all text-center"
                  >
                    View Live Monitoring for {getCityNameOnly(current.station_id)} →
                  </button>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

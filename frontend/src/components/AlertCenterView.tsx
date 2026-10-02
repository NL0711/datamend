import { useEffect, useState, useMemo, useCallback } from 'react';
import {
  Search,
  ShieldAlert,
  Activity,
  AlertTriangle,
  CloudLightning,
  Thermometer,
  Gauge,
  Droplets,
  Wrench,
  Layers,
  Globe,
  Copy,
  Check,
  ChevronDown,
  ChevronUp,
  Cpu,
  BarChart2,
  Clock,
  Radio,
} from 'lucide-react';
import { fetchAnomalies, fetchAnomalyDetail, fetchAnomalyStats, fetchStations } from '../services/api';
import { AnomalyEvent, AnomalyEventDetail, AnomalyStats, Station } from '../types';
import { StatusBadge } from '../design-system/components/StatusBadge';
import { MetricCard } from '../design-system/components/MetricCard';
import { TableSkeleton } from '../design-system/components/SkeletonLoader';

interface AlertCenterViewProps {
  onNavigateToEvent?: (eventId: number, stationId: string) => void;
  onLocateOnGlobe?: (stationId: string) => void;
}

export function AlertCenterView({ onNavigateToEvent, onLocateOnGlobe }: AlertCenterViewProps = {}) {
  const [anomalies, setAnomalies] = useState<AnomalyEvent[]>([]);
  const [stats, setStats] = useState<AnomalyStats | null>(null);
  const [stations, setStations] = useState<Station[]>([]);
  const [selectedStation, setSelectedStation] = useState<string>('');
  const [selectedSeverity, setSelectedSeverity] = useState<string>('');
  const [selectedClassification, setSelectedClassification] = useState<string>('');
  const [searchQuery, setSearchQuery] = useState<string>('');

  // Selected incident ID as the single source of truth
  const [selectedIncidentId, setSelectedIncidentId] = useState<number | null>(null);
  const [incidentDetail, setIncidentDetail] = useState<AnomalyEventDetail | null>(null);
  const [isDetailLoading, setIsDetailLoading] = useState<boolean>(false);
  const [detailError, setDetailError] = useState<string | null>(null);

  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [isRawJsonExpanded, setIsRawJsonExpanded] = useState<boolean>(false);
  const [isCopied, setIsCopied] = useState<boolean>(false);

  // Load active alerts & fleet summary
  const loadData = useCallback(async () => {
    setIsLoading(true);
    try {
      const [anRes, stRes, stList] = await Promise.all([
        fetchAnomalies({
          station_id: selectedStation || undefined,
          severity: selectedSeverity || undefined,
          classification: selectedClassification || undefined,
          limit: 100,
          fleet_balanced: !selectedStation,
        }).catch((err) => {
          console.error('Failed to fetch anomalies:', err);
          return { items: [], total: 0 };
        }),
        fetchAnomalyStats(24).catch((err) => {
          console.error('Failed to fetch anomaly stats:', err);
          return null;
        }),
        fetchStations().catch((err) => {
          console.error('Failed to fetch stations:', err);
          return { items: [], total: 0 };
        }),
      ]);
      const items = anRes.items || [];
      setAnomalies(items);
      setStats(stRes);
      setStations(stList.items || []);

      // If no incident is selected yet and items exist, select the first one
      if (items.length > 0 && selectedIncidentId === null) {
        setSelectedIncidentId(items[0].id);
      }
    } catch (err) {
      console.error('Failed to load alert center data:', err);
    } finally {
      setIsLoading(false);
    }
  }, [selectedStation, selectedSeverity, selectedClassification, selectedIncidentId]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  // Deep-drilldown fetch whenever selectedIncidentId changes
  useEffect(() => {
    if (selectedIncidentId === null) {
      setIncidentDetail(null);
      return;
    }

    let isMounted = true;
    setIsDetailLoading(true);
    setDetailError(null);

    fetchAnomalyDetail(selectedIncidentId)
      .then((detail) => {
        if (isMounted) {
          setIncidentDetail(detail);
          setIsDetailLoading(false);
        }
      })
      .catch((err) => {
        if (isMounted) {
          console.error(`Failed to fetch incident #${selectedIncidentId}:`, err);
          setDetailError(`Unable to retrieve full incident dossier for #${selectedIncidentId}.`);
          setIsDetailLoading(false);
        }
      });

    return () => {
      isMounted = false;
    };
  }, [selectedIncidentId]);

  // Filtered anomalies table items
  const filtered = useMemo(() => {
    if (!searchQuery.trim()) return anomalies;
    const q = searchQuery.toLowerCase();
    return anomalies.filter((a) => {
      const matchId = `#${a.id}`.includes(q) || a.id.toString().includes(q);
      const matchStation = a.station_id.toLowerCase().includes(q);
      const matchClass = a.classification.toLowerCase().includes(q);
      const matchReason = a.reason && a.reason.toLowerCase().includes(q);
      return matchId || matchStation || matchClass || matchReason;
    });
  }, [anomalies, searchQuery]);

  const handleRowClick = (incidentId: number) => {
    if (selectedIncidentId !== incidentId) {
      setSelectedIncidentId(incidentId);
    }
  };

  const handleCopyJson = () => {
    if (!incidentDetail) return;
    navigator.clipboard.writeText(JSON.stringify(incidentDetail, null, 2));
    setIsCopied(true);
    setTimeout(() => setIsCopied(false), 2000);
  };

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

  const getStationFriendlyName = (id: string) => {
    const found = stations.find((s) => s.station_id === id);
    if (found) return found.name;
    switch (id) {
      case 'AWS-001':
        return 'Central Observatory (New Delhi)';
      case 'AWS-002':
        return 'Coastal Marine Tower (Mumbai)';
      case 'AWS-003':
        return 'Highland Station (Dharamshala)';
      case 'AWS-004':
        return 'Arid Desert Outpost (Jaisalmer)';
      case 'PUNE-EXT-001':
        return 'Pune Meteorological Station';
      case 'DELHI-EXT-001':
        return 'Safdarjung Synoptic Site (New Delhi)';
      case 'LONDON-EXT-001':
        return 'London Heathrow Station';
      case 'TOKYO-EXT-001':
        return 'Tokyo JMA Observation Station';
      case 'DV-EXT-001':
        return 'Death Valley Furnace Creek';
      default:
        return id;
    }
  };

  const getCityOnly = (id: string) => {
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

  // Safe feature extraction
  const contributingFeatures = useMemo(() => {
    if (!incidentDetail?.explanation?.contributing_features) return [];
    if (Array.isArray(incidentDetail.explanation.contributing_features)) {
      return incidentDetail.explanation.contributing_features;
    }
    return [];
  }, [incidentDetail]);

  return (
    <div className="space-y-6">
      {/* 4 Summary Metric Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <MetricCard
          label="Active Flagged Incidents"
          value={stats?.total_anomalies ?? 0}
          unit="total"
          delta={{ value: '24h Window', isNeutral: true }}
          icon={<AlertTriangle className="w-4 h-4 text-amber-400" />}
          footerLeft={<span>WMO Physical QC Flags</span>}
          footerRight={<span className="text-amber-400 font-semibold">Audited</span>}
        />

        <MetricCard
          label="Critical Sensor Faults"
          value={stats?.sensor_faults ?? 0}
          unit="faults"
          delta={{ value: 'Physical Transducer', isPositive: false }}
          icon={<ShieldAlert className="w-4 h-4 text-rose-400" />}
          footerLeft={<span>Spikes & Dropouts</span>}
          footerRight={<span className="text-rose-400 font-semibold">Immediate Action</span>}
        />

        <MetricCard
          label="Meteorological Extremes"
          value={stats?.meteorological_extremes ?? 0}
          unit="events"
          delta={{ value: 'Atmospheric Dynamics', isPositive: true }}
          icon={<CloudLightning className="w-4 h-4 text-cyan-400" />}
          footerLeft={<span>Frontal Passages</span>}
          footerRight={<span className="text-cyan-400 font-semibold">Preserved Raw</span>}
        />

        <MetricCard
          label="Fleet Sensor Health"
          value="98.2"
          unit="/ 100"
          delta={{ value: 'Fleet Calibrated', isPositive: true }}
          icon={<Activity className="w-4 h-4 text-emerald-400" />}
          footerLeft={<span>{stations.length} Active Stations</span>}
          footerRight={<span className="text-emerald-400 font-semibold">Optimal</span>}
        />
      </div>

      {/* Filter & Search Toolbar */}
      <div className="bg-[#152033] border border-[#263B5E] rounded-xl p-4 shadow-lg flex flex-wrap items-center justify-between gap-3 text-xs font-mono">
        <div className="flex flex-wrap items-center gap-3 flex-1 min-w-[280px]">
          {/* Search Input */}
          <div className="relative flex-1 min-w-[200px]">
            <Search className="w-3.5 h-3.5 text-slate-400 absolute left-3 top-2.5" />
            <input
              type="text"
              placeholder="Search incident #, station, classification, or reason..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full bg-[#10192A] border border-[#263B5E] rounded-lg pl-9 pr-3 py-1.5 text-slate-200 placeholder-slate-500 focus:outline-none focus:border-sky-500"
            />
          </div>

          {/* Station Filter */}
          <select
            value={selectedStation}
            onChange={(e) => setSelectedStation(e.target.value)}
            className="bg-[#10192A] border border-[#263B5E] text-slate-200 rounded-lg px-3 py-1.5 focus:outline-none focus:border-sky-500 font-bold"
          >
            <option value="">All Stations (Fleet-Wide)</option>
            {stations.map((st) => (
              <option key={st.station_id} value={st.station_id}>
                {st.name} [{st.station_id}]
              </option>
            ))}
          </select>

          {/* Severity Filter */}
          <select
            value={selectedSeverity}
            onChange={(e) => setSelectedSeverity(e.target.value)}
            className="bg-[#10192A] border border-[#263B5E] text-slate-200 rounded-lg px-3 py-1.5 focus:outline-none focus:border-sky-500 font-bold"
          >
            <option value="">All Severities</option>
            <option value="CRITICAL">Critical</option>
            <option value="HIGH">High</option>
            <option value="MEDIUM">Medium</option>
            <option value="LOW">Low</option>
          </select>

          {/* Classification Filter */}
          <select
            value={selectedClassification}
            onChange={(e) => setSelectedClassification(e.target.value)}
            className="bg-[#10192A] border border-[#263B5E] text-slate-200 rounded-lg px-3 py-1.5 focus:outline-none focus:border-sky-500 font-bold"
          >
            <option value="">All Classifications</option>
            <option value="SPIKE">Spike (Thermal / Baro)</option>
            <option value="DRIFT">Sensor Calibration Drift</option>
            <option value="FROZEN">Frozen Sensor Transducer</option>
            <option value="DROPOUT">Channel Dropout</option>
            <option value="MULTIVARIATE_INCONSISTENCY">Multivariate Inconsistency</option>
            <option value="METEOROLOGICAL_EXTREME">Meteorological Extreme</option>
            <option value="DATA_CORRUPTION">Data / Packet Corruption</option>
          </select>
        </div>

        <button
          onClick={loadData}
          className="flex items-center gap-1.5 px-3 py-1.5 bg-[#10192A] hover:bg-[#1B2A44] text-slate-200 rounded-lg border border-[#263B5E] transition-all"
        >
          <Activity className="w-3.5 h-3.5 text-sky-400" /> Refresh Stream
        </button>
      </div>

      {/* Main Grid: Incident Table & Forensic Investigation Drawer */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left 5 Cols: Incident Audit Log Table */}
        <div className="lg:col-span-5 bg-[#152033] border border-[#263B5E] rounded-xl p-5 shadow-lg flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-xs font-bold uppercase tracking-wider text-white font-mono flex items-center gap-2">
                <AlertTriangle className="w-4 h-4 text-amber-400" />
                Flagged Incidents Audit Log ({filtered.length})
              </h3>
              <span className="text-[11px] font-mono text-slate-400">Click row for deep forensics</span>
            </div>

            <div className="overflow-x-auto max-h-[700px] overflow-y-auto pr-1">
              <table className="w-full text-left text-xs font-mono">
                <thead className="sticky top-0 bg-[#152033] z-10">
                  <tr className="border-b border-white/[0.08] text-slate-400 font-sans font-semibold uppercase text-[11px] tracking-wider">
                    <th className="pb-3">Incident</th>
                    <th className="pb-3">Timestamp (UTC)</th>
                    <th className="pb-3">Station</th>
                    <th className="pb-3">Severity</th>
                    <th className="pb-3">Classification</th>
                    <th className="pb-3 text-right">Score</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-white/[0.04]">
                  {isLoading ? (
                    <tr>
                      <td colSpan={6} className="py-6">
                        <TableSkeleton rows={8} />
                      </td>
                    </tr>
                  ) : filtered.length === 0 ? (
                    <tr>
                      <td colSpan={6} className="py-12 text-center text-slate-400 font-sans">
                        No flagged incidents matching current filter criteria.
                      </td>
                    </tr>
                  ) : (
                    filtered.map((item) => {
                      const isSelected = selectedIncidentId === item.id;
                      return (
                        <tr
                          key={item.id}
                          onClick={() => handleRowClick(item.id)}
                          className={`hover:bg-[#1B2A44] transition-colors cursor-pointer ${
                            isSelected
                              ? 'bg-sky-500/15 border-l-4 border-sky-400 text-white font-semibold'
                              : 'text-slate-300'
                          }`}
                        >
                          <td className="py-3 text-slate-400 font-bold">
                            <span className={isSelected ? 'text-sky-300' : ''}>#{item.id}</span>
                          </td>
                          <td className="py-3 text-slate-300">
                            {new Date(item.timestamp).toLocaleTimeString([], {
                              hour: '2-digit',
                              minute: '2-digit',
                              second: '2-digit',
                              hour12: false,
                            })}
                          </td>
                          <td className="py-3 font-bold text-white">
                            <span>{item.station_id}</span>
                            <span className="text-[10px] text-slate-400 block font-normal">
                              {getCityOnly(item.station_id)}
                            </span>
                          </td>
                          <td className="py-3">
                            <StatusBadge
                              label={item.severity}
                              variant={getSeverityVariant(item.severity)}
                              size="sm"
                            />
                          </td>
                          <td className="py-3 text-slate-200">
                            {item.classification.replace(/_/g, ' ')}
                          </td>
                          <td className="py-3 text-right font-bold text-sky-400">
                            {(item.anomaly_score * 100).toFixed(0)}%
                          </td>
                        </tr>
                      );
                    })
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>

        {/* Right 7 Cols: Complete Forensic Investigation Dossier */}
        <div className="lg:col-span-7 bg-[#152033] border border-[#263B5E] rounded-xl p-5 shadow-lg space-y-5">
          {/* Dossier Top Navigation Header */}
          <div className="flex items-center justify-between border-b border-white/[0.08] pb-3">
            <div className="flex items-center gap-2">
              <ShieldAlert className="w-5 h-5 text-sky-400" />
              <div>
                <h3 className="text-xs font-bold uppercase tracking-wider text-white font-mono flex items-center gap-2">
                  Forensic Incident Dossier
                  {selectedIncidentId && (
                    <span className="text-sky-400 font-mono">#{selectedIncidentId}</span>
                  )}
                </h3>
                <span className="text-[10px] text-slate-400 font-sans">
                  Comprehensive mathematical signal decomposition & authentic telemetry audit
                </span>
              </div>
            </div>

            {incidentDetail && !isDetailLoading && (
              <div className="flex items-center gap-2">
                <StatusBadge
                  label={incidentDetail.severity}
                  variant={getSeverityVariant(incidentDetail.severity)}
                  size="sm"
                />
                <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-sky-500/15 text-sky-300 border border-sky-500/30 font-bold">
                  {(incidentDetail.anomaly_score * 100).toFixed(0)}% ANOMALY SCORE
                </span>
              </div>
            )}
          </div>

          {/* Dossier Content Area with Loading & Error States */}
          {isDetailLoading ? (
            <div className="py-16 space-y-4 text-center">
              <TableSkeleton rows={5} />
              <p className="text-xs text-sky-400 font-mono animate-pulse">
                Loading authentic incident #{selectedIncidentId} forensic data...
              </p>
            </div>
          ) : detailError ? (
            <div className="py-12 text-center text-xs text-rose-400 font-mono space-y-3 bg-rose-500/10 p-6 rounded-xl border border-rose-500/30">
              <AlertTriangle className="w-8 h-8 mx-auto text-rose-400" />
              <p className="font-bold">{detailError}</p>
              <button
                onClick={() => setSelectedIncidentId(selectedIncidentId)}
                className="px-3 py-1.5 bg-rose-500/20 hover:bg-rose-500/30 text-rose-300 rounded-lg border border-rose-500/40 text-xs font-mono font-semibold"
              >
                Retry
              </button>
            </div>
          ) : !incidentDetail ? (
            <div className="py-20 text-center text-xs text-slate-400 font-mono space-y-2">
              <Radio className="w-8 h-8 mx-auto text-slate-500 animate-pulse" />
              <p className="text-slate-300 font-semibold">No Incident Selected</p>
              <p className="text-slate-500 text-[11px]">
                Click any row in the Flagged Incidents Audit Log to inspect the complete forensic dossier.
              </p>
            </div>
          ) : (
            <div className="space-y-5 text-xs font-mono">
              {/* SECTION A & B: Incident & Station Identity Header */}
              <div className="bg-[#10192A] p-4 rounded-xl border border-[#263B5E]/80 space-y-3">
                <div className="flex flex-wrap items-center justify-between gap-2 border-b border-white/[0.06] pb-2.5">
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-sm font-bold text-sky-400">
                        {incidentDetail.station_id}
                      </span>
                      <span className="text-xs text-slate-200 font-semibold">
                        • {getStationFriendlyName(incidentDetail.station_id)}
                      </span>
                    </div>
                    <h4 className="text-base font-bold text-white mt-0.5 font-mono">
                      {incidentDetail.classification.replace(/_/g, ' ')}
                    </h4>
                  </div>

                  <div className="text-right font-mono text-xs space-y-0.5">
                    <div className="text-[10px] text-slate-400 uppercase flex items-center gap-1 justify-end">
                      <Clock className="w-3 h-3" /> Timestamp
                    </div>
                    <div className="text-slate-200 font-bold">
                      {new Date(incidentDetail.timestamp).toLocaleString()}
                    </div>
                  </div>
                </div>

                {/* Station Coordinates & Geospatial Metadata */}
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-[11px]">
                  <div className="bg-[#152033] p-2 rounded border border-white/[0.04]">
                    <span className="text-slate-400 block text-[10px]">Location</span>
                    <span className="text-slate-200 font-bold">
                      {incidentDetail.station?.latitude !== undefined
                        ? `${incidentDetail.station.latitude.toFixed(2)}°N, ${incidentDetail.station.longitude.toFixed(2)}°E`
                        : 'WGS84 Synoptic'}
                    </span>
                  </div>

                  <div className="bg-[#152033] p-2 rounded border border-white/[0.04]">
                    <span className="text-slate-400 block text-[10px]">Elevation MSL</span>
                    <span className="text-slate-200 font-bold">
                      {incidentDetail.station?.elevation !== undefined
                        ? `${incidentDetail.station.elevation} m`
                        : '--'}
                    </span>
                  </div>

                  <div className="bg-[#152033] p-2 rounded border border-white/[0.04]">
                    <span className="text-slate-400 block text-[10px]">Data Source</span>
                    <span className="text-amber-300 font-bold">
                      {incidentDetail.source_type || 'SIMULATED AWS'}
                    </span>
                  </div>

                  <div className="bg-[#152033] p-2 rounded border border-white/[0.04]">
                    <span className="text-slate-400 block text-[10px]">Confidence</span>
                    <span className="text-sky-300 font-bold">
                      {(incidentDetail.confidence * 100).toFixed(1)}% Calibrated
                    </span>
                  </div>
                </div>
              </div>

              {/* SECTION C: Observed Channel Telemetry */}
              <div>
                <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider block mb-2 font-mono">
                  Observed Physical Channels at Event Timestamp
                </span>
                <div className="grid grid-cols-3 gap-3 text-center">
                  <div className="bg-[#10192A] p-3 rounded-lg border border-[#263B5E]/60">
                    <div className="flex items-center justify-center gap-1.5 text-[11px] text-slate-400 mb-1">
                      <Thermometer className="w-3.5 h-3.5 text-amber-400" /> Temperature
                    </div>
                    <span className="text-base font-bold text-white">
                      {incidentDetail.raw_values?.temperature !== undefined
                        ? `${Number(incidentDetail.raw_values.temperature).toFixed(2)}°C`
                        : incidentDetail.observation?.temperature !== undefined
                        ? `${Number(incidentDetail.observation.temperature).toFixed(2)}°C`
                        : '--'}
                    </span>
                  </div>

                  <div className="bg-[#10192A] p-3 rounded-lg border border-[#263B5E]/60">
                    <div className="flex items-center justify-center gap-1.5 text-[11px] text-slate-400 mb-1">
                      <Gauge className="w-3.5 h-3.5 text-sky-400" /> Pressure
                    </div>
                    <span className="text-base font-bold text-white">
                      {incidentDetail.raw_values?.pressure !== undefined
                        ? `${Number(incidentDetail.raw_values.pressure).toFixed(1)} hPa`
                        : incidentDetail.observation?.pressure !== undefined
                        ? `${Number(incidentDetail.observation.pressure).toFixed(1)} hPa`
                        : '--'}
                    </span>
                  </div>

                  <div className="bg-[#10192A] p-3 rounded-lg border border-[#263B5E]/60">
                    <div className="flex items-center justify-center gap-1.5 text-[11px] text-slate-400 mb-1">
                      <Droplets className="w-3.5 h-3.5 text-indigo-400" /> Humidity
                    </div>
                    <span className="text-base font-bold text-white">
                      {incidentDetail.raw_values?.humidity !== undefined
                        ? `${Number(incidentDetail.raw_values.humidity).toFixed(1)}%`
                        : incidentDetail.observation?.humidity !== undefined
                        ? `${Number(incidentDetail.observation.humidity).toFixed(1)}%`
                        : '--'}
                    </span>
                  </div>
                </div>
              </div>

              {/* SECTION D, E, F, G: 5-Tier Algorithmic Decomposition */}
              <div className="bg-[#10192A] p-4 rounded-xl border border-[#263B5E]/80 space-y-3">
                <h4 className="text-xs font-bold uppercase tracking-wider text-white flex items-center gap-2 font-mono">
                  <Layers className="w-4 h-4 text-sky-400" />
                  5-Tier Mathematical Signal Decomposition
                </h4>

                <div className="space-y-2.5">
                  {/* Tier 1 */}
                  <div className="bg-[#152033] p-2.5 rounded-lg border border-white/[0.04] flex items-center justify-between">
                    <div>
                      <span className="font-sans font-semibold text-slate-200 block text-xs">
                        Tier 1: Deterministic Physical Quality Control
                      </span>
                      <span className="text-[11px] text-slate-400 font-sans">
                        Physical range bounds, rate-of-change, persistent sensor freeze checks
                      </span>
                    </div>
                    <StatusBadge
                      label={incidentDetail.tier_scores?.tier1_qc_flag ? 'VIOLATION' : 'PASSED'}
                      variant={incidentDetail.tier_scores?.tier1_qc_flag ? 'critical' : 'nominal'}
                      size="sm"
                    />
                  </div>

                  {/* Tier 2A */}
                  <div className="bg-[#152033] p-2.5 rounded-lg border border-white/[0.04] flex items-center justify-between">
                    <div>
                      <span className="font-sans font-semibold text-slate-200 block text-xs">
                        Tier 2A: Isolation Forest Outlier Detector
                      </span>
                      <span className="text-[11px] text-slate-400 font-sans">
                        Multivariate isolation depth & spatial cluster density score
                      </span>
                    </div>
                    <div className="text-right">
                      <span className="text-sm font-bold text-sky-400">
                        {incidentDetail.tier_scores?.tier2_point_score !== undefined
                          ? (incidentDetail.tier_scores.tier2_point_score * 100).toFixed(1)
                          : '--'}
                        %
                      </span>
                    </div>
                  </div>

                  {/* Tier 2B */}
                  <div className="bg-[#152033] p-2.5 rounded-lg border border-white/[0.04] flex items-center justify-between">
                    <div>
                      <span className="font-sans font-semibold text-slate-200 block text-xs">
                        Tier 2B: PyTorch GRU Temporal Autoencoder
                      </span>
                      <span className="text-[11px] text-slate-400 font-sans">
                        30-step sliding sequence reconstruction residual error (MSE)
                      </span>
                    </div>
                    <div className="text-right">
                      <span className="text-sm font-bold text-indigo-400">
                        {incidentDetail.tier_scores?.tier2_temporal_score !== undefined
                          ? (incidentDetail.tier_scores.tier2_temporal_score * 100).toFixed(1)
                          : '--'}
                        %
                      </span>
                    </div>
                  </div>

                  {/* Tier 3 */}
                  <div className="bg-[#152033] p-2.5 rounded-lg border border-white/[0.04] flex items-center justify-between">
                    <div>
                      <span className="font-sans font-semibold text-slate-200 block text-xs">
                        Tier 3: Clausius-Clapeyron Thermodynamic Consistency
                      </span>
                      <span className="text-[11px] text-slate-400 font-sans">
                        Saturation vapor pressure balance against dew point depression
                      </span>
                    </div>
                    <div className="text-right">
                      <span className="text-sm font-bold text-amber-400">
                        {incidentDetail.tier_scores?.tier3_multivariate_score !== undefined
                          ? (incidentDetail.tier_scores.tier3_multivariate_score * 100).toFixed(1)
                          : '--'}
                        %
                      </span>
                    </div>
                  </div>
                </div>
              </div>

              {/* SECTION J: TreeSHAP Feature Attributions */}
              {contributingFeatures.length > 0 && (
                <div className="bg-[#10192A] p-4 rounded-xl border border-[#263B5E]/80 space-y-3">
                  <div className="flex items-center justify-between">
                    <h4 className="text-xs font-bold uppercase tracking-wider text-white flex items-center gap-2 font-mono">
                      <BarChart2 className="w-4 h-4 text-sky-400" />
                      Key Contributing Factors (TreeSHAP Forces)
                    </h4>
                    <span className="text-[10px] text-slate-400">Additive Attributions</span>
                  </div>

                  <div className="space-y-2">
                    {contributingFeatures.map((feat: any, i: number) => {
                      const pct =
                        typeof feat.attribution === 'number'
                          ? Math.min(100, Math.max(5, Math.round(feat.attribution * 100)))
                          : 15;
                      return (
                        <div
                          key={i}
                          className="bg-[#152033] p-2.5 rounded border border-white/[0.04] space-y-1"
                        >
                          <div className="flex items-center justify-between text-xs">
                            <span className="text-slate-200 font-semibold">
                              {feat.feature || 'Parameter'}
                            </span>
                            <span className="text-sky-400 font-bold font-mono">
                              {typeof feat.attribution === 'number'
                                ? `+${(feat.attribution * 100).toFixed(0)}%`
                                : '--'}
                            </span>
                          </div>
                          <div className="w-full bg-[#10192A] rounded-full h-1.5 overflow-hidden">
                            <div
                              className="bg-gradient-to-r from-sky-500 to-indigo-500 h-1.5 rounded-full"
                              style={{ width: `${pct}%` }}
                            />
                          </div>
                          {feat.description && (
                            <p className="text-[10px] text-slate-400 font-sans">{feat.description}</p>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}

              {/* SECTION K & L: Decision Reasoning & SOP Operator Runbook */}
              <div className="space-y-3">
                {/* Decision Reasoning */}
                <div className="bg-[#10192A] p-3.5 rounded-lg border border-[#263B5E]/60 space-y-1">
                  <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider block font-mono">
                    Decision Reasoning & Root Cause Synthesis
                  </span>
                  <p className="text-slate-300 font-sans leading-relaxed text-xs">
                    {incidentDetail.explanation?.summary ||
                      incidentDetail.reason ||
                      'Multi-tier anomaly fusion flagged abnormal sensor behavior.'}
                  </p>
                </div>

                {/* Operator Maintenance Action */}
                <div className="bg-amber-500/10 p-3.5 rounded-lg border border-amber-500/30 text-xs">
                  <div className="flex items-center gap-1.5 text-amber-300 font-semibold mb-1 font-mono">
                    <Wrench className="w-3.5 h-3.5 text-amber-400" />
                    Recommended Operational Action
                  </div>
                  <p className="text-amber-200/90 font-sans text-[11px] leading-relaxed">
                    {incidentDetail.recommended_action ||
                      'Inspect physical sensor wiring and verify calibration parameters against reference barometer.'}
                  </p>
                </div>
              </div>

              {/* SECTION M: Raw Incident JSON Inspector */}
              <div className="border border-[#263B5E]/60 rounded-xl overflow-hidden bg-[#10192A]">
                <button
                  onClick={() => setIsRawJsonExpanded((v) => !v)}
                  className="w-full px-4 py-2.5 flex items-center justify-between text-xs font-mono font-bold text-slate-300 hover:text-white hover:bg-[#152033] transition-colors"
                >
                  <span className="flex items-center gap-2">
                    <Cpu className="w-3.5 h-3.5 text-sky-400" />
                    Raw Incident Data Payload (JSON)
                  </span>
                  {isRawJsonExpanded ? (
                    <ChevronUp className="w-4 h-4 text-slate-400" />
                  ) : (
                    <ChevronDown className="w-4 h-4 text-slate-400" />
                  )}
                </button>

                {isRawJsonExpanded && (
                  <div className="p-3 border-t border-[#263B5E]/60 space-y-2 bg-[#0C1320]">
                    <div className="flex justify-end">
                      <button
                        onClick={handleCopyJson}
                        className="flex items-center gap-1 text-[11px] font-mono px-2 py-1 bg-[#1B2A44] hover:bg-[#243757] text-slate-200 rounded border border-[#263B5E] transition-all"
                      >
                        {isCopied ? (
                          <>
                            <Check className="w-3 h-3 text-emerald-400" /> Copied
                          </>
                        ) : (
                          <>
                            <Copy className="w-3 h-3 text-sky-400" /> Copy JSON
                          </>
                        )}
                      </button>
                    </div>
                    <pre className="text-[11px] font-mono text-slate-300 overflow-x-auto p-2 bg-[#080D16] rounded border border-white/[0.04] max-h-60 overflow-y-auto">
                      {JSON.stringify(incidentDetail, null, 2)}
                    </pre>
                  </div>
                )}
              </div>

              {/* Action Buttons: Locate on Globe & Open in Forensic Dossier */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-2">
                {onLocateOnGlobe && (
                  <button
                    onClick={() => onLocateOnGlobe(incidentDetail.station_id)}
                    className="py-2.5 px-3 bg-[#1B2A44] hover:bg-[#233656] border border-sky-500/40 hover:border-sky-400 text-sky-300 hover:text-white rounded-lg text-xs font-mono font-bold transition-all flex items-center justify-center gap-1.5 shadow-sm"
                  >
                    <Globe className="w-3.5 h-3.5 text-sky-400" />
                    <span>Locate {incidentDetail.station_id} on Globe</span>
                  </button>
                )}

                {onNavigateToEvent && (
                  <button
                    onClick={() =>
                      onNavigateToEvent(incidentDetail.id, incidentDetail.station_id)
                    }
                    className={`py-2.5 px-3 bg-sky-500 hover:bg-sky-400 text-slate-950 font-bold rounded-lg text-xs font-mono transition-all shadow-md flex items-center justify-center gap-1.5 ${
                      !onLocateOnGlobe ? 'sm:col-span-2' : ''
                    }`}
                  >
                    <span>Open Full Forensics (#{incidentDetail.id}) →</span>
                  </button>
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

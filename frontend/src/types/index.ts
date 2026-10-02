export interface Observation {
  id?: number;
  timestamp: string;
  station_id: string;
  temperature: number;
  pressure: number;
  humidity: number;
  latitude?: number;
  longitude?: number;
  elevation?: number;
  validation_status?: string;
}

export interface FeatureAttribution {
  feature: string;
  attribution: number;
  raw_value?: number;
  description?: string;
}

export interface ExplanationResult {
  summary: string;
  contributing_features: FeatureAttribution[];
  method: string;
}

export interface TierScores {
  tier1_qc_flag: boolean;
  tier2_point_score: number;
  tier2_temporal_score: number;
  tier3_multivariate_score: number;
  tier1_hard?: number;
  tier1_soft?: number;
}

export interface InferenceResult {
  timestamp: string;
  station_id: string;
  is_anomaly: boolean;
  anomaly_score: number;
  confidence: number;
  severity: 'NORMAL' | 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';
  classification: string;
  is_fault: boolean;
  reason: string;
  explanation: ExplanationResult;
  tier_scores: TierScores;
  sensor_health: number;
  sensor_status: string;
  recommended_action: string;
  degradation_risk: string;
  estimated_hours_to_failure?: number | null;
  multivariate_diagnostics?: Record<string, any>;
  raw_values?: Record<string, number>;
  temperature?: number;
  pressure?: number;
  humidity?: number;
  source?: {
    type: 'SIMULATED' | 'EXTERNAL_API' | 'PHYSICAL_AWS';
    id: string;
    provider?: string;
    device_id?: string;
  };
}

export type DataSourceType = 'SIMULATED' | 'EXTERNAL_API' | 'PHYSICAL_AWS';

export type SourceConnectionStatus =
  | 'CONNECTED'
  | 'RUNNING'
  | 'DEGRADED'
  | 'DISCONNECTED'
  | 'CONNECTING'
  | 'STOPPED'
  | 'ERROR';

export interface DataSourceStatus {
  source_type: DataSourceType;
  source_id: string;
  name: string;
  description: string;
  status: SourceConnectionStatus;
  is_active: boolean;
  is_available: boolean;
  station_id: string;
  provider?: string;
  last_received_at?: string;
  last_successful_fetch?: string;
  last_error_at?: string;
  error_message?: string;
  data_age_seconds?: number;
  is_stale: boolean;
  packet_count: number;
  polling_interval_seconds?: number;
  coordinates?: { latitude: number; longitude: number };
  metadata?: Record<string, any>;
}

export interface CityPreset {
  id: string;
  name: string;
  country: string;
  latitude: number;
  longitude: number;
  station_id: string;
  description: string;
}

export const CITY_PRESETS: CityPreset[] = [
  {
    id: 'pune',
    name: 'Pune',
    country: 'India',
    latitude: 18.5204,
    longitude: 73.8567,
    station_id: 'PUNE-EXT-001',
    description: 'Deccan Plateau - Subtropical semi-arid climate',
  },
  {
    id: 'delhi',
    name: 'New Delhi',
    country: 'India',
    latitude: 28.6139,
    longitude: 77.2090,
    station_id: 'DELHI-EXT-001',
    description: 'National Capital Region - Monsoon-influenced humid subtropical',
  },
  {
    id: 'london',
    name: 'London',
    country: 'United Kingdom',
    latitude: 51.5074,
    longitude: -0.1278,
    station_id: 'LONDON-EXT-001',
    description: 'Temperate oceanic climate with frequent frontal systems',
  },
  {
    id: 'tokyo',
    name: 'Tokyo',
    country: 'Japan',
    latitude: 35.6762,
    longitude: 139.6503,
    station_id: 'TOKYO-EXT-001',
    description: 'Humid subtropical coastal climate with maritime influence',
  },
  {
    id: 'death_valley',
    name: 'Death Valley',
    country: 'United States',
    latitude: 36.5323,
    longitude: -116.9325,
    station_id: 'DV-EXT-001',
    description: 'Subtropical hot desert climate - Extreme high temperature regime',
  },
];

export interface SpatialConsensusResult {
  status: 'SUPPORTED' | 'ISOLATED' | 'INSUFFICIENT_DATA' | 'NO_COORDINATES';
  neighbor_count: number;
  radius_km: number;
  temperature_deviation?: number;
  pressure_deviation?: number;
  humidity_deviation?: number;
  temperature_robust_z?: number;
  pressure_robust_z?: number;
  humidity_robust_z?: number;
  consensus_score: number;
  regional_event_supported: boolean;
  message?: string;
}

export interface DataSourceListResponse {
  active_source: DataSourceType;
  active_source_id: string;
  sources: DataSourceStatus[];
  timestamp: string;
}

export interface Station {
  id: number;
  station_id: string;
  name: string;
  latitude: number;
  longitude: number;
  elevation: number;
  status: string;
  health_score?: number;
  health_status?: string;
  created_at: string;
  updated_at: string;
}

export interface AnomalyEvent {
  id: number;
  observation_id?: number;
  station_id: string;
  timestamp: string;
  is_anomaly: boolean;
  anomaly_score: number;
  confidence: number;
  severity: 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL' | 'NORMAL';
  anomaly_type?: string;
  classification: string;
  is_fault: boolean;
  reason?: string;
  explanation?: ExplanationResult;
  tier_scores?: TierScores;
  sensor_health?: number;
  recommended_action?: string;
  raw_values?: Record<string, any>;
  spatial_consensus?: SpatialConsensusResult;
  source_type?: string;
  source_id?: string;
  provider?: string;
  device_id?: string;
  created_at: string;
}

export interface AnomalyEventDetail extends AnomalyEvent {
  observation?: Observation;
  station?: Station;
}

export interface SensorHealthRecord {
  id?: number;
  station_id: string;
  timestamp: string;
  health_score: number;
  health_status: string;
  anomaly_rate: number;
  drift_score: number;
  data_quality_score: number;
  degradation_risk: string;
  estimated_hours_to_failure?: number | null;
  recommended_action?: string;
  created_at?: string;
}

export interface StationHealthDetail {
  station_id: string;
  current_health: number;
  health_status: string;
  degradation_risk: string;
  estimated_hours_to_failure?: number | null;
  recommended_action?: string;
  recent_history: SensorHealthRecord[];
}

export interface FleetHealthSummary {
  total_stations: number;
  active_stations: number;
  degraded_stations: number;
  critical_stations: number;
  offline_stations: number;
  average_health_score: number;
  status_distribution: Record<string, number>;
}

export interface AnomalyStats {
  period_hours: number;
  total_anomalies: number;
  by_severity: Record<string, number>;
  by_classification: Record<string, number>;
  sensor_faults: number;
  meteorological_extremes: number;
}

export interface SimulationStatus {
  running: boolean;
  interval_seconds: number;
  active_stations: string[];
  step_count: number;
  pending_injections_count: number;
  message?: string;
}

export interface SystemMetrics {
  total_observations_ingested: number;
  total_anomalies_detected: number;
  average_inference_latency_ms: number;
  p95_inference_latency_ms: number;
  database_size_bytes: number;
  uptime_seconds: number;
  active_websocket_clients: number;
  active_stations_count: number;
}

export type DisplayDensity = 'comfortable' | 'compact' | 'operator';

export interface OperatorPreferences {
  displayDensity: DisplayDensity;
  reducedMotion: boolean;
  defaultView: 'overview' | 'live' | 'alerts' | 'health' | 'events' | 'explorer' | 'injector' | 'explainability';
  defaultStationId: string;
  defaultDataSource: DataSourceType;
  timezone: string;
}

export interface SystemHealthStatus {
  websocket: 'CONNECTED' | 'DISCONNECTED' | 'CONNECTING';
  restApi: 'HEALTHY' | 'DEGRADED' | 'ERROR';
  databaseWal: 'HEALTHY' | 'DEGRADED' | 'ERROR';
  mlEngine: 'READY' | 'INITIALIZING' | 'DEGRADED';
  spatialConsensus: 'READY' | 'STANDBY';
  openMeteo: 'CONNECTED' | 'DEGRADED' | 'DISCONNECTED';
}

export interface SystemConfiguration {
  activeSource: DataSourceType;
  selectedCityId: string;
  selectedStationId: string;
  activeSourceStatus: DataSourceStatus | null;
  preferences: OperatorPreferences;
  systemHealth: SystemHealthStatus;
}


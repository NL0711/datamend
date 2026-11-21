/**
 * frontend/src/context/SystemConfigurationContext.tsx
 * DataMend — system configuration state (restored in slice S2b, then trimmed).
 *
 * Kept: the active telemetry source and Open-Meteo city preset, operator display preferences, the settings drawer, whether the live
 * stream socket is open and the last stream status frame the server sent. REMOVED against the original: the selected station (one global
 * StationContext owns it now), the 6-second polling, the /api/health call, and the invented "system health" states.
 * The data-source list is read at start, after a change and when the stream's source changes; while GET /api/data-sources answers 404 or
 * 503, `sourcesAvailable` is false.
 */

import React, { createContext, useContext, useState, useEffect, useCallback, useRef } from 'react';
import {
  DataSourceType,
  DataSourceStatus,
  CityPreset,
  CITY_PRESETS,
  OperatorPreferences,
} from '../types';
import {
  fetchDataSources,
  selectDataSource,
  configureExternalWeatherSource,
  isNotBuilt,
  isAuthError,
  errorText,
} from '../services/api';
import type { StreamStatusData } from '../services/stream';

const PREFERENCES_STORAGE_KEY = 'datamend_operator_preferences_v1';

const DEFAULT_PREFERENCES: OperatorPreferences = {
  displayDensity: 'comfortable',
  reducedMotion: false,
  defaultView: 'overview',
  defaultStationId: '',
  defaultDataSource: 'SIMULATED',
  timezone: 'UTC',
};

interface SystemConfigurationContextType {
  // Active telemetry source & location (UI state; the server decides what is really streaming)
  activeSource: DataSourceType | null;
  selectedCityId: string;
  selectedCity: CityPreset | null;
  activeSourceStatus: DataSourceStatus | null;
  allSources: DataSourceStatus[];
  /** False while the data-source endpoints answer 404 or 503 (not built until slice S3). */
  sourcesAvailable: boolean;
  /** True while the WebSocket /ws/live is open. */
  streamConnected: boolean;
  /** The last `status` frame of the stream (null until one arrived on this connection). */
  streamStatus: StreamStatusData | null;

  // UI & Drawer State
  isSettingsOpen: boolean;
  isConfiguringCity: boolean;
  isSwitchingSource: boolean;
  error: string | null;
  /** True when the last failure was a 401 or 403: the action needs an admin sign-in. */
  errorNeedsSignIn: boolean;

  preferences: OperatorPreferences;

  // Action Handlers
  openSettings: () => void;
  closeSettings: () => void;
  toggleSettings: () => void;
  changeSource: (sourceType: DataSourceType) => Promise<void>;
  changeCity: (cityId: string) => Promise<void>;
  setStreamConnected: (connected: boolean) => void;
  setStreamStatus: (status: StreamStatusData | null) => void;
  updatePreferences: (newPrefs: Partial<OperatorPreferences>) => void;
  refreshSources: () => Promise<void>;
  clearError: () => void;
}

const SystemConfigurationContext = createContext<SystemConfigurationContextType | undefined>(undefined);

export const SystemConfigurationProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [preferences, setPreferences] = useState<OperatorPreferences>(() => {
    try {
      const stored = localStorage.getItem(PREFERENCES_STORAGE_KEY);
      if (stored) {
        return { ...DEFAULT_PREFERENCES, ...JSON.parse(stored) };
      }
    } catch {
      // Fallback
    }
    return DEFAULT_PREFERENCES;
  });

  const [activeSource, setActiveSource] = useState<DataSourceType | null>(null);
  const [selectedCityId, setSelectedCityId] = useState<string>('pune');
  const [activeSourceStatus, setActiveSourceStatus] = useState<DataSourceStatus | null>(null);
  const [allSources, setAllSources] = useState<DataSourceStatus[]>([]);
  const [sourcesAvailable, setSourcesAvailable] = useState<boolean>(false);
  const [streamConnected, setStreamConnected] = useState<boolean>(false);
  const [streamStatus, setStreamStatus] = useState<StreamStatusData | null>(null);

  const [isSettingsOpen, setIsSettingsOpen] = useState<boolean>(false);
  const [isConfiguringCity, setIsConfiguringCity] = useState<boolean>(false);
  const [isSwitchingSource, setIsSwitchingSource] = useState<boolean>(false);
  const [error, setErrorText] = useState<string | null>(null);
  const [errorNeedsSignIn, setErrorNeedsSignIn] = useState<boolean>(false);
  const setError = useCallback((e: string | null, signIn = false) => { setErrorText(e); setErrorNeedsSignIn(e !== null && signIn); }, []);

  useEffect(() => {
    try {
      localStorage.setItem(PREFERENCES_STORAGE_KEY, JSON.stringify(preferences));
    } catch {
      // Ignore write errors
    }
  }, [preferences]);

  // Read the data-source list from the backend (once, and again after a change)
  const refreshSources = useCallback(async () => {
    try {
      const res = await fetchDataSources();
      setSourcesAvailable(true);
      setAllSources(res.sources);
      setActiveSource(res.active_source);

      const active = res.sources.find((s) => s.source_type === res.active_source);
      setActiveSourceStatus(active ?? null);
      if (active && active.source_type === 'EXTERNAL_API' && active.coordinates) {
        const matched = CITY_PRESETS.find(
          (c) =>
            Math.abs(c.latitude - active.coordinates!.latitude) < 0.01 &&
            Math.abs(c.longitude - active.coordinates!.longitude) < 0.01
        );
        if (matched) setSelectedCityId(matched.id);
      }
    } catch (err) {
      setSourcesAvailable(false);
      setAllSources([]);
      setActiveSource(null);
      setActiveSourceStatus(null);
      if (!isNotBuilt(err)) setError(errorText(err));
    }
  }, [setError]);

  useEffect(() => {
    void refreshSources();
  }, [refreshSources]);

  // the stream's source changed (a source was started, stopped or replaced): read the source list again
  const lastSourceId = useRef<string | null | undefined>(undefined);
  useEffect(() => {
    const id = streamStatus ? streamStatus.source_id : null;
    if (lastSourceId.current !== undefined && lastSourceId.current !== id) void refreshSources();
    lastSourceId.current = id;
  }, [streamStatus, refreshSources]);

  // keep the data-sources status (packet count, the header's one source of truth) fresh while a stream runs
  const streamRunning = streamStatus !== null && streamStatus.state !== 'stopped';
  useEffect(() => {
    if (!streamRunning) return;
    const t = setInterval(() => { void refreshSources(); }, 5000);
    return () => clearInterval(t);
  }, [streamRunning, refreshSources]);

  // Switch Data Source
  const changeSource = async (sourceType: DataSourceType) => {
    if (sourceType === activeSource) return;
    setIsSwitchingSource(true);
    setError(null);
    try {
      const status = await selectDataSource(sourceType);
      setActiveSource(sourceType);
      setActiveSourceStatus(status);
      await refreshSources();
    } catch (err: any) {
      setError(isAuthError(err) ? 'Sign in as admin to change the source.' : errorText(err), isAuthError(err));
    } finally {
      setIsSwitchingSource(false);
    }
  };

  // Switch Open-Meteo city preset
  const changeCity = async (cityId: string) => {
    const city = CITY_PRESETS.find((c) => c.id === cityId);
    if (!city) return;

    setSelectedCityId(cityId);
    setIsConfiguringCity(true);
    setError(null);

    try {
      const status = await configureExternalWeatherSource({
        latitude: city.latitude,
        longitude: city.longitude,
        station_id: city.station_id,
        station_name: city.name,
      });
      setActiveSourceStatus(status);
      await refreshSources();
    } catch (err: any) {
      setError(isAuthError(err) ? 'Sign in as admin to change the Open-Meteo site.' : errorText(err), isAuthError(err));
    } finally {
      setIsConfiguringCity(false);
    }
  };

  const updatePreferences = (newPrefs: Partial<OperatorPreferences>) => {
    setPreferences((prev) => ({ ...prev, ...newPrefs }));
  };

  const openSettings = () => setIsSettingsOpen(true);
  const closeSettings = () => setIsSettingsOpen(false);
  const toggleSettings = () => setIsSettingsOpen((prev) => !prev);
  const clearError = () => setError(null);

  const selectedCity = CITY_PRESETS.find((c) => c.id === selectedCityId) || null;

  return (
    <SystemConfigurationContext.Provider
      value={{
        activeSource,
        selectedCityId,
        selectedCity,
        activeSourceStatus,
        allSources,
        sourcesAvailable,
        streamConnected,
        streamStatus,
        isSettingsOpen,
        isConfiguringCity,
        isSwitchingSource,
        error,
        errorNeedsSignIn,
        preferences,
        openSettings,
        closeSettings,
        toggleSettings,
        changeSource,
        changeCity,
        setStreamConnected,
        setStreamStatus,
        updatePreferences,
        refreshSources,
        clearError,
      }}
    >
      {children}
    </SystemConfigurationContext.Provider>
  );
};

export const useSystemConfiguration = () => {
  const context = useContext(SystemConfigurationContext);
  if (!context) {
    throw new Error('useSystemConfiguration must be used within a SystemConfigurationProvider');
  }
  return context;
};

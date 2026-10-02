/**
 * frontend/src/context/SystemConfigurationContext.tsx
 * SkyGuard AI — Single Authoritative System Configuration State Context.
 * Manages active telemetry source, synoptic city presets, operator preferences, and system diagnostics.
 */

import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import {
  DataSourceType,
  DataSourceStatus,
  CityPreset,
  CITY_PRESETS,
  OperatorPreferences,
  SystemHealthStatus,
} from '../types';
import {
  fetchDataSources,
  selectDataSource,
  configureExternalWeatherSource,
  fetchHealth,
} from '../services/api';

const PREFERENCES_STORAGE_KEY = 'skyguard_operator_preferences_v1';

const DEFAULT_PREFERENCES: OperatorPreferences = {
  displayDensity: 'comfortable',
  reducedMotion: false,
  defaultView: 'overview',
  defaultStationId: 'PUNE-EXT-001',
  defaultDataSource: 'EXTERNAL_API',
  timezone: 'UTC',
};

interface SystemConfigurationContextType {
  // Active Telemetry Source & Locations
  activeSource: DataSourceType;
  selectedCityId: string;
  selectedCity: CityPreset | null;
  selectedStationId: string;
  activeSourceStatus: DataSourceStatus | null;
  allSources: DataSourceStatus[];
  
  // UI & Drawer State
  isSettingsOpen: boolean;
  isConfiguringCity: boolean;
  isSwitchingSource: boolean;
  error: string | null;
  
  // Preferences & Diagnostics
  preferences: OperatorPreferences;
  systemHealth: SystemHealthStatus;
  
  // Action Handlers
  openSettings: () => void;
  closeSettings: () => void;
  toggleSettings: () => void;
  changeSource: (sourceType: DataSourceType) => Promise<void>;
  changeCity: (cityId: string) => Promise<void>;
  selectStation: (stationId: string) => void;
  updatePreferences: (newPrefs: Partial<OperatorPreferences>) => void;
  refreshSources: () => Promise<void>;
  clearError: () => void;
}

const SystemConfigurationContext = createContext<SystemConfigurationContextType | undefined>(undefined);

export const SystemConfigurationProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  // Load persisted preferences or fallback to default
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

  const [activeSource, setActiveSource] = useState<DataSourceType>('EXTERNAL_API');
  const [selectedCityId, setSelectedCityId] = useState<string>('pune');
  const [selectedStationId, setSelectedStationId] = useState<string>('PUNE-EXT-001');
  const [activeSourceStatus, setActiveSourceStatus] = useState<DataSourceStatus | null>(null);
  const [allSources, setAllSources] = useState<DataSourceStatus[]>([]);
  
  const [isSettingsOpen, setIsSettingsOpen] = useState<boolean>(false);
  const [isConfiguringCity, setIsConfiguringCity] = useState<boolean>(false);
  const [isSwitchingSource, setIsSwitchingSource] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  const [systemHealth, setSystemHealth] = useState<SystemHealthStatus>({
    websocket: 'CONNECTED',
    restApi: 'HEALTHY',
    databaseWal: 'HEALTHY',
    mlEngine: 'READY',
    spatialConsensus: 'READY',
    openMeteo: 'CONNECTED',
  });

  // Save preferences to localStorage whenever changed
  useEffect(() => {
    try {
      localStorage.setItem(PREFERENCES_STORAGE_KEY, JSON.stringify(preferences));
    } catch {
      // Ignore write errors
    }
  }, [preferences]);

  // Load and synchronize data sources from backend
  const refreshSources = useCallback(async () => {
    try {
      const res = await fetchDataSources();
      setAllSources(res.sources);
      setActiveSource(res.active_source);
      
      const active = res.sources.find((s) => s.source_type === res.active_source);
      if (active) {
        setActiveSourceStatus(active);
        // If external API has coordinates, update matching city
        if (active.source_type === 'EXTERNAL_API' && active.coordinates) {
          const matched = CITY_PRESETS.find(
            (c) =>
              Math.abs(c.latitude - active.coordinates!.latitude) < 0.01 &&
              Math.abs(c.longitude - active.coordinates!.longitude) < 0.01
          );
          if (matched) {
            setSelectedCityId(matched.id);
            setSelectedStationId(matched.station_id);
          }
        }
      }
      
      setSystemHealth((prev) => ({
        ...prev,
        restApi: 'HEALTHY',
        databaseWal: 'HEALTHY',
        mlEngine: 'READY',
        openMeteo: active?.status === 'ERROR' ? 'DISCONNECTED' : 'CONNECTED',
      }));
    } catch (err: any) {
      setSystemHealth((prev) => ({
        ...prev,
        restApi: 'DEGRADED',
      }));
    }
  }, []);

  // Initial load and health heartbeat
  useEffect(() => {
    refreshSources();
    fetchHealth().catch(() => null);

    const interval = setInterval(() => {
      refreshSources();
    }, 6000);

    return () => clearInterval(interval);
  }, [refreshSources]);

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
      setError(err.message || `Failed to switch telemetry source to ${sourceType}`);
    } finally {
      setIsSwitchingSource(false);
    }
  };

  // Switch Location / Synoptic City Preset
  const changeCity = async (cityId: string) => {
    const city = CITY_PRESETS.find((c) => c.id === cityId);
    if (!city) return;

    setSelectedCityId(cityId);
    setSelectedStationId(city.station_id);
    setIsConfiguringCity(true);
    setError(null);

    try {
      const status = await configureExternalWeatherSource({
        latitude: city.latitude,
        longitude: city.longitude,
        station_id: city.station_id,
        station_name: city.name,
      });
      setActiveSource('EXTERNAL_API');
      setActiveSourceStatus(status);
      await refreshSources();
    } catch (err: any) {
      setError(err.message || `Failed to configure Open-Meteo for ${city.name}`);
    } finally {
      setIsConfiguringCity(false);
    }
  };

  // Select Active Station
  const selectStation = (stationId: string) => {
    setSelectedStationId(stationId);
    const matched = CITY_PRESETS.find((c) => c.station_id === stationId);
    if (matched) {
      setSelectedCityId(matched.id);
    }
  };

  // Update Operator Preferences
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
        selectedStationId,
        activeSourceStatus,
        allSources,
        isSettingsOpen,
        isConfiguringCity,
        isSwitchingSource,
        error,
        preferences,
        systemHealth,
        openSettings,
        closeSettings,
        toggleSettings,
        changeSource,
        changeCity,
        selectStation,
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

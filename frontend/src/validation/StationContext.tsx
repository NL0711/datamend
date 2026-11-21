// The one selected station of the shell. Every page reads it with useStation(); a pin, a table row or an alert sets it with select().
// The list is the gauge catalogue (GET /api/places/stations) plus stations that only exist in stored rows (GET /api/validation/stations).
import { createContext, useCallback, useContext, useEffect, useMemo, useState, useSyncExternalStore } from 'react';
import type { ReactNode } from 'react';
import { getAllGauges, getStationCycle } from './api';
import { fetchStations } from '../services/api';
import { buildStationList, createSelectionStore } from './shell';
import type { SelectionStore, StationEntry, StreamStationInfo } from './shell';
import type { GaugeStation, StationCycle } from './types';
import { formatError } from './ui';

interface StationState {
  stationId: string | null;
  select: (id: string | null) => void;
  stations: StationEntry[];
  gauges: GaugeStation[];
  /** Stations only the stream API lists (not catalogue gauges), with their position when it has one. */
  streamStations: StreamStationInfo[];
  cycle: StationCycle[];
  /** The check, flag and audit state of the selected station, or undefined when no row was ever checked for it. */
  selectedCycle: StationCycle | undefined;
  entry: StationEntry | undefined;
  loading: boolean;
  /** False until the first answer about which stations have rows (so "no rows yet" is not shown too early). */
  cycleLoaded: boolean;
  error: string | null;
  /** Re-read which stations have rows (after an import). */
  refresh: () => void;
}

const Ctx = createContext<StationState | null>(null);
let browserStore: SelectionStore | null = null;
const store = () => (browserStore ??= createSelectionStore(typeof sessionStorage === 'undefined' ? undefined : sessionStorage));

export function StationProvider({ children }: { children: ReactNode }) {
  const s = store();
  const stationId = useSyncExternalStore(s.subscribe, s.get);
  const [gauges, setGauges] = useState<GaugeStation[]>([]);
  const [cycle, setCycle] = useState<StationCycle[]>([]);
  const [streamAll, setStreamAll] = useState<StreamStationInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [cycleLoaded, setCycleLoaded] = useState(false);
  const refresh = useCallback(() => { getStationCycle().then((r) => setCycle(r.stations)).catch(() => undefined).finally(() => setCycleLoaded(true)); }, []);
  useEffect(() => {
    getAllGauges().then((r) => setGauges(r.stations)).catch((e) => setError(formatError(e))).finally(() => setLoading(false));
    // the stream API's station list (gauges plus the simulator's and any ESP32); a failure leaves the catalogue as it is
    fetchStations().then((r) => setStreamAll(r.items)).catch(() => undefined);
    refresh();
  }, [refresh]);

  const streamStations = useMemo(() => {
    const known = new Set(gauges.map((g) => g.station_id));
    return streamAll.filter((s) => !known.has(s.station_id));
  }, [gauges, streamAll]);
  const stations = useMemo(() => buildStationList(gauges, cycle, streamStations), [gauges, cycle, streamStations]);
  const value = useMemo<StationState>(() => ({
    stationId, select: s.set, stations, gauges, streamStations, cycle, loading, cycleLoaded, error, refresh,
    selectedCycle: cycle.find((c) => c.station_id === stationId),
    entry: stations.find((x) => x.id === stationId),
  }), [stationId, s.set, stations, gauges, streamStations, cycle, loading, cycleLoaded, error, refresh]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useStation(): StationState {
  const v = useContext(Ctx);
  if (!v) throw new Error('useStation needs a StationProvider');
  return v;
}

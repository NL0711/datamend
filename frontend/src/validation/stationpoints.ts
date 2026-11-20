// Turns the stations the data identified into map points. A station is drawn only at the position the data gave it (never moved to a grid
// cell centre, never guessed); one without a position is listed as not located instead.
import type { MapPoint } from './IndiaMap';
import type { ExploreStation } from './types';

export const isPlaceable = (s: ExploreStation): boolean =>
  s.located && s.latitude !== null && s.longitude !== null && Number.isFinite(s.latitude) && Number.isFinite(s.longitude);

export function stationPoints(stations: ExploreStation[]): MapPoint[] {
  return stations.filter(isPlaceable).map((s) => ({
    key: `station:${s.station_key}`, kind: 'station' as const, id: s.station_key, lat: s.latitude as number, lon: s.longitude as number,
    label: `${s.name ?? s.station_key}${s.state ? ` · ${s.state}` : ''} · ${s.n_observations.toLocaleString('en-IN')} observations`,
  }));
}

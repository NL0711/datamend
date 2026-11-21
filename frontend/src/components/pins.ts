// Pure helpers of the restored views (no React): map pins from the gauge catalogue and the stored station cycle, and the two
// formulas the original Overview and Live pages show (dew point, vapour pressure), here returning null when an input is missing.
import type { GlobeStation } from '../globe/StationGlobe3D';
import { globeState } from '../validation/lib';
import type { GaugeStation, StationCycle } from '../validation/types';

/** One pin per catalogue gauge, plus stations that exist only in an uploaded file and carry their own coordinates. */
export function buildPins(gauges: GaugeStation[], cycle: StationCycle[]): GlobeStation[] {
  const byId = new Map(cycle.map((c) => [c.station_id, c]));
  const out: GlobeStation[] = gauges.map((g) => {
    const c = byId.get(g.station_id);
    return {
      station_id: g.station_id, label: g.place, latitude: g.latitude, longitude: g.longitude, state: globeState(c),
      checked: c?.checked ?? 0, suspect: c?.suspect ?? 0, uncertain: c?.uncertain ?? 0, runs: c?.runs ?? 0, positionSource: 'catalogue',
    };
  });
  const known = new Set(gauges.map((g) => g.station_id));
  for (const c of cycle) {
    if (known.has(c.station_id) || c.latitude === null || c.longitude === null) continue;
    out.push({
      station_id: c.station_id, label: c.station_id, latitude: c.latitude, longitude: c.longitude, state: globeState(c),
      checked: c.checked, suspect: c.suspect, uncertain: c.uncertain, runs: c.runs, positionSource: c.position_source,
    });
  }
  return out;
}

/** Magnus-Tetens dew point in degrees C; null when the temperature or the humidity is missing, or the humidity is not above 0. */
export function dewPoint(temperature: number | null | undefined, humidity: number | null | undefined): number | null {
  if (temperature == null || humidity == null || humidity <= 0) return null;
  const a = 17.27;
  const b = 237.7;
  const alpha = (a * temperature) / (b + temperature) + Math.log(humidity / 100);
  return (b * alpha) / (a - alpha);
}

/** Actual vapour pressure in hPa from temperature (C) and relative humidity (%); null when either is missing. */
export function vaporPressure(temperature: number | null | undefined, humidity: number | null | undefined): number | null {
  if (temperature == null || humidity == null) return null;
  return (humidity / 100) * 6.112 * Math.exp((17.67 * temperature) / (temperature + 243.5));
}

/** `12.3` -> "12.3 unit"; null or undefined -> a dash. Never a made-up default. */
export function reading(value: number | null | undefined, digits: number, unit: string): string {
  return value == null || Number.isNaN(value) ? '—' : `${value.toFixed(digits)}${unit}`;
}

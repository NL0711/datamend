// Pure display helpers: coordinates with their hemisphere letter (never a signed number with the wrong letter), a UTC clock for chart axes,
// the one packet count the header shows, and the one-line summary of the stream-detection statistics.

/** "18.5000°N" or "97.2800°W"; the letter follows the sign. */
export function fmtLat(lat: number, digits = 2): string {
  return `${Math.abs(lat).toFixed(digits)}°${lat < 0 ? 'S' : 'N'}`;
}
export function fmtLon(lon: number, digits = 2): string {
  return `${Math.abs(lon).toFixed(digits)}°${lon < 0 ? 'W' : 'E'}`;
}
export function fmtLatLon(lat: number, lon: number, digits = 2): string {
  return `${fmtLat(lat, digits)}, ${fmtLon(lon, digits)}`;
}

/** "14:03:09" in UTC from a Date; empty for an invalid date. */
export function clockUtc(d: Date): string {
  return Number.isNaN(d.getTime()) ? '' : d.toISOString().slice(11, 19);
}

/** The packet count of the active source as the data-sources status reports it (the one source of truth); null when that status is not known. */
export function packetCount(active: { packet_count?: number } | null | undefined): number | null {
  return active && typeof active.packet_count === 'number' ? active.packet_count : null;
}

/** "12 detections (7 sensor faults, 5 meteorological extremes)", or the reason there are none to show. */
export function streamStatsLine(
  s: { total_anomalies: number; sensor_faults: number; meteorological_extremes: number } | null,
  error: string | null,
): string {
  if (error) return error;
  if (!s) return 'loading...';
  return `${s.total_anomalies} detection${s.total_anomalies === 1 ? '' : 's'} (${s.sensor_faults} sensor fault${s.sensor_faults === 1 ? '' : 's'}, ${s.meteorological_extremes} meteorological extreme${s.meteorological_extremes === 1 ? '' : 's'}).`;
}

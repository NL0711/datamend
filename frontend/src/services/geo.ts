// Pure display helpers: coordinates with their hemisphere letter (never a signed number with the wrong letter) and a UTC clock for chart axes.

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

/** "14:03:09" in UTC from a Date. */
export function clockUtc(d: Date): string {
  return Number.isNaN(d.getTime()) ? '' : d.toISOString().slice(11, 19);
}

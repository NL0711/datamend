// The words for the active live source, in one place (header chip, status strip, settings drawer). `null` means no source answered.
import type { DataSourceType } from '../types';

export function sourceLabel(source: DataSourceType | null, cityName?: string): string {
  switch (source) {
    case 'SIMULATED':
      return 'AUTOMATIC WEATHER STATIONS';
    case 'EXTERNAL_API':
      return cityName ? `OPEN-METEO: ${cityName.toUpperCase()}` : 'OPEN-METEO';
    case 'WEATHER_UNION':
      return 'WEATHER UNION';
    case 'PHYSICAL_AWS':
      return 'PHYSICAL AWS (ESP32)';
    default:
      return 'NO LIVE SOURCE CONNECTED';
  }
}

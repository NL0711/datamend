// Maps a severity word of the original contract onto a StatusBadge variant (pure; tested).
import type { StatusBadgeVariant } from '../design-system/components/StatusBadge';

export function severityVariant(severity?: string): StatusBadgeVariant {
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
}

/** Badge variant of a rainfall verdict (OK, UNCERTAIN, SUSPECT, NO_DATA) or the word "NOT CHECKED". */
export function verdictVariant(state: string): StatusBadgeVariant {
  switch (state) {
    case 'SUSPECT':
      return 'critical';
    case 'UNCERTAIN':
      return 'warning';
    case 'OK':
      return 'nominal';
    default:
      return 'neutral';
  }
}

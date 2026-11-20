// Which provider a pasted link belongs to, so the Import step needs one box and no provider choice.
import type { ImportProvider } from './types';

/** 'kaggle' for a kaggle.com link, owner/name or kernel:owner/name; 'aws' for s3:// or an amazonaws.com link; null when it is neither (yet). */
export function detectProvider(input: string): ImportProvider | null {
  const s = input.trim();
  if (!s) return null;
  if (/^s3:\/\//i.test(s)) return 'aws';
  if (/^https?:\/\//i.test(s)) {
    try {
      const host = new URL(s).hostname.toLowerCase();
      if (host === 'kaggle.com' || host.endsWith('.kaggle.com')) return 'kaggle';
      if (host === 'amazonaws.com' || host.endsWith('.amazonaws.com')) return 'aws';
    } catch { return null; }
    return null;
  }
  if (/^kernel:[A-Za-z0-9_.-]{1,60}\/[A-Za-z0-9_.-]{1,100}$/.test(s)) return 'kaggle';
  if (/^[A-Za-z0-9_.-]{1,60}\/[A-Za-z0-9_.-]{1,100}$/.test(s)) return 'kaggle';
  return null;
}

/** A short label for the detected source, shown beside the box. */
export const providerLabel = (p: ImportProvider | null): string => (p === 'kaggle' ? 'Kaggle' : p === 'aws' ? 'Amazon S3' : '');

/** A Kaggle API token looks like KGAT_ followed by letters and digits; the server accepts letters, digits, underscore and hyphen (8 to 200). */
export const looksLikeKaggleToken = (t: string): boolean => /^[A-Za-z0-9_-]{8,200}$/.test(t.trim());

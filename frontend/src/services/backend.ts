/// <reference types="vite/client" />

export const BACKEND_URL = (import.meta.env.VITE_BACKEND_URL || '').replace(/\/+$/, '');

export function websocketUrl(path: string): string {
  const url = new URL(path, BACKEND_URL || window.location.origin);
  url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
  return url.toString();
}

/**
 * DataMend — Resilient WebSocket client for the live stream (/ws/live of slices S3a and S3b).
 *
 * The server sends two kinds of frame: `status` (the stream's state, on connect and on every change) and `observation` (one reading).
 * Frames are parsed by services/stream.ts. The browser sends the HttpOnly `datamend_session` cookie that the sign-in set; a refused
 * handshake looks like an ordinary close to the browser, so a client that is not signed in just stays DISCONNECTED and retries with a
 * growing delay (2.5 s up to 60 s). Nothing is simulated in place of a missing stream.
 */

import { backoffDelay, parseFrame } from './stream';
import type { StreamObservation, StreamStatusData } from './stream';

export interface WebSocketCallbacks {
  onObservation?: (data: StreamObservation) => void;
  onStatus?: (status: StreamStatusData) => void;
  onOpen?: () => void;
  onClose?: (code: number) => void;
  onError?: (err: Event) => void;
}

export function liveSocketUrl(loc: { protocol: string; host: string } = window.location): string {
  return `${loc.protocol === 'https:' ? 'wss:' : 'ws:'}//${loc.host}/ws/live`;
}

export class TelemetryStreamClient {
  private ws: WebSocket | null = null;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private shouldReconnect = true;
  private attempts = 0;

  constructor(private callbacks: WebSocketCallbacks) {}

  public connect(): void {
    this.shouldReconnect = true;
    if (this.ws && (this.ws.readyState === WebSocket.OPEN || this.ws.readyState === WebSocket.CONNECTING)) return;
    try {
      const ws = new WebSocket(liveSocketUrl());
      this.ws = ws;
      ws.onopen = () => {
        this.attempts = 0;
        this.callbacks.onOpen?.();
      };
      ws.onmessage = (event) => {
        const frame = parseFrame(event.data);
        if (!frame) return;
        if (frame.kind === 'status') this.callbacks.onStatus?.(frame.status);
        else this.callbacks.onObservation?.(frame.observation);
      };
      ws.onerror = (err) => this.callbacks.onError?.(err);
      ws.onclose = (ev) => {
        if (this.ws === ws) this.ws = null;
        this.callbacks.onClose?.(ev.code);
        this.scheduleReconnect();
      };
    } catch (err) {
      console.error('WebSocket connection error:', err);
      this.scheduleReconnect();
    }
  }

  private scheduleReconnect(): void {
    if (!this.shouldReconnect) return;
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer);
    const delay = backoffDelay(this.attempts);
    this.attempts += 1;
    this.reconnectTimer = setTimeout(() => this.connect(), delay);
  }

  public disconnect(): void {
    this.shouldReconnect = false;
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer);
    this.reconnectTimer = null;
    const ws = this.ws;
    this.ws = null;
    if (ws) {
      ws.onclose = null;
      ws.close();
    }
  }

  public isConnected(): boolean {
    return this.ws !== null && this.ws.readyState === WebSocket.OPEN;
  }
}

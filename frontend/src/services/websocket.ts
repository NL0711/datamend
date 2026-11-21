/**
 * DataMend — Resilient WebSocket Client for Real-Time Telemetry & Anomaly Streams (the ORIGINAL contract, restored in slice S2b).
 *
 * NOT BUILT on the server yet: `/ws/live` is built in slice S3. Until then the connection fails and the client retries every few
 * seconds; the shell shows "No live stream connected" while `isConnected()` is false. Nothing is simulated in its place.
 */

import { InferenceResult } from '../types';

export interface WebSocketCallbacks {
  onTelemetry?: (data: InferenceResult) => void;
  onOpen?: () => void;
  onClose?: () => void;
  onError?: (err: Event) => void;
}

export class TelemetryStreamClient {
  private ws: WebSocket | null = null;
  private reconnectTimer: any = null;
  private shouldReconnect: boolean = true;
  private attempts: number = 0;
  private callbacks: WebSocketCallbacks;

  constructor(callbacks: WebSocketCallbacks) {
    this.callbacks = callbacks;
  }

  public connect(): void {
    this.shouldReconnect = true;
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws/live`;

    try {
      this.ws = new WebSocket(wsUrl);

      this.ws.onopen = () => {
        this.attempts = 0;
        if (this.callbacks.onOpen) this.callbacks.onOpen();
      };

      this.ws.onmessage = (event) => {
        try {
          const raw = JSON.parse(event.data);
          let telemetry: InferenceResult | null = null;

          if (raw && raw.type === 'observation' && raw.data) {
            telemetry = raw.data as InferenceResult;
            if (!telemetry.station_id && raw.station_id) {
              telemetry.station_id = raw.station_id;
            }
          } else if (raw && (raw.anomaly_score !== undefined || raw.station_id || raw.temperature !== undefined)) {
            telemetry = raw as InferenceResult;
          }

          if (telemetry && this.callbacks.onTelemetry) {
            this.callbacks.onTelemetry(telemetry);
          }
        } catch (err) {
          console.warn('Malformed WebSocket message received:', err);
        }
      };

      this.ws.onerror = (err) => {
        if (this.callbacks.onError) this.callbacks.onError(err);
      };

      this.ws.onclose = () => {
        if (this.callbacks.onClose) this.callbacks.onClose();
        if (this.shouldReconnect) {
          // 2.5 s, then doubling up to 60 s while the server has no /ws/live (slice S3), so an absent stream is not hammered
          const delay = Math.min(60000, 2500 * 2 ** this.attempts);
          this.attempts += 1;
          this.reconnectTimer = setTimeout(() => {
            this.connect();
          }, delay);
        }
      };
    } catch (err) {
      console.error('WebSocket connection error:', err);
      if (this.shouldReconnect) {
        this.reconnectTimer = setTimeout(() => {
          this.connect();
        }, 3000);
      }
    }
  }

  public disconnect(): void {
    this.shouldReconnect = false;
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer);
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
  }

  public isConnected(): boolean {
    return this.ws !== null && this.ws.readyState === WebSocket.OPEN;
  }
}

export function createTelemetryWebSocket(onMessage: (data: any) => void): WebSocket {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const wsUrl = `${protocol}//${window.location.host}/ws/live`;
  const ws = new WebSocket(wsUrl);

  ws.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      onMessage(data);
    } catch (err) {
      console.error('Failed to parse WebSocket message:', err);
    }
  };

  return ws;
}

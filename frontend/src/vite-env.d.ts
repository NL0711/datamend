/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** wss://<backend host>/ws/live when the dashboard is hosted apart from the backend (Vercel cannot proxy WebSockets). Empty = same host. */
  readonly VITE_WS_URL?: string;
}

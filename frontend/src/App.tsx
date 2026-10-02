import { useState, useEffect, useRef } from 'react';
import {
  AlertTriangle,
  ShieldCheck,
  Cpu,
  Database,
  Eye,
  Radio,
  Zap,
  Layers,
  Signal,
  Clock,
  CheckCircle2,
  Compass,
  Sliders,
  Globe,
} from 'lucide-react';
import { TelemetryStreamClient } from './services/websocket';
import { InferenceResult } from './types';
import { OverviewView } from './components/OverviewView';
import { LiveMonitoringView } from './components/LiveMonitoringView';
import { AlertCenterView } from './components/AlertCenterView';
import { SensorHealthView } from './components/SensorHealthView';
import { EventDetailView } from './components/EventDetailView';
import { DataExplorerView } from './components/DataExplorerView';
import { AnomalyInjectorUI } from './components/AnomalyInjectorUI';
import { ExplainabilityViewer } from './components/ExplainabilityViewer';
import { SettingsCenter } from './settings/SettingsCenter';
import {
  SystemConfigurationProvider,
  useSystemConfiguration,
} from './context/SystemConfigurationContext';

function AppContent() {
  const {
    activeSource,
    selectedCity,
    selectedStationId,
    selectStation,
    preferences,
    openSettings,
  } = useSystemConfiguration();

  const [activeTab, setActiveTab] = useState<
    'overview' | 'live' | 'alerts' | 'health' | 'events' | 'explorer' | 'injector' | 'explainability'
  >(preferences.defaultView || 'overview');

  const [selectedIncidentId, setSelectedIncidentId] = useState<number | null>(null);
  const [latestTelemetry, setLatestTelemetry] = useState<InferenceResult | null>(null);
  const [historyBuffer, setHistoryBuffer] = useState<InferenceResult[]>([]);
  const [isWsConnected, setIsWsConnected] = useState<boolean>(false);
  const [isStreaming, setIsStreaming] = useState<boolean>(true);
  const [utcTime, setUtcTime] = useState<string>('');
  const isStreamingRef = useRef<boolean>(true);

  isStreamingRef.current = isStreaming;

  // Live UTC Clock updater
  useEffect(() => {
    const updateTime = () => {
      const now = new Date();
      setUtcTime(now.toISOString().substring(11, 19) + ' UTC');
    };
    updateTime();
    const interval = setInterval(updateTime, 1000);
    return () => clearInterval(interval);
  }, []);

  // Keyboard navigation shortcuts (1-8 and 's' for Settings)
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (
        e.target instanceof HTMLInputElement ||
        e.target instanceof HTMLSelectElement ||
        e.target instanceof HTMLTextAreaElement
      ) {
        return;
      }
      const tabs: (
        | 'overview'
        | 'live'
        | 'alerts'
        | 'health'
        | 'events'
        | 'explorer'
        | 'injector'
        | 'explainability'
      )[] = [
        'overview',
        'live',
        'alerts',
        'health',
        'events',
        'explorer',
        'injector',
        'explainability',
      ];
      const keyNum = parseInt(e.key, 10);
      if (keyNum >= 1 && keyNum <= 8) {
        setActiveTab(tabs[keyNum - 1]);
      }
      if (e.key === 's' || e.key === 'S' || (e.ctrlKey && e.key === ',')) {
        openSettings();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [openSettings]);

  // WebSocket Live Connection
  useEffect(() => {
    const wsClient = new TelemetryStreamClient({
      onOpen: () => {
        setIsWsConnected(true);
      },
      onClose: () => {
        setIsWsConnected(false);
      },
      onTelemetry: (data: InferenceResult) => {
        if (!isStreamingRef.current) return;
        setLatestTelemetry(data);
        setHistoryBuffer((prev) => {
          const next = [...prev, data];
          return next.length > 150 ? next.slice(-150) : next;
        });
      },
    });

    wsClient.connect();

    return () => {
      wsClient.disconnect();
    };
  }, []);

  const navItems = [
    { id: 'overview', label: 'Command Center', icon: Compass, short: '1' },
    { id: 'live', label: 'Live Telemetry', icon: Eye, short: '2' },
    { id: 'alerts', label: 'Alert Center', icon: AlertTriangle, short: '3' },
    { id: 'health', label: 'Sensor Health', icon: ShieldCheck, short: '4' },
    { id: 'events', label: 'Event Forensics', icon: Cpu, short: '5' },
    { id: 'explorer', label: 'Data Explorer', icon: Database, short: '6' },
    { id: 'injector', label: 'Anomaly Lab', icon: Zap, short: '7' },
    { id: 'explainability', label: 'XAI Reasoner', icon: Layers, short: '8' },
  ];

  const getSourceBadge = () => {
    switch (activeSource) {
      case 'PHYSICAL_AWS':
        return (
          <button
            onClick={openSettings}
            className="flex items-center gap-1.5 px-2.5 py-1 bg-[#10192A] hover:bg-[#1B2A44] border border-emerald-500/40 rounded-lg transition-all text-xs font-mono"
            title="Click to configure Telemetry Source"
          >
            <Signal className="w-3.5 h-3.5 text-emerald-400" />
            <span className="text-emerald-300 font-bold">PHYSICAL ESP32</span>
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-ping ml-0.5" />
          </button>
        );
      case 'EXTERNAL_API':
        return (
          <button
            onClick={openSettings}
            className="flex items-center gap-1.5 px-2.5 py-1 bg-[#10192A] hover:bg-[#1B2A44] border border-sky-500/40 rounded-lg transition-all text-xs font-mono"
            title="Click to configure Climate Site / Source"
          >
            <Globe className="w-3.5 h-3.5 text-sky-400" />
            <span className="text-sky-300 font-bold">
              OPEN-METEO: {selectedCity ? selectedCity.name.toUpperCase() : 'LIVE'}
            </span>
          </button>
        );
      case 'SIMULATED':
      default:
        return (
          <button
            onClick={openSettings}
            className="flex items-center gap-1.5 px-2.5 py-1 bg-[#10192A] hover:bg-[#1B2A44] border border-amber-500/40 rounded-lg transition-all text-xs font-mono"
            title="Click to configure Telemetry Source"
          >
            <Radio className="w-3.5 h-3.5 text-amber-400" />
            <span className="text-amber-300 font-bold">SIMULATED AWS</span>
          </button>
        );
    }
  };

  const densityPadding =
    preferences.displayDensity === 'compact'
      ? 'p-3 sm:p-4 space-y-4'
      : preferences.displayDensity === 'operator'
      ? 'p-2 sm:p-3 space-y-3'
      : 'p-4 sm:p-6 space-y-6';

  return (
    <div className="min-h-screen bg-[#0F1726] text-slate-100 flex flex-col font-sans selection:bg-sky-500/30 selection:text-sky-200 antialiased">
      {/* Top Mission Telemetry Bar */}
      <header className="h-14 border-b border-[#263B5E] bg-[#152033]/95 backdrop-blur-md px-4 sm:px-6 flex items-center justify-between sticky top-0 z-40 shadow-md select-none">
        {/* Brand & Project Identity */}
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-[#1B2A44] border border-sky-500/40 flex items-center justify-center text-sky-400 shadow-inner shrink-0">
            <svg viewBox="0 0 24 24" className="w-4.5 h-4.5 fill-none stroke-current stroke-2">
              <circle cx="12" cy="12" r="9" stroke="currentColor" strokeOpacity="0.4" strokeDasharray="2 2" />
              <path d="M4 12c3-4 6-4 8 0s5 4 8 0" />
              <circle cx="12" cy="12" r="2" fill="currentColor" />
            </svg>
          </div>

          <div>
            <div className="flex items-center gap-2">
              <span className="text-sm font-black tracking-wider text-white font-mono">
                SKYGUARD<span className="text-sky-400 ml-1">AI</span>
              </span>
              <span className="text-[10px] uppercase font-mono px-2 py-0.2 bg-[#1B2A44] text-slate-300 rounded border border-white/[0.08] font-bold">
                OPERATIONS v0.3.0
              </span>
            </div>
            <p className="text-[11px] text-slate-400 hidden sm:block">
              WMO-No. 8 Automatic Weather Station Quality Control System
            </p>
          </div>
        </div>

        {/* Global Operational HUD Indicators */}
        <div className="flex items-center gap-2.5 sm:gap-4 text-xs font-mono">
          {/* Active Data Source Pill */}
          <div className="hidden sm:block">
            {getSourceBadge()}
          </div>

          {/* Real-time UTC Mission Clock */}
          <div className="flex items-center gap-1.5 px-2.5 py-1 rounded bg-[#0C1320] border border-[#263B5E] text-[11px] text-slate-300 font-semibold">
            <Clock className="w-3.5 h-3.5 text-sky-400" />
            <span>{utcTime || '00:00:00 UTC'}</span>
          </div>

          {/* WebSocket Ingestion Status */}
          <div
            className={`flex items-center gap-2 px-2.5 py-1 rounded border text-[11px] font-bold transition-all ${
              isWsConnected
                ? 'bg-emerald-500/15 border-emerald-500/40 text-emerald-400'
                : 'bg-amber-500/15 border-amber-500/40 text-amber-400'
            }`}
          >
            <span
              className={`w-1.5 h-1.5 rounded-full ${
                isWsConnected ? 'bg-emerald-400 animate-ping' : 'bg-amber-400'
              }`}
            />
            <span className="hidden md:inline">{isWsConnected ? 'STREAM ACTIVE' : 'CONNECTING...'}</span>
          </div>

          {/* Global System Settings Trigger Button */}
          <button
            onClick={openSettings}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-[#1B2A44] hover:bg-[#233656] border border-sky-500/40 hover:border-sky-400 text-white rounded-lg font-bold transition-all shadow-sm group"
            title="System Configuration (Press S or Ctrl+,)"
          >
            <Sliders className="w-3.5 h-3.5 text-sky-400 group-hover:rotate-90 transition-transform" />
            <span className="hidden sm:inline">Settings</span>
          </button>
        </div>
      </header>

      {/* Main Layout Body: Left Command Rail + Operational Deck */}
      <div className="flex-1 flex overflow-hidden">
        {/* Left Command Rail */}
        <aside className="w-16 sm:w-56 bg-[#152033] border-r border-[#263B5E] flex flex-col justify-between shrink-0 select-none">
          <nav className="p-2 sm:p-3 space-y-1">
            <div className="px-3 py-1.5 text-[10px] font-mono font-bold text-slate-400 uppercase tracking-wider hidden sm:block">
              Operations Rail
            </div>

            {navItems.map((tab) => {
              const Icon = tab.icon;
              const isActive = activeTab === tab.id;
              return (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id as any)}
                  title={`${tab.label} (Press ${tab.short})`}
                  className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-xs font-semibold transition-all group ${
                    isActive
                      ? 'bg-sky-500 text-slate-950 shadow-md font-bold'
                      : 'text-slate-300 hover:text-white hover:bg-[#1B2A44]'
                  }`}
                >
                  <Icon className={`w-4 h-4 shrink-0 ${isActive ? 'text-slate-950' : 'text-sky-400'}`} />
                  <span className="hidden sm:inline truncate">{tab.label}</span>
                  <span
                    className={`ml-auto text-[10px] font-mono px-1.5 py-0.2 rounded hidden sm:inline ${
                      isActive ? 'bg-slate-950/20 text-slate-950' : 'text-slate-500 group-hover:text-slate-400'
                    }`}
                  >
                    {tab.short}
                  </span>
                </button>
              );
            })}
          </nav>

          {/* Rail Footer Information */}
          <div className="p-3 border-t border-[#263B5E] hidden sm:block text-[11px] font-mono text-slate-400 space-y-1 bg-[#10192A]">
            <div className="flex items-center justify-between text-slate-300">
              <span>Pipeline Latency:</span>
              <span className="font-bold text-emerald-400">&lt; 2.0 ms</span>
            </div>
            <div className="flex items-center justify-between text-slate-400 text-[10px]">
              <span>Inference Engine:</span>
              <span className="text-sky-300">PyTorch GRU</span>
            </div>
          </div>
        </aside>

        {/* Operational Workspace Deck */}
        <main className={`flex-1 overflow-y-auto ${densityPadding}`}>
          {/* Active View */}
          {activeTab === 'overview' && (
            <OverviewView
              selectedStationId={selectedStationId}
              onSelectStation={selectStation}
              latestTelemetry={latestTelemetry}
              historyBuffer={historyBuffer}
              onNavigate={(tab) => setActiveTab(tab as any)}
            />
          )}
          {activeTab === 'live' && (
            <LiveMonitoringView
              selectedStationId={selectedStationId}
              onSelectStation={selectStation}
              latestTelemetry={latestTelemetry}
              historyBuffer={historyBuffer}
              isStreaming={isStreaming}
              onToggleStreaming={() => setIsStreaming((s) => !s)}
            />
          )}
          {activeTab === 'alerts' && (
            <AlertCenterView
              onNavigateToEvent={(eventId, stationId) => {
                setSelectedIncidentId(eventId);
                selectStation(stationId);
                setActiveTab('events');
              }}
              onLocateOnGlobe={(stationId) => {
                selectStation(stationId);
                setActiveTab('overview');
              }}
            />
          )}
          {activeTab === 'health' && <SensorHealthView />}
          {activeTab === 'events' && (
            <EventDetailView
              initialEventId={selectedIncidentId}
              initialStationId={selectedStationId}
              onSelectStation={selectStation}
              onNavigateToLive={(stationId) => {
                selectStation(stationId);
                setActiveTab('live');
              }}
            />
          )}
          {activeTab === 'explorer' && <DataExplorerView />}
          {activeTab === 'injector' && (
            <AnomalyInjectorUI onNavigateToLive={() => setActiveTab('live')} />
          )}
          {activeTab === 'explainability' && <ExplainabilityViewer />}
        </main>
      </div>

      {/* Global Settings Center Drawer */}
      <SettingsCenter />

      {/* Mission Control Status Bar Footer */}
      <footer className="h-9 border-t border-[#263B5E] bg-[#10192A] px-4 sm:px-6 text-xs text-slate-400 flex items-center justify-between font-mono z-40 select-none">
        <div className="flex items-center gap-3">
          <span className="flex items-center gap-1.5 text-slate-300 text-[11px]">
            <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" /> WMO-No. 8 & CIMO Compliant QC Engine
          </span>
          <span className="text-slate-600 hidden sm:inline">•</span>
          <span className="text-slate-400 text-[10px] hidden md:inline">
            5-Tier Fusion (Hard QC • Isolation Forest • GRU Autoencoder • Clausius-Clapeyron • TreeSHAP)
          </span>
        </div>

        <div className="text-[11px] text-slate-300">
          REST API <span className="text-sky-400 font-bold">:8899</span> | WS <span className="text-sky-400 font-bold">/ws/live</span>
        </div>
      </footer>
    </div>
  );
}

export default function App() {
  return (
    <SystemConfigurationProvider>
      <AppContent />
    </SystemConfigurationProvider>
  );
}

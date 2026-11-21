// The dashboard shell: the layout of the ORIGINAL app (commit ab3b0b3), restored in slice S2b and wired to the current platform.
// Header (h-14, sticky): brand, the GLOBAL station picker over the 580 Weather Union gauges, the live-source chip, the UTC clock, Import and
// Settings. Left rail: Overview, Live, Alerts, Events, Explorer, Review, Injector, Agent with the keys 1 to 8. Pages are hash routes under
// `#/app/<page>` (validation/shell.ts). ONE selected station lives in StationContext and every page reads it.
// Wired to the backend (slices S3a, S3b): the /ws/live stream (status and observation frames), stored T/P/RH observations, data sources, the
// simulator, the fault injector and the stream settings. NOT BUILT: the agent (slice S6). Nothing is mocked here.
import { useCallback, useEffect, useRef, useState } from 'react';
import {
  AlertTriangle,
  Bot,
  CheckCircle2,
  Clock,
  Compass,
  Database,
  Eye,
  FileSearch,
  Globe,
  ShieldCheck,
  Sliders,
  Upload,
  Zap,
} from 'lucide-react';
import type { ComponentType } from 'react';
import { TelemetryStreamClient } from './services/websocket';
import { describeStream, pushRolling } from './services/stream';
import type { StreamObservation } from './services/stream';
import { StreamSettings } from './settings/StreamSettings';
import { OverviewView } from './components/OverviewView';
import { LiveMonitoringView } from './components/LiveMonitoringView';
import { AlertCenterView } from './components/AlertCenterView';
import { EventDetailView } from './components/EventDetailView';
import { DataExplorerView } from './components/DataExplorerView';
import { AnomalyInjectorUI } from './components/AnomalyInjectorUI';
import { AgentView } from './components/AgentView';
import { sourceLabel } from './components/sourceLabel';
import { SettingsCenter } from './settings/SettingsCenter';
import { SystemConfigurationProvider, useSystemConfiguration } from './context/SystemConfigurationContext';
import { AdminChip } from './validation/Login';
import { OverviewView as PlatformCounts } from './validation/OverviewView';
import type { Tab } from './validation/OverviewView';
import { LiveFeedView } from './validation/LiveFeedView';
import { PageBoundary } from './validation/PageBoundary';
import { ReviewView } from './validation/ReviewView';
import { RunsView } from './validation/RunsView';
import { SettingsView } from './validation/SettingsView';
import { StationProvider, useStation } from './validation/StationContext';
import { StationPicker } from './validation/StationPicker';
import { hashForPage, pageForKey, pageForTab, pageFromHash, pageFromId } from './validation/shell';
import type { EventFocus, PageId } from './validation/shell';
import { PAGE_INFO, RAIL_GROUPS, railKey, railTitle } from './validation/guide';
import { PageIntro } from './components/PageIntro';
import { StartGuide } from './components/StartGuide';
import { Legend } from './components/Legend';

const ICON: Record<string, ComponentType<{ className?: string }>> = {
  overview: Compass, live: Eye, alerts: AlertTriangle, events: FileSearch, explorer: Database, review: ShieldCheck, injector: Zap, agent: Bot,
  import: Upload, settings: Sliders,
};

function AppContent() {
  const { activeSource, selectedCity, preferences, openSettings, streamConnected, setStreamConnected, streamStatus, setStreamStatus, sourcesAvailable } = useSystemConfiguration();
  const streamView = describeStream(streamConnected, streamStatus);
  const { stationId, select, refresh, stations } = useStation();

  const [page, setPage] = useState<PageId>(() => {
    const hash = window.location.hash;
    return /^#\/app\/?$/.test(hash) ? preferences.defaultView : pageFromHash(hash);       // a plain "#/app" opens the preferred first page
  });
  const [focus, setFocus] = useState<(EventFocus & { station: string | null }) | null>(null);
  const [latestByStation, setLatestByStation] = useState<Record<string, StreamObservation>>({});
  const [historyBuffer, setHistoryBuffer] = useState<StreamObservation[]>([]);
  const [isStreaming, setIsStreaming] = useState<boolean>(true);
  const [utcTime, setUtcTime] = useState<string>('');
  const [guideNonce, setGuideNonce] = useState(0);
  const isStreamingRef = useRef<boolean>(true);
  isStreamingRef.current = isStreaming;

  const navigate = useCallback((p: PageId) => { window.location.hash = hashForPage(p); }, []);

  useEffect(() => {
    const on = () => { if (window.location.hash.startsWith('#/app')) setPage(pageFromHash(window.location.hash)); };
    window.addEventListener('hashchange', on);
    return () => window.removeEventListener('hashchange', on);
  }, []);

  // Live UTC clock
  useEffect(() => {
    const updateTime = () => setUtcTime(new Date().toISOString().substring(11, 19) + ' UTC');
    updateTime();
    const interval = setInterval(updateTime, 1000);
    return () => clearInterval(interval);
  }, []);

  // Keys 1 to 8 open the rail pages, "s" opens Settings; nothing while typing
  useEffect(() => {
    const on = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement | null;
      if (e.ctrlKey || e.metaKey || e.altKey || (t && (['INPUT', 'SELECT', 'TEXTAREA'].includes(t.tagName) || t.isContentEditable))) return;
      const p = pageForKey(e.key);
      if (p) navigate(p);
      else if (e.key === 's' || e.key === 'S') navigate('settings');
    };
    window.addEventListener('keydown', on);
    return () => window.removeEventListener('keydown', on);
  }, [navigate]);

  // WebSocket live connection to /ws/live: status frames set the stream state, observation frames feed the pages
  useEffect(() => {
    const wsClient = new TelemetryStreamClient({
      onOpen: () => setStreamConnected(true),
      onClose: () => { setStreamConnected(false); setStreamStatus(null); },
      onStatus: (s) => setStreamStatus(s),
      onObservation: (data) => {
        if (!isStreamingRef.current) return;
        setLatestByStation((prev) => ({ ...prev, [data.station_id]: data }));
        setHistoryBuffer((prev) => pushRolling(prev, data, 400));
      },
    });
    wsClient.connect();
    return () => { wsClient.disconnect(); };
  }, [setStreamConnected, setStreamStatus]);

  const openRun = (id: number) => { setFocus({ runId: id, rowId: null, station: stationId }); navigate('events'); };
  const go = (t: Tab) => navigate(pageForTab(t));

  const sourceChip = (
    <button
      onClick={openSettings}
      className={`flex items-center gap-1.5 px-3 py-1 bg-[#F4F6FA] hover:bg-[#EDF1F7] border rounded-lg transition-all text-xs font-mono shadow-sm ${activeSource ? 'border-sky-500/50' : 'border-[#D3DCE7]'}`}
      title={`Live data source and display preferences. ${streamView.detail}`}
    >
      <Globe className={`w-3.5 h-3.5 ${activeSource ? 'text-sky-600' : 'text-slate-400'}`} />
      <span className={`font-bold ${activeSource ? 'text-sky-800' : 'text-slate-600'}`}>{sourceLabel(activeSource, selectedCity?.name)}</span>
      <span className={`w-1.5 h-1.5 rounded-full ml-0.5 ${streamView.tone === 'nominal' ? 'bg-emerald-500 animate-pulse' : streamView.tone === 'warning' ? 'bg-amber-500' : streamView.tone === 'critical' ? 'bg-rose-500' : 'bg-slate-300'}`} />
      <span className={`text-[10px] font-bold ${streamView.tone === 'nominal' ? 'text-emerald-700' : streamView.tone === 'warning' ? 'text-amber-700' : streamView.tone === 'critical' ? 'text-rose-700' : 'text-slate-500'}`}>{streamView.label}</span>
    </button>
  );

  const headerButton = (target: PageId, Icon: ComponentType<{ className?: string }>, label: string, title: string) => (
    <button
      onClick={() => navigate(target)}
      aria-current={page === target ? 'page' : undefined}
      title={title}
      className={`flex items-center gap-1.5 px-3 py-1.5 border rounded-lg font-bold transition-all shadow-sm group text-slate-900 ${
        page === target ? 'bg-sky-500/15 border-sky-500' : 'bg-[#EDF1F7] hover:bg-[#E2E8F2] border-sky-500/40 hover:border-sky-400'
      }`}
    >
      <Icon className="w-3.5 h-3.5 text-sky-600 group-hover:rotate-90 transition-transform" />
      <span className="hidden sm:inline">{label}</span>
    </button>
  );

  const densityPadding =
    preferences.displayDensity === 'compact'
      ? 'p-3 sm:p-4 space-y-4'
      : preferences.displayDensity === 'operator'
      ? 'p-2 sm:p-3 space-y-3'
      : 'p-4 sm:p-6 space-y-6';

  return (
    <div className="h-screen bg-[#F4F6FA] text-slate-900 flex flex-col font-sans selection:bg-sky-500/30 selection:text-sky-900 antialiased">
      {/* Top bar */}
      <header className="h-14 shrink-0 border-b border-[#D3DCE7] bg-[#FFFFFF]/95 backdrop-blur-md px-4 sm:px-6 flex items-center justify-between sticky top-0 z-40 shadow-md select-none gap-3">
        <div className="flex items-center gap-3 min-w-0">
          <button onClick={() => navigate('overview')} className="flex items-center gap-3 shrink-0 text-left" aria-label="DataMend overview">
            <div className="w-8 h-8 rounded-lg bg-[#EDF1F7] border border-sky-500/40 flex items-center justify-center text-sky-600 shadow-inner shrink-0">
              <svg viewBox="0 0 24 24" className="w-4.5 h-4.5 fill-none stroke-current stroke-2">
                <circle cx="12" cy="12" r="9" stroke="currentColor" strokeOpacity="0.4" strokeDasharray="2 2" />
                <path d="M4 12c3-4 6-4 8 0s5 4 8 0" />
                <circle cx="12" cy="12" r="2" fill="currentColor" />
              </svg>
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="text-sm font-black tracking-wider text-slate-900 font-mono">DATAMEND</span>
                <span className="text-[10px] uppercase font-mono px-2 py-0.5 bg-[#EDF1F7] text-slate-600 rounded border border-slate-200 font-bold">PROTOTYPE</span>
              </div>
              <p className="text-[11px] text-slate-500 hidden lg:block">Weather station data validation platform</p>
            </div>
          </button>

          <StationPicker />
        </div>

        <div className="flex items-center gap-2.5 sm:gap-4 text-xs font-mono shrink-0">
          <div className="hidden md:block">{sourceChip}</div>

          <div className="hidden sm:flex items-center gap-1.5 px-2.5 py-1 rounded bg-[#E8EDF4] border border-[#D3DCE7] text-[11px] text-slate-600 font-semibold">
            <Clock className="w-3.5 h-3.5 text-sky-600" />
            <span>{utcTime || '00:00:00 UTC'}</span>
          </div>

          <Legend onShowGuide={() => { setGuideNonce((n) => n + 1); navigate('overview'); }} />
          {headerButton('import', Upload, 'Import', 'Bring in your own data: upload a file or paste a link')}
          {headerButton('settings', Sliders, 'Settings', 'Settings (press S)')}
        </div>
      </header>

      {/* Body: left rail and the page */}
      <div className="flex-1 min-h-0 flex overflow-hidden">
        <aside className="w-16 sm:w-56 bg-[#FFFFFF] border-r border-[#D3DCE7] flex flex-col justify-between shrink-0 select-none overflow-y-auto">
          <nav className="p-2 sm:p-3 space-y-1" aria-label="main">
            {RAIL_GROUPS.map((group) => (
              <div key={group.label} className="space-y-1">
                <div className="px-3 pt-2 pb-1 text-[10px] font-mono font-bold text-slate-500 uppercase tracking-wider hidden sm:block">{group.label}</div>
                {group.pages.map((id) => {
                  const Icon = ICON[id];
                  const isActive = page === id;
                  const key = railKey(id);
                  return (
                    <button
                      key={id}
                      onClick={() => navigate(id)}
                      aria-current={isActive ? 'page' : undefined}
                      title={railTitle(id)}
                      className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-xs font-semibold transition-all group ${
                        isActive ? 'bg-sky-500 text-slate-950 shadow-md font-bold' : 'text-slate-600 hover:text-slate-900 hover:bg-[#EDF1F7]'
                      }`}
                    >
                      <Icon className={`w-4 h-4 shrink-0 ${isActive ? 'text-slate-950' : 'text-sky-600'}`} />
                      <span className="hidden sm:inline truncate">{PAGE_INFO[id].title}</span>
                      {(key || id === 'settings') && (
                        <span className={`ml-auto text-[10px] font-mono px-1.5 py-0.5 rounded hidden sm:inline ${isActive ? 'bg-slate-950/20 text-slate-950' : 'text-slate-500 group-hover:text-slate-500'}`}>
                          {key ?? 'S'}
                        </span>
                      )}
                    </button>
                  );
                })}
              </div>
            ))}
          </nav>

          <div>
            <AdminChip onSignIn={() => { window.location.hash = '#/login'; }} />
            <div className="p-3 border-t border-[#D3DCE7] hidden sm:block text-[11px] font-mono text-slate-500 space-y-1 bg-[#F4F6FA]">
              <div className="flex items-center justify-between text-slate-600">
                <span>Stations:</span>
                <span className="font-bold text-slate-800">{stations.length || '…'}</span>
              </div>
              <div className="flex items-center justify-between text-slate-500 text-[10px]">
                <span>Live stream:</span>
                <span className={streamView.tone === 'nominal' ? 'text-emerald-700 font-bold' : streamView.tone === 'warning' ? 'text-amber-700 font-bold' : 'text-slate-600'}>{streamView.key === 'stale' ? 'stale' : streamView.label.toLowerCase()}</span>
              </div>
              <div className="flex items-center justify-between text-slate-500 text-[10px]">
                <span>Source list:</span>
                <span className="text-slate-600">{sourcesAvailable ? 'answering' : 'not answering'}</span>
              </div>
            </div>
          </div>
        </aside>

        <main className={`flex-1 min-w-0 overflow-y-auto ${densityPadding}`}>
          <PageBoundary resetKey={page}>
            <PageIntro page={page} />
            {page === 'overview' && (
              <>
                <StartGuide key={guideNonce} onNavigate={navigate} />
                <OverviewView
                  latestByStation={latestByStation}
                  onNavigate={(t) => navigate(pageFromId(t))}
                />
                <div className="space-y-2">
                  <h3 className="text-xs font-bold uppercase tracking-wider text-slate-900 font-mono">Counts from uploaded-file runs</h3>
                  <PlatformCounts onOpenRun={openRun} go={go} />
                </div>
              </>
            )}
            {page === 'live' && (
              <>
                <LiveMonitoringView
                  latestTelemetry={stationId ? latestByStation[stationId] || null : null}
                  historyBuffer={historyBuffer}
                  isStreaming={isStreaming}
                  onToggleStreaming={() => setIsStreaming((s) => !s)}
                />
                <div className="space-y-2">
                  <h3 className="text-xs font-bold uppercase tracking-wider text-slate-900 font-mono">Rain-gauge feed (Weather Union, rain only, polled by the server)</h3>
                  <p className="text-xs text-slate-600">A separate poller from the input stream above. It is set under Settings, "Rain-gauge feed".</p>
                  <LiveFeedView onOpenRun={openRun} stationId={stationId} onSelectStation={select} />
                </div>
              </>
            )}
            {page === 'alerts' && (
              <AlertCenterView
                onNavigateToEvent={(r) => { setFocus({ runId: r.run_id, rowId: r.id, station: r.station_id }); select(r.station_id); navigate('events'); }}
                onLocateOnGlobe={(s) => { select(s); navigate('overview'); }}
                onImport={() => navigate('import')}
              />
            )}
            {page === 'events' && <EventDetailView focus={focus} onImport={() => navigate('import')} onNavigateToLive={() => navigate('live')} />}
            {page === 'explorer' && <DataExplorerView onImport={() => navigate('import')} />}
            {page === 'review' && <ReviewView key={stationId ?? 'all'} station={stationId ?? ''} onClearStation={() => undefined} />}
            {page === 'injector' && <AnomalyInjectorUI onNavigateToLive={() => navigate('live')} />}
            {page === 'agent' && <AgentView />}
            {page === 'import' && <RunsView onOpen={(id) => { refresh(); setFocus({ runId: id, rowId: null, station: null }); navigate('events'); }} />}
            {page === 'settings' && (
              <div className="space-y-4">
                <StreamSettings />
                <div className="bg-[#FFFFFF] border border-[#D3DCE7] rounded-xl p-4 shadow-lg flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <h3 className="text-xs font-bold uppercase tracking-wider text-slate-900 font-mono">Display preferences</h3>
                    <p className="text-xs text-slate-600">Page density, motion and the first page. The same window also has a source switch and the Open-Meteo site; the "Input stream" form above is the full version.</p>
                  </div>
                  <button onClick={openSettings} className="px-3 py-2 bg-sky-500 hover:bg-sky-400 text-slate-950 font-mono font-bold text-xs rounded-lg shadow">Open display preferences</button>
                </div>
                <SettingsView />
              </div>
            )}
          </PageBoundary>
        </main>
      </div>

      <SettingsCenter />

      {/* Status bar */}
      <footer className="h-9 shrink-0 border-t border-[#D3DCE7] bg-[#F4F6FA] px-4 sm:px-6 text-xs text-slate-500 flex items-center justify-between font-mono z-40 select-none">
        <div className="flex items-center gap-3">
          <span className="flex items-center gap-1.5 text-slate-600 text-[11px]">
            <CheckCircle2 className="w-3.5 h-3.5 text-sky-600" /> Prototype: rainfall checks are rule-based; rule scores are uncalibrated
          </span>
        </div>
        <div className="text-[11px] text-slate-600 hidden sm:block">
          REST <span className="text-sky-600 font-bold">/api</span> | WS <span className="text-sky-600 font-bold">/ws/live</span>{' '}
          <span className={streamView.tone === 'nominal' ? 'text-emerald-700 font-bold' : 'text-slate-500'}>{streamView.label.toLowerCase()}</span>
        </div>
      </footer>
    </div>
  );
}

export default function App() {
  return (
    <SystemConfigurationProvider>
      <StationProvider>
        <AppContent />
      </StationProvider>
    </SystemConfigurationProvider>
  );
}

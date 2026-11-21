// Overview (the command centre) of the ORIGINAL dashboard, restored in slice S2b: context strip, the globe with a station dossier beside it,
// the station registry and the flagged-incident stream. Data: the globe, registry and dossier read the 580-gauge catalogue and the stored
// station cycle through the shell's StationContext; the temperature, pressure and humidity tiles show the latest reading of the selected
// station from the WebSocket or, failing that, the latest stored observation (GET /api/observations); dashes only when there is none.
// Pins are coloured by the real verdict of the station's checked rows or latest stream reading, grey otherwise. Changed against the
// original: no fallback station (KTLX), no default health score of 98, no "SUPPORTED" spatial-consensus claim, no "Live" label without a stream.
import { useEffect, useMemo, useState } from 'react';
import { fetchObservations, isNotBuilt } from '../services/api';
import { describeStream, fmtUtc, pinState } from '../services/stream';
import type { StreamObservation } from '../services/stream';
import { Observation } from '../types';
import { StatusBadge } from '../design-system/components/StatusBadge';
import { NetworkMap } from '../design-system/components/NetworkMap';
import { StationGlobe3D } from '../design-system/components/StationGlobe3D';
import { TableSkeleton } from '../design-system/components/SkeletonLoader';
import { ContextualStatusStrip } from './ContextualStatusStrip';
import { AnomalyFeed } from './AnomalyFeed';
import { buildPins, dewPoint, reading } from './pins';
import { verdictVariant } from './severity';
import { useSystemConfiguration } from '../context/SystemConfigurationContext';
import { useStation } from '../validation/StationContext';
import { openStationPicker } from './PageIntro';
import { getQueue } from '../validation/api';
import { globeState, queueQuery } from '../validation/lib';
import type { QueueRow } from '../validation/types';

interface OverviewViewProps {
  latestByStation: Record<string, StreamObservation>;
  onNavigate: (tab: string) => void;
}

export function OverviewView({ latestByStation, onNavigate }: OverviewViewProps) {
  const { openSettings, streamConnected, streamStatus } = useSystemConfiguration();
  const stream = describeStream(streamConnected, streamStatus);
  const { stationId, select, stations, gauges, streamStations, cycle, selectedCycle, entry, loading } = useStation();
  const [mapViewMode, setMapViewMode] = useState<'3D' | '2D'>('3D');
  const [queue, setQueue] = useState<QueueRow[] | null>(null);
  const [stationLatestObs, setStationLatestObs] = useState<Observation | null>(null);
  const [obsNotBuilt, setObsNotBuilt] = useState(false);

  const streamStates = useMemo(() => Object.fromEntries(Object.entries(latestByStation).map(([id, o]) => [id, pinState(o)])), [latestByStation]);
  const pins = useMemo(() => buildPins(gauges, cycle, streamStations, streamStates), [gauges, cycle, streamStations, streamStates]);
  // the flat map fits its view to the pins it draws, so the far-away stream stations are left to the globe
  const flatPins = useMemo(() => pins.filter((p) => p.positionSource !== 'stream').map((p) => ({ station_id: p.station_id, name: p.label, latitude: p.latitude, longitude: p.longitude, state: p.state })), [pins]);
  const gauge = gauges.find((g) => g.station_id === stationId);
  const streamStation = streamStations.find((s) => s.station_id === stationId);

  // flagged rainfall rows waiting for a reviewer (the real incident stream of today)
  useEffect(() => {
    let current = true;
    getQueue(queueQuery({ page: 1, status: 'unreviewed' })).then((d) => { if (current) setQueue(d.rows.slice(0, 4)); }).catch(() => { if (current) setQueue([]); });
    return () => { current = false; };
  }, []);

  // the latest stored T/P/RH observation of the selected station (endpoint built in S3)
  useEffect(() => {
    setStationLatestObs(null);
    if (!stationId) return;
    let current = true;
    fetchObservations({ station_id: stationId, limit: 1 })
      .then((res) => { if (!current) return; setObsNotBuilt(false); setStationLatestObs(res.items && res.items.length > 0 ? res.items[0] : null); })
      .catch((e) => { if (current) setObsNotBuilt(isNotBuilt(e)); });
    return () => { current = false; };
  }, [stationId]);

  const activeObs: StreamObservation | null = stationId ? latestByStation[stationId] ?? null : null;

  // the newest of the stream reading and the stored one is shown; never a mix of the two
  const useLive = activeObs !== null && (stationLatestObs === null || new Date(activeObs.timestamp) >= new Date(stationLatestObs.timestamp));
  const currentTemp = useLive ? activeObs!.temperature : stationLatestObs?.temperature ?? null;
  const currentHumidity = useLive ? activeObs!.humidity : stationLatestObs?.humidity ?? null;
  const currentPressure = useLive ? activeObs!.pressure : stationLatestObs?.pressure ?? null;
  const shownTime = useLive ? activeObs!.timestamp : stationLatestObs?.timestamp ?? null;
  const dew = dewPoint(currentTemp, currentHumidity);

  const state = globeState(selectedCycle);
  const stateLabel = state === 'NO_DATA' ? (selectedCycle && selectedCycle.checked > 0 ? 'NO DATA' : 'NOT CHECKED') : state;

  return (
    <div className="space-y-6">
      <ContextualStatusStrip />

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left 7 Cols: the globe with a view switcher */}
        <div className="lg:col-span-7 space-y-3">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="text-xs font-bold uppercase tracking-wider text-slate-900 flex items-center gap-2 font-mono">
                Station map
              </h3>
              <p className="text-[11px] text-slate-600">
                {loading ? 'Loading the station list…' : `${gauges.length} Weather Union gauges plus stations from uploaded files and the stream. Click a pin to select the station. Pin colour is the latest verdict (see "?" for the words); grey means nothing checked yet.`}
              </p>
            </div>

            <div className="flex items-center gap-1.5 bg-[#FFFFFF] p-1.5 sm:p-2 rounded-xl border border-[#D3DCE7] font-mono text-xs shadow-sm">
              {(['3D', '2D'] as const).map((m) => (
                <button
                  key={m}
                  onClick={() => setMapViewMode(m)}
                  className={`px-4 py-2 sm:px-5 sm:py-2.5 rounded-lg font-bold text-xs transition-all ${
                    mapViewMode === m ? 'bg-sky-500 text-slate-950 shadow-md' : 'text-slate-600 hover:text-slate-900 hover:bg-[#E2E8F0]'
                  }`}
                >
                  {m === '3D' ? '3D Globe' : '2D Map'}
                </button>
              ))}
            </div>
          </div>

          {mapViewMode === '3D' ? (
            <StationGlobe3D stations={pins} selectedStationId={stationId ?? undefined} onSelectStation={(id) => select(id)} />
          ) : (
            <NetworkMap stations={flatPins} selectedStationId={stationId ?? undefined} onSelectStation={(id) => select(id)} />
          )}
        </div>

        {/* Right 5 Cols: the selected station's dossier */}
        <div className="lg:col-span-5 bg-[#FFFFFF] border border-[#D3DCE7] rounded-xl p-5 shadow-lg flex flex-col justify-between space-y-4">
          {!stationId ? (
            <div className="py-12 text-center text-xs text-slate-600 space-y-2">
              <p className="text-slate-900 font-bold font-mono">No station selected</p>
              <p className="text-[11px]">Pick a station to see its latest readings and verdict here. You can also click a pin on the map.</p>
              <button onClick={openStationPicker} className="mt-2 px-3.5 py-1.5 bg-sky-500 hover:bg-sky-400 text-slate-950 font-mono font-bold text-xs rounded-lg shadow">Pick a station</button>
            </div>
          ) : (
            <div>
              <div className="flex items-center justify-between border-b border-slate-200 pb-3">
                <div>
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-xs font-bold text-sky-600">{stationId}</span>
                    <StatusBadge label={stateLabel} variant={verdictVariant(state)} size="sm" />
                  </div>
                  <h4 className="text-base font-bold text-slate-900 mt-1 font-mono">{entry?.place ?? stationId}</h4>
                </div>
                <div className="text-right font-mono text-xs">
                  <span className="text-slate-500 block text-[10px] uppercase">Readings checked</span>
                  <span className="text-lg font-bold text-slate-900">{selectedCycle?.checked ?? 0}</span>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-2 mt-3 text-xs font-mono text-slate-600">
                <div className="bg-[#F4F6FA] p-2.5 rounded-lg border border-[#D3DCE7]/60">
                  <span className="text-slate-500 block text-[10px]">WGS84 Coordinates</span>
                  <span className="text-slate-900 font-semibold">
                    {gauge ? `${gauge.latitude.toFixed(4)}°N, ${gauge.longitude.toFixed(4)}°E` : streamStation && streamStation.latitude != null && streamStation.longitude != null ? `${streamStation.latitude.toFixed(4)}°N, ${streamStation.longitude.toFixed(4)}°E` : selectedCycle?.latitude != null && selectedCycle.longitude != null ? `${selectedCycle.latitude.toFixed(4)}°N, ${selectedCycle.longitude.toFixed(4)}°E` : 'no position'}
                  </span>
                </div>
                <div className="bg-[#F4F6FA] p-2.5 rounded-lg border border-[#D3DCE7]/60">
                  <span className="text-slate-500 block text-[10px]">City · device</span>
                  <span className="text-slate-900 font-semibold">{entry?.city ?? '—'}{gauge ? ` · ${gauge.device}` : ''}</span>
                </div>
              </div>

              {/* Rainfall checks of this station (stored runs) */}
              <div className="mt-4 grid grid-cols-3 gap-2 text-center font-mono">
                <div className="bg-[#F4F6FA] p-2.5 rounded-lg border border-[#D3DCE7]/60">
                  <div className="text-[10px] text-slate-500 mb-0.5">SUSPECT</div>
                  <span className="text-base font-bold text-rose-600">{selectedCycle?.suspect ?? 0}</span>
                </div>
                <div className="bg-[#F4F6FA] p-2.5 rounded-lg border border-[#D3DCE7]/60">
                  <div className="text-[10px] text-slate-500 mb-0.5">UNCERTAIN</div>
                  <span className="text-base font-bold text-amber-600">{selectedCycle?.uncertain ?? 0}</span>
                </div>
                <div className="bg-[#F4F6FA] p-2.5 rounded-lg border border-[#D3DCE7]/60">
                  <div className="text-[10px] text-slate-500 mb-0.5">Awaiting review</div>
                  <span className="text-base font-bold text-slate-900">{selectedCycle?.unaudited ?? 0}</span>
                </div>
              </div>

              {/* Temperature, pressure and humidity */}
              <div className="mt-4 space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-[10px] uppercase font-bold text-slate-500 font-mono tracking-wider">Temperature, pressure, humidity</span>
                  {shownTime && useLive && stream.live ? (
                    <span className="text-[10px] font-mono text-emerald-600 flex items-center gap-1 font-semibold">
                      <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" /> Live · {fmtUtc(shownTime)} UTC
                    </span>
                  ) : shownTime ? (
                    <span className="text-[10px] font-mono text-sky-600 flex items-center gap-1 font-semibold">
                      <span className="w-1.5 h-1.5 rounded-full bg-sky-500" /> Last reading · {fmtUtc(shownTime)} UTC ({stream.label.toLowerCase()})
                    </span>
                  ) : (
                    <span className="text-[10px] font-mono text-slate-500 flex items-center gap-1 font-semibold">
                      <span className="w-1.5 h-1.5 rounded-full bg-slate-400" /> {stream.live ? 'Waiting for a reading' : `No reading yet (${stream.label.toLowerCase()})`}
                    </span>
                  )}
                </div>

                <div className="grid grid-cols-3 gap-2 text-center font-mono">
                  <div className="bg-[#F4F6FA] p-2.5 rounded-lg border border-[#D3DCE7]/60">
                    <div className="text-[10px] text-slate-500 mb-0.5">Temperature</div>
                    <span className="text-base font-bold text-slate-900">{reading(currentTemp, 1, '°C')}</span>
                  </div>
                  <div className="bg-[#F4F6FA] p-2.5 rounded-lg border border-[#D3DCE7]/60">
                    <div className="text-[10px] text-slate-500 mb-0.5">Pressure</div>
                    <span className="text-base font-bold text-slate-900">{reading(currentPressure, 1, ' hPa')}</span>
                  </div>
                  <div className="bg-[#F4F6FA] p-2.5 rounded-lg border border-[#D3DCE7]/60">
                    <div className="text-[10px] text-slate-500 mb-0.5">Humidity</div>
                    <span className="text-base font-bold text-slate-900">{reading(currentHumidity, 1, '%')}</span>
                  </div>
                </div>

                <div className="bg-[#F4F6FA] p-2.5 rounded-lg border border-[#D3DCE7]/60 flex items-center justify-between text-xs font-mono">
                  <span className="text-slate-500">Magnus-Tetens Dew Point:</span>
                  <span className="text-slate-900 font-bold">{reading(dew, 1, '°C')}</span>
                </div>
                {obsNotBuilt && !activeObs && (
                  <p className="text-[11px] text-slate-500 font-sans">GET /api/observations did not answer (404, 501, 502 or 503).</p>
                )}
              </div>
            </div>
          )}

          <div className="pt-3 border-t border-slate-200 flex items-center gap-2">
            <button
              onClick={() => onNavigate('live')}
              className="flex-1 py-2.5 bg-sky-500 hover:bg-sky-400 text-slate-950 font-mono font-bold text-xs rounded-lg transition-all flex items-center justify-center gap-2 shadow"
            >
              Watch this station on Live →
            </button>
            <button
              onClick={openSettings}
              className="py-2.5 px-3 bg-[#F4F6FA] hover:bg-[#EDF1F7] border border-[#D3DCE7] text-slate-600 hover:text-slate-900 font-mono font-bold text-xs rounded-lg transition-all shadow"
              title="Display preferences and the input stream"
              aria-label="Display preferences and the input stream"
            >
              ⚙
            </button>
          </div>
        </div>
      </div>

      {/* Bottom grid: the station registry and the incident streams */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        <div className="lg:col-span-7 bg-[#FFFFFF] border border-[#D3DCE7] rounded-xl p-5 shadow-lg space-y-4">
          <div className="flex items-center justify-between">
            <h3 className="text-xs font-bold uppercase tracking-wider text-slate-900 flex items-center gap-2 font-mono">
              Station Registry ({stations.length} stations)
            </h3>
            <span className="text-[10px] font-mono text-slate-500">Click a row to select the station</span>
          </div>

          <div className="overflow-x-auto max-h-80 overflow-y-auto">
            <table className="w-full text-left text-xs font-mono">
              <thead className="sticky top-0 bg-[#FFFFFF] z-10">
                <tr className="border-b border-slate-200 text-slate-500 font-sans font-semibold uppercase text-[11px] tracking-wider">
                  <th className="pb-3">Station</th>
                  <th className="pb-3">City</th>
                  <th className="pb-3 text-right">Readings checked</th>
                  <th className="pb-3 text-right">Verdict</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-200">
                {loading ? (
                  <tr>
                    <td colSpan={4} className="py-6">
                      <TableSkeleton rows={4} />
                    </td>
                  </tr>
                ) : (
                  stations.map((st) => {
                    const c = cycle.find((x) => x.station_id === st.id);
                    const s = globeState(c);
                    return (
                      <tr
                        key={st.id}
                        onClick={() => select(st.id)}
                        className={`cursor-pointer transition-colors ${st.id === stationId ? 'bg-sky-500/15 border-l-2 border-sky-400' : 'hover:bg-[#EDF1F7]'}`}
                      >
                        <td className="py-2.5 text-slate-900 font-bold flex items-center gap-2">
                          <span className="text-sky-600">{st.id}</span>
                          <span className="text-slate-600 font-normal truncate max-w-[160px] font-sans">{st.place}</span>
                        </td>
                        <td className="py-2.5 text-slate-600">{st.city}</td>
                        <td className="py-2.5 text-right text-slate-700">{c?.checked ?? 0}</td>
                        <td className="py-2.5 text-right">
                          <StatusBadge label={s === 'NO_DATA' ? (c && c.checked > 0 ? 'NO DATA' : 'NOT CHECKED') : s} variant={verdictVariant(s)} size="sm" />
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
        </div>

        <div className="lg:col-span-5 bg-[#FFFFFF] border border-[#D3DCE7] rounded-xl p-5 shadow-lg space-y-4">
          <div className="flex items-center justify-between">
            <h3 className="text-xs font-bold uppercase tracking-wider text-slate-900 flex items-center gap-2 font-mono">Newest flags</h3>
            <button onClick={() => onNavigate('alerts')} className="text-xs font-mono text-sky-600 hover:underline">
              Open Alerts →
            </button>
          </div>

          <div className="space-y-2.5">
            <div className="text-[10px] uppercase font-bold text-slate-500 font-mono tracking-wider">Uploaded-file readings awaiting review</div>
            {queue === null ? (
              <p className="text-xs text-slate-500 font-mono">Loading…</p>
            ) : queue.length === 0 ? (
              <div className="p-4 text-center text-xs text-slate-500 font-sans border border-dashed border-[#D3DCE7] rounded-lg space-y-2">
                <p>Nothing is waiting for review. Flags from your own data appear here once you import a file.</p>
                <button onClick={() => onNavigate('import')} className="px-3 py-1.5 bg-[#EDF1F7] hover:bg-[#E2E8F2] text-slate-700 text-xs font-semibold rounded-lg border border-[#D3DCE7] font-mono">Import a file</button>
              </div>
            ) : (
              queue.map((r) => (
                <div
                  key={`${r.run_id}:${r.id}`}
                  onClick={() => { select(r.station_id); onNavigate('alerts'); }}
                  className="p-3 bg-[#F4F6FA] hover:bg-[#EDF1F7] border border-[#D3DCE7]/70 rounded-lg cursor-pointer transition-all space-y-1 font-mono text-xs"
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <StatusBadge label={r.verdict} variant={verdictVariant(r.verdict)} size="sm" />
                      <span className="font-bold text-slate-900">{r.station_id}</span>
                    </div>
                    <span className="text-[10px] text-slate-500">{r.time?.slice(0, 16).replace('T', ' ') ?? 'n/a'}</span>
                  </div>
                  <div className="text-slate-700 font-sans font-semibold text-[11px] truncate">{r.checks.join(', ') || 'no check fired'}</div>
                  <div className="text-[10px] text-slate-500">Rule score {r.rule_score.toFixed(2)} (uncalibrated) · run #{r.run_id}</div>
                </div>
              ))
            )}

            <div className="pt-2 text-[10px] uppercase font-bold text-slate-500 font-mono tracking-wider">Live stream detections (temperature, pressure, humidity, rain)</div>
            <AnomalyFeed limit={3} onOpen={() => onNavigate('alerts')} />
          </div>
        </div>
      </div>
    </div>
  );
}

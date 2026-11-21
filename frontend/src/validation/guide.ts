// Plain-language words of the station-first shell: what every page is for and what it reads, the rail groups and their one-line hints, the
// "Start here" guide and the legend (verdict words, scores, review decisions). Pure data and helpers, no React, so they are tested without a
// browser. The wording follows AGENTS.md (sections 1, 4, 6, 7) and CONTEXT.md; the dashboard adds no label for simulated data.
import type { KeyValueStorage, PageId } from './shell';
import { RAIL } from './shell';

/** What a page reads: the live stream, uploaded files, both, or (Settings) the server's settings. */
export type ReadsKind = 'stream' | 'files' | 'both' | 'settings';

export interface PageInfo { title: string; what: string; reads: ReadsKind; readsDetail?: string }

export const PAGE_INFO: Record<PageId, PageInfo> = {
  overview: {
    title: 'Overview',
    what: 'The map of every station, the selected station\'s latest readings and verdict, and the newest flagged readings.',
    reads: 'both',
    readsDetail: 'live readings for the temperature, pressure and humidity tiles; stored file runs for the counts and the flagged list',
  },
  live: {
    title: 'Live',
    what: 'Watch the selected station\'s readings arrive, each one with its verdict. Where readings come from is set in Settings, under "Input stream".',
    reads: 'stream',
    readsDetail: 'the input stream; the rain-gauge feed at the bottom is a separate rain-only poller',
  },
  alerts: {
    title: 'Alerts',
    what: 'Problems the checks found. The first section lists detections on live stream readings. The second lists flagged readings from uploaded-file runs that no one has reviewed yet.',
    reads: 'both',
    readsDetail: 'stream detections (top and bottom right) and uploaded-file runs (the table)',
  },
  events: {
    title: 'Events',
    what: 'The evidence behind each flag for the selected station: which check fired, what was observed, the threshold and the readings it looked at.',
    reads: 'both',
    readsDetail: 'flagged readings of the station\'s latest uploaded-file run first, then stream detections below',
  },
  explorer: {
    title: 'Explorer',
    what: 'Browse every stored reading of the selected station, newest first, with its verdict and rule score.',
    reads: 'both',
    readsDetail: 'stored stream readings first, then the station\'s uploaded-file rows',
  },
  review: {
    title: 'Review',
    what: 'Record your decision on each flagged reading: confirmed fault, false alarm, genuine extreme or needs follow-up. A decision never changes a verdict or score.',
    reads: 'files',
    readsDetail: 'flagged readings of stored runs (uploaded files and the daily rain-gauge run)',
  },
  injector: {
    title: 'Injector',
    what: 'Queue a deliberate fault (a spike, a flat line, a drift) into the simulator\'s stream to see whether the checks catch it.',
    reads: 'stream',
    readsDetail: 'the simulator stream; it changes no other source',
  },
  agent: {
    title: 'Agent',
    what: 'Ask the agent to explain the selected station\'s results. It reads them through read-only tools and may only propose; a person accepts every proposal.',
    reads: 'both',
    readsDetail: 'runs, evidence and stream state, through read-only tools',
  },
  import: {
    title: 'Import',
    what: 'Bring in your own data: upload a file, or paste an Amazon S3 or Kaggle link. Each file is checked on arrival and becomes a run you can open in Events.',
    reads: 'files',
  },
  settings: {
    title: 'Settings',
    what: 'Choose where live readings come from, manage the separate rain-gauge feed, and create MCP access tokens for other people\'s agents.',
    reads: 'settings',
  },
};

const READS_WORDS: Record<ReadsKind, string> = {
  stream: 'the live stream',
  files: 'uploaded files',
  both: 'both the live stream and uploaded files',
  settings: 'the server\'s settings',
};

/** "Reads: the live stream", with the page's detail after a dash when it has one. */
export function readsLine(page: PageId): string {
  const info = PAGE_INFO[page];
  return `Reads: ${READS_WORDS[info.reads]}${info.readsDetail ? ` (${info.readsDetail})` : ''}`;
}

// ---- the rail --------------------------------------------------------------------------------------------------------------------
export interface RailGroup { label: string; pages: PageId[] }
/** Three groups. Import is a header button and Settings a header button too, but both are listed under Tools so the rail shows them. */
export const RAIL_GROUPS: RailGroup[] = [
  { label: 'Watch', pages: ['overview', 'live', 'alerts', 'events', 'explorer'] },
  { label: 'Decide', pages: ['review', 'agent'] },
  { label: 'Tools', pages: ['injector', 'import', 'settings'] },
];

/** One line per page for the rail's tooltip. */
export const RAIL_HINT: Record<PageId, string> = {
  overview: 'Map of every station and the selected station at a glance',
  live: 'Watch the selected station\'s readings arrive',
  alerts: 'Problems the checks found, in the stream and in uploaded files',
  events: 'The evidence behind each flag',
  explorer: 'Browse every stored reading of the selected station',
  review: 'Record your decision on each flagged reading',
  agent: 'Ask the agent to explain the results (it only proposes)',
  injector: 'Put a deliberate fault into the simulator to test the checks',
  import: 'Upload a file or paste a link; it is checked on arrival',
  settings: 'Where live readings come from, rain-gauge feed, access tokens',
};

/** Key number of a page: the rail pages keep 1 to 8; Import and Settings have none (Settings answers to S). */
export function railKey(page: PageId): string | null {
  const i = RAIL.findIndex((r) => r.id === page);
  return i >= 0 ? String(i + 1) : null;
}

/** The tooltip of one rail item: its hint, then the key. */
export function railTitle(page: PageId): string {
  const key = railKey(page);
  const keyText = key ? ` (press ${key})` : page === 'settings' ? ' (press S)' : '';
  return `${PAGE_INFO[page].title}: ${RAIL_HINT[page]}${keyText}`;
}

// ---- the "Start here" guide --------------------------------------------------------------------------------------------------------
export const GUIDE_KEY = 'datamend-guide-dismissed';
export const GUIDE_INTRO = 'DataMend checks weather-station readings, flags problems and shows the evidence behind every flag. It never decides for you: a person makes every call.';

export interface GuideStep { n: number; title: string; text: string; button: string; target: PageId | 'pick-station' }
export const GUIDE_STEPS: GuideStep[] = [
  { n: 1, title: 'Pick a station', text: 'Every page shows the one station you choose in the header.', button: 'Pick a station', target: 'pick-station' },
  { n: 2, title: 'Watch it on Live', text: 'See its temperature, pressure, humidity and rain arrive, each with a verdict.', button: 'Open Live', target: 'live' },
  { n: 3, title: 'See problems on Alerts and Events', text: 'Alerts lists what was flagged. Events shows the evidence behind each flag.', button: 'Open Alerts', target: 'alerts' },
  { n: 4, title: 'Bring in your own data', text: 'Upload a file or paste a link; it is checked and added to the same station list.', button: 'Open Import', target: 'import' },
];

export const isGuideDismissed = (storage?: Pick<KeyValueStorage, 'getItem'> | null): boolean => {
  try { return storage?.getItem(GUIDE_KEY) === '1'; } catch { return false; }
};
export const dismissGuide = (storage?: Pick<KeyValueStorage, 'setItem'> | null): void => {
  try { storage?.setItem(GUIDE_KEY, '1'); } catch { /* storage blocked: the guide shows again next visit */ }
};
export const restoreGuide = (storage?: Pick<KeyValueStorage, 'removeItem'> | null): void => {
  try { storage?.removeItem(GUIDE_KEY); } catch { /* nothing to undo */ }
};

/** The event the guide sends to open the header's station picker. */
export const OPEN_PICKER_EVENT = 'datamend:open-station-picker';

// ---- the legend ------------------------------------------------------------------------------------------------------------------
export interface LegendEntry { term: string; meaning: string }
export interface LegendSection { heading: string; entries: LegendEntry[] }
export const LEGEND: LegendSection[] = [
  {
    heading: 'Verdict on one reading',
    entries: [
      { term: 'OK', meaning: 'No check that ran found a problem.' },
      { term: 'UNCERTAIN', meaning: 'Something looks odd but nothing is proven wrong, for example a heavy value that nothing nearby can confirm. Never called a fault on size alone.' },
      { term: 'SUSPECT', meaning: 'A rule was broken or the reading contradicts itself. It says the data may be wrong, not what the weather did.' },
    ],
  },
  {
    heading: 'Scores and what did not run',
    entries: [
      { term: 'Rule score', meaning: 'Rule score (uncalibrated, not a probability): a fixed-weight ordering of how suspicious a reading is, built from the checks that fired.' },
      { term: 'Not run', meaning: 'A check that could not run, with the reason (for example, no history yet). It is never skipped silently and never counted as a pass.' },
      { term: 'Model score', meaning: 'Model score (optional, not validated): a trained model\'s reconstruction error. It adds a layer when the scorer is available and never produces a verdict alone.' },
    ],
  },
  {
    heading: 'Review decisions (yours, never automatic)',
    entries: [
      { term: 'Confirmed fault', meaning: 'You checked the evidence and the reading is wrong.' },
      { term: 'False alarm', meaning: 'The reading is fine; the check should not have fired.' },
      { term: 'Genuine extreme', meaning: 'The value is unusual but real, so it is kept as measured.' },
      { term: 'Needs follow-up', meaning: 'You cannot tell yet; someone should look again.' },
    ],
  },
];

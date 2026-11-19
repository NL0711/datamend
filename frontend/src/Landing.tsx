// The public home page. It says what DataMend does and what it does not, and sends people to the dashboard (#/app).
// Nothing on it is a live number: the hero picture is an illustration and says so (dashed = not a measurement).
import { ArrowRight, CloudRain, Eye, FileUp, History, Radio, ShieldCheck, SearchCheck } from 'lucide-react';

const LINKS: [string, string][] = [['How it works', '#how'], ['What it checks', '#checks'], ['Data sources', '#data']];

const STEPS = [
  { icon: SearchCheck, title: 'Check', text: 'Every row of a rain-gauge series goes through rules, the station\'s own history and its neighbours. A row is OK, SUSPECT, UNCERTAIN or has no data.' },
  { icon: Eye, title: 'Flag, with evidence', text: 'A flag is never just a score. It carries the value, the threshold, the neighbours and the reason, in plain words you can read.' },
  { icon: ShieldCheck, title: 'Audit', text: 'A reviewer confirms a fault, calls it a false alarm or a genuine extreme. The decision is stored apart and never changes the verdict.' },
];

const CHECKS: [string, string][] = [
  ['Impossible values', 'Negative rain, or a daily total above any recorded in India.'],
  ['Counter jumps and resets', 'A cumulative counter that leaps by tens of millimetres between readings.'],
  ['Frozen readings', 'The same non-zero intensity repeated, or the same daily value day after day.'],
  ['Intensity against counter', 'Rain reported while the counter stays flat.'],
  ['Heavy for this place and season', 'A day in the extreme upper tail of the station\'s own history. Flagged as uncertain, never as a fault on size alone.'],
  ['Neighbour disagreement', 'A wet reading when nearby gauges are dry, or the other way round.'],
];

const SOURCES = [
  { icon: FileUp, tag: 'UPLOAD', title: 'Your own files', text: 'CSV or JSON, per reading or per day. File-level problems reject the file; row-level problems keep the row with a reason.' },
  { icon: Radio, tag: 'LIVE', title: 'Weather Union feed', text: 'Real rain-gauge readings, polled within a daily call budget. Needs an API key and a city, set by the admin.' },
  { icon: History, tag: 'REPLAY', title: 'NOAA ISD India replay', text: 'Real daily rainfall of Indian stations up to August 2025. Always labelled a replay, never shown as live.' },
];

function Mark({ small }: { small?: boolean }) {
  const s = small ? 22 : 26;
  return (
    <svg width={s} height={s} viewBox="0 0 24 24" aria-hidden="true">
      <path d="M12 2.2c3.4 4.4 6.2 7.7 6.2 11.3a6.2 6.2 0 1 1-12.4 0c0-3.6 2.8-6.9 6.2-11.3z" fill="#0E7490" />
      <path d="M9 14.2a3.2 3.2 0 0 0 2.4 3" stroke="#fff" strokeOpacity=".8" strokeWidth="1.3" strokeLinecap="round" fill="none" />
    </svg>);
}

const Cta = ({ children, quiet }: { children: React.ReactNode; quiet?: boolean }) => (
  <a href={quiet ? '#how' : '#/app'}
     className={`inline-flex items-center gap-2 px-5 py-3 rounded-lg text-sm font-semibold transition ${quiet ? 'border border-slate-300 text-slate-800 bg-white hover:bg-slate-50' : 'bg-teal-700 text-white hover:bg-teal-800'}`}>{children}</a>);

/** An illustration of one flagged day. Dashed and labelled: it is not data. */
function Illustration() {
  const bars = [4, 9, 0, 0, 14, 22, 6, 0, 3, 11, 58, 7];            // illustrative values only
  const max = 60;
  return (
    <figure className="rounded-xl border border-dashed border-slate-400 bg-slate-50 p-5 w-full">
      <div className="flex items-center justify-between mb-3">
        <span className="text-xs font-semibold text-slate-700">Daily rainfall, one station</span>
        <span className="text-[11px] font-mono px-2 py-0.5 rounded border border-dashed border-slate-400 text-slate-700 bg-white">ILLUSTRATION, NOT DATA</span>
      </div>
      <svg viewBox="0 0 360 150" className="w-full h-auto" role="img" aria-label="Bar chart of twelve days of illustrative rainfall; the eleventh day is flagged">
        <line x1="0" y1="130" x2="360" y2="130" stroke="#CBD5E1" />
        {bars.map((v, i) => {
          const h = (v / max) * 110;
          const flagged = i === 10;
          return <rect key={i} x={10 + i * 29} y={130 - h} width="20" height={Math.max(h, 1)} rx="3" fill={flagged ? '#DC2626' : '#7DD3FC'} />;
        })}
        <circle cx={10 + 10 * 29 + 10} cy={130 - (58 / max) * 110 - 10} r="5" fill="none" stroke="#DC2626" strokeWidth="1.5" />
      </svg>
      <figcaption className="mt-3 rounded-lg bg-white border border-slate-200 p-3 text-xs text-slate-700 space-y-1">
        <div className="flex items-center gap-2"><span className="px-1.5 py-0.5 rounded bg-red-50 border border-red-200 text-red-700 font-mono font-bold text-[10px]">UNCERTAIN</span><b>Heavy for this place and season</b></div>
        <p>Value in the extreme upper tail of this station's own earlier wet days, while the nearest gauges stayed dry. Size alone is not called a fault.</p>
      </figcaption>
    </figure>);
}

export function Landing() {
  return (
    <div className="landing min-h-screen bg-white text-slate-900">
      <header className="sticky top-0 z-20 bg-white/90 backdrop-blur border-b border-slate-200">
        <div className="mx-auto max-w-6xl px-5 h-14 flex items-center gap-6">
          <a href="#/" className="flex items-center gap-2 font-semibold"><Mark small />DataMend</a>
          <nav className="hidden md:flex items-center gap-5 text-sm text-slate-600 ml-4" aria-label="sections">
            {LINKS.map(([label, href]) => <a key={href} href={href} className="hover:text-slate-900 transition-colors">{label}</a>)}
          </nav>
          <a href="#/app" className="ml-auto inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-teal-700 text-white text-sm font-semibold hover:bg-teal-800 transition">Open dashboard <ArrowRight className="w-4 h-4" /></a>
        </div>
      </header>

      <main>
        <section className="relative overflow-hidden border-b border-slate-200">
          <div className="rain-layer" aria-hidden="true" style={{ right: '0', width: '55%', opacity: 0.55 }} />
          <div className="relative mx-auto max-w-6xl px-5 py-16 md:py-24 grid md:grid-cols-2 gap-12 items-center">
            <div>
              <p className="inline-flex items-center gap-2 text-xs font-semibold text-teal-800 bg-teal-50 border border-teal-100 rounded-full px-3 py-1"><CloudRain className="w-3.5 h-3.5" />Rainfall time-series validation</p>
              <h1 className="mt-5 text-4xl md:text-5xl font-semibold tracking-tight leading-[1.1]">Know which rain readings to trust.</h1>
              <p className="mt-5 text-lg text-slate-600 max-w-xl">DataMend checks rain-gauge data, flags what looks wrong and shows the evidence behind every flag, so a reviewer can decide in seconds.</p>
              <div className="mt-8 flex flex-wrap gap-3"><Cta>Open dashboard <ArrowRight className="w-4 h-4" /></Cta><Cta quiet>See how it works</Cta></div>
              <p className="mt-6 text-sm text-slate-500">Rainfall only. Open to read; an admin signs in to change settings and record reviews.</p>
            </div>
            <Illustration />
          </div>
        </section>

        <section id="how" className="mx-auto max-w-6xl px-5 py-20">
          <h2 className="text-3xl font-semibold tracking-tight">Check, flag, audit</h2>
          <p className="mt-3 text-slate-600 max-w-2xl">One loop for every station, from the first row to the reviewer's decision.</p>
          <ol className="mt-10 grid md:grid-cols-3 gap-5">
            {STEPS.map(({ icon: Icon, title, text }, i) => (
              <li key={title} className="rounded-xl border border-slate-200 p-6 transition hover:border-slate-300 hover:-translate-y-0.5">
                <div className="flex items-center gap-3"><span className="w-9 h-9 rounded-lg bg-teal-50 text-teal-700 flex items-center justify-center"><Icon className="w-5 h-5" /></span><span className="text-xs font-mono text-slate-500">0{i + 1}</span></div>
                <h3 className="mt-4 text-lg font-semibold">{title}</h3>
                <p className="mt-2 text-sm text-slate-600 leading-relaxed">{text}</p>
              </li>))}
          </ol>
        </section>

        <section id="checks" className="border-y border-slate-200 bg-slate-50">
          <div className="mx-auto max-w-6xl px-5 py-20">
            <h2 className="text-3xl font-semibold tracking-tight">What it checks</h2>
            <p className="mt-3 text-slate-600 max-w-2xl">Rules and statistics, not a black box. Thresholds are design choices and the score is not a probability. A check that cannot run says so.</p>
            <ul className="mt-10 grid sm:grid-cols-2 lg:grid-cols-3 gap-5">
              {CHECKS.map(([title, text]) => (
                <li key={title} className="rounded-xl bg-white border border-slate-200 p-5 transition hover:border-slate-300">
                  <h3 className="font-semibold">{title}</h3><p className="mt-1.5 text-sm text-slate-600 leading-relaxed">{text}</p>
                </li>))}
            </ul>
          </div>
        </section>

        <section id="data" className="mx-auto max-w-6xl px-5 py-20">
          <h2 className="text-3xl font-semibold tracking-tight">Where the data comes from</h2>
          <p className="mt-3 text-slate-600 max-w-2xl">Each run says where its rows came from. A replay is never shown as live, and synthetic data is always labelled synthetic.</p>
          <ul className="mt-10 grid md:grid-cols-3 gap-5">
            {SOURCES.map(({ icon: Icon, tag, title, text }) => (
              <li key={tag} className="rounded-xl border border-slate-200 p-6">
                <div className="flex items-center justify-between"><span className="w-9 h-9 rounded-lg bg-teal-50 text-teal-700 flex items-center justify-center"><Icon className="w-5 h-5" /></span>
                  <span className="text-[11px] font-mono font-bold px-2 py-0.5 rounded border border-slate-300 text-slate-700">{tag}</span></div>
                <h3 className="mt-4 text-lg font-semibold">{title}</h3><p className="mt-2 text-sm text-slate-600 leading-relaxed">{text}</p>
              </li>))}
          </ul>
        </section>

        <section className="border-t border-slate-200 bg-slate-50">
          <div className="mx-auto max-w-6xl px-5 py-16 flex flex-wrap items-center gap-6 justify-between">
            <div><h2 className="text-2xl font-semibold tracking-tight">Look at the stations on the map.</h2><p className="mt-2 text-slate-600">Every gauge and IMD station, and where each one is in check, flag and audit.</p></div>
            <Cta>Open dashboard <ArrowRight className="w-4 h-4" /></Cta>
          </div>
        </section>
      </main>

      <footer className="border-t border-slate-200">
        <div className="mx-auto max-w-6xl px-5 py-8 text-sm text-slate-500 flex flex-wrap gap-x-6 gap-y-2 justify-between">
          <span className="flex items-center gap-2"><Mark small />DataMend, rainfall validation</span>
          <span>AI explanations are generated text from a separate narrator, marked as such, and never change a verdict.</span>
        </div>
      </footer>
    </div>
  );
}

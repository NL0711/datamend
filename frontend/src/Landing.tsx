// The public home page. It says what DataMend does and what it does not, and sends people to the dashboard (#/app).
// Nothing on it is a live number: the hero picture is an illustration and says so (dashed = not a measurement).
// Look: one warm paper ground, a serif for headlines, hairline rules and plain numbered rows instead of bordered icon cards.
const SERIF = { fontFamily: "'Iowan Old Style', 'Palatino Linotype', Palatino, Georgia, serif" } as const;

const LINKS: [string, string][] = [['How it works', '#how'], ['What it checks', '#checks'], ['Data sources', '#data']];

const STEPS = [
  { title: 'Check', text: 'Every row of a rain-gauge series goes through rules, the station\'s own history and its neighbours. A row is OK, SUSPECT, UNCERTAIN or has no data.' },
  { title: 'Flag, with evidence', text: 'A flag is never just a score. It carries the value, the threshold, the neighbours and the reason, in plain words you can read.' },
  { title: 'Audit', text: 'A reviewer confirms a fault, calls it a false alarm or a genuine extreme. The decision is stored apart and never changes the verdict.' },
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
  { tag: 'UPLOAD', title: 'Your own files', text: 'CSV or JSON, per reading or per day. File-level problems reject the file; row-level problems keep the row with a reason.' },
  { tag: 'LIVE', title: 'Weather Union feed', text: 'Real rain-gauge readings, polled within a daily call budget. Needs an API key and a city, set by the admin.' },
  { tag: 'REPLAY', title: 'NOAA ISD India replay', text: 'Real daily rainfall of Indian stations up to August 2025. Always labelled a replay, never shown as live.' },
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
     className={quiet ? 'text-sm font-medium text-slate-800 underline underline-offset-4 decoration-slate-400 hover:decoration-slate-900 py-3'
       : 'inline-flex items-center px-5 py-3 rounded-sm text-sm font-semibold bg-slate-900 text-white hover:bg-teal-800 transition-colors'}>{children}</a>);

/** An illustration of one flagged day. Dashed and labelled: it is not data. */
function Illustration() {
  const bars = [4, 9, 0, 0, 14, 22, 6, 0, 3, 11, 58, 7];            // illustrative values only
  const max = 60;
  return (
    <figure className="w-full border-t-2 border-slate-900 bg-[#FBF9F4] px-5 pt-4 pb-5 shadow-[0_1px_0_rgba(15,23,42,.08)]">
      <div className="flex items-baseline justify-between mb-3">
        <span className="text-sm text-slate-800" style={SERIF}>Daily rainfall at one station, twelve days</span>
        <span className="text-[11px] font-mono uppercase tracking-wide text-slate-500">Illustration, not data</span>
      </div>
      <svg viewBox="0 0 360 150" className="w-full h-auto" role="img" aria-label="Bar chart of twelve days of illustrative rainfall; the eleventh day is flagged">
        <line x1="0" y1="130" x2="360" y2="130" stroke="#CBD5E1" />
        {bars.map((v, i) => {
          const h = (v / max) * 110;
          const flagged = i === 10;
          return <rect key={i} x={10 + i * 29} y={130 - h} width="20" height={Math.max(h, 1)} rx="0" fill={flagged ? '#DC2626' : '#94A3B8'} />;
        })}
        <circle cx={10 + 10 * 29 + 10} cy={130 - (58 / max) * 110 - 10} r="5" fill="none" stroke="#DC2626" strokeWidth="1.5" />
      </svg>
      <figcaption className="mt-3 border-l-2 border-red-600 pl-3 text-xs text-slate-700 space-y-1">
        <div className="flex items-baseline gap-2"><span className="text-red-700 font-mono font-bold text-[10px] tracking-wide">UNCERTAIN</span><b>Heavy for this place and season</b></div>
        <p>Value in the extreme upper tail of this station's own earlier wet days, while the nearest gauges stayed dry. Size alone is not called a fault.</p>
      </figcaption>
    </figure>);
}

export function Landing() {
  return (
    <div className="landing min-h-screen bg-[#F7F5EF] text-slate-900">
      <header className="sticky top-0 z-20 bg-[#F7F5EF]/95 border-b border-slate-300">
        <div className="mx-auto max-w-6xl px-5 h-14 flex items-center gap-6">
          <a href="#/" className="flex items-center gap-2 font-semibold"><Mark small />DataMend</a>
          <nav className="hidden md:flex items-center gap-5 text-sm text-slate-600 ml-4" aria-label="sections">
            {LINKS.map(([label, href]) => <a key={href} href={href} className="hover:text-slate-900 transition-colors">{label}</a>)}
          </nav>
          <a href="#/login" className="ml-auto text-sm font-semibold text-slate-700 hover:text-slate-900 px-2 py-2">Admin sign in</a>
          <a href="#/app" className="inline-flex items-center px-4 py-2 rounded-sm bg-slate-900 text-white text-sm font-semibold hover:bg-teal-800 transition-colors">Open dashboard</a>
        </div>
      </header>

      <main>
        <section className="border-b border-slate-300">
          <div className="mx-auto max-w-6xl px-5 py-16 md:py-28 grid md:grid-cols-[1.1fr_1fr] gap-14 items-end">
            <div>
              <h1 className="text-5xl md:text-7xl font-normal tracking-[-0.02em] leading-[1.02]" style={SERIF}>Know which rain readings to trust.</h1>
              <p className="mt-7 text-lg text-slate-700 max-w-xl leading-relaxed">DataMend checks rain-gauge data, flags what looks wrong and shows the evidence behind every flag, so a reviewer can decide in seconds.</p>
              <div className="mt-8 flex flex-wrap items-center gap-6"><Cta>Open dashboard</Cta><Cta quiet>See how it works</Cta></div>
              <p className="mt-6 text-sm text-slate-500">Rainfall only. Open to read; an admin signs in to change settings and record reviews.</p>
            </div>
            <Illustration />
          </div>
        </section>

        <section id="how" className="mx-auto max-w-6xl px-5 py-20 grid md:grid-cols-[1fr_2fr] gap-10 border-b border-slate-300">
          <div>
            <h2 className="text-4xl font-normal tracking-tight" style={SERIF}>Check, flag, audit</h2>
            <p className="mt-3 text-slate-700 max-w-xs">One loop for every station, from the first row to the reviewer's decision.</p>
          </div>
          <ol>
            {STEPS.map(({ title, text }, i) => (
              <li key={title} className="grid grid-cols-[3.5rem_1fr] gap-4 py-6 border-t border-slate-300 first:border-t-0 first:pt-0">
                <span className="text-4xl leading-none text-slate-400" style={SERIF}>{i + 1}</span>
                <div><h3 className="text-xl" style={SERIF}>{title}</h3><p className="mt-1.5 text-slate-700 leading-relaxed max-w-xl">{text}</p></div>
              </li>))}
          </ol>
        </section>

        <section id="checks" className="mx-auto max-w-6xl px-5 py-20 grid md:grid-cols-[1fr_2fr] gap-10 border-b border-slate-300">
          <div>
            <h2 className="text-4xl font-normal tracking-tight" style={SERIF}>What it checks</h2>
            <p className="mt-3 text-slate-700 max-w-xs">Rules and statistics, not a black box. Thresholds are design choices and the score is not a probability. A check that cannot run says so.</p>
          </div>
          <dl>
            {CHECKS.map(([title, text]) => (
              <div key={title} className="grid sm:grid-cols-[14rem_1fr] gap-x-6 gap-y-1 py-4 border-t border-slate-300 first:border-t-0 first:pt-0">
                <dt className="font-semibold text-slate-900">{title}</dt><dd className="text-slate-700 leading-relaxed">{text}</dd>
              </div>))}
          </dl>
        </section>

        <section id="data" className="mx-auto max-w-6xl px-5 py-20 grid md:grid-cols-[1fr_2fr] gap-10 border-b border-slate-300">
          <div>
            <h2 className="text-4xl font-normal tracking-tight" style={SERIF}>Where the data comes from</h2>
            <p className="mt-3 text-slate-700 max-w-xs">Each run says where its rows came from. A replay is never shown as live, and synthetic data is always labelled synthetic.</p>
          </div>
          <ul>
            {SOURCES.map(({ tag, title, text }) => (
              <li key={tag} className="py-5 border-t border-slate-300 first:border-t-0 first:pt-0">
                <div className="flex items-baseline gap-3"><h3 className="text-xl" style={SERIF}>{title}</h3><span className="text-[11px] font-mono tracking-wide text-slate-600">{tag}</span></div>
                <p className="mt-1.5 text-slate-700 leading-relaxed max-w-xl">{text}</p>
              </li>))}
          </ul>
        </section>

        <section>
          <div className="mx-auto max-w-6xl px-5 py-16 flex flex-wrap items-baseline gap-x-10 gap-y-4 justify-between">
            <h2 className="text-3xl font-normal tracking-tight max-w-xl" style={SERIF}>Every gauge and IMD station is on the map, with where it stands in check, flag and audit.</h2>
            <Cta>Open dashboard</Cta>
          </div>
        </section>
      </main>

      <footer className="border-t border-slate-300">
        <div className="mx-auto max-w-6xl px-5 py-8 text-sm text-slate-500 flex flex-wrap gap-x-6 gap-y-2 justify-between">
          <span className="flex items-center gap-2"><Mark small />DataMend, rainfall validation</span>
          <span>AI explanations are generated text from a separate narrator, marked as such, and never change a verdict.</span>
        </div>
      </footer>
    </div>
  );
}

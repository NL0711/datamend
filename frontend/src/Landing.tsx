// The public home page. It says what DataMend does and what it does not, and has one action: Sign in (#/login).
// The dashboard itself is only shown after signing in. Nothing here is a live number: the hero picture is an illustration and says so
// (dashed = not a measurement). Colours and type are the dashboard's: white ground, slate text, one teal accent, hairline rules.

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
  { tag: 'LIVE', title: 'Weather Union feed', text: 'Real rain-gauge readings, polled within a daily call budget. Needs an API key and a city.' },
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
  <a href={quiet ? '#how' : '#/login'}
     className={quiet ? 'text-sm font-medium text-slate-700 underline underline-offset-4 decoration-slate-300 hover:decoration-slate-700 py-3'
       : 'inline-flex items-center px-5 py-3 rounded-lg text-sm font-semibold bg-teal-700 text-white hover:bg-teal-800 transition-colors'}>{children}</a>);

/** An illustration of one flagged day. Dashed and labelled: it is not data. */
function Illustration() {
  const bars = [4, 9, 0, 0, 14, 22, 6, 0, 3, 11, 58, 7];            // illustrative values only
  const max = 60;
  return (
    <figure className="w-full rounded-xl border border-dashed border-slate-400 bg-slate-50 px-5 pt-4 pb-5">
      <div className="flex items-baseline justify-between mb-3">
        <span className="text-sm font-semibold text-slate-800">Daily rainfall at one station, twelve days</span>
        <span className="text-[11px] font-mono uppercase tracking-wide text-slate-500">Illustration, not data</span>
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
      <figcaption className="mt-3 border-l-2 border-red-600 pl-3 text-xs text-slate-700 space-y-1">
        <div className="flex items-baseline gap-2"><span className="text-red-700 font-mono font-bold text-[10px] tracking-wide">UNCERTAIN</span><b>Heavy for this place and season</b></div>
        <p>Value in the extreme upper tail of this station's own earlier wet days, while the nearest gauges stayed dry. Size alone is not called a fault.</p>
      </figcaption>
    </figure>);
}

export function Landing() {
  return (
    <div className="landing min-h-screen bg-white text-slate-900">
      <header className="sticky top-0 z-20 bg-white/95 border-b border-slate-200">
        <div className="mx-auto max-w-6xl px-5 h-14 flex items-center gap-6">
          <a href="#/" className="flex items-center gap-2 font-semibold"><Mark small />DataMend</a>
          <nav className="hidden md:flex items-center gap-5 text-sm text-slate-600 ml-4" aria-label="sections">
            {LINKS.map(([label, href]) => <a key={href} href={href} className="hover:text-slate-900 transition-colors">{label}</a>)}
          </nav>
          <a href="#/login" className="ml-auto inline-flex items-center px-4 py-2 rounded-lg bg-teal-700 text-white text-sm font-semibold hover:bg-teal-800 transition-colors">Sign in</a>
        </div>
      </header>

      <main>
        <section className="relative overflow-hidden border-b border-slate-200">
          <div className="rain-layer" aria-hidden="true" style={{ right: '0', width: '55%', opacity: 0.55 }} />
          <div className="relative mx-auto max-w-6xl px-5 py-16 md:py-28 grid md:grid-cols-[1.1fr_1fr] gap-14 items-center">
            <div>
              <h1 className="text-5xl md:text-6xl font-semibold tracking-tight leading-[1.05]">Know which rain readings to trust.</h1>
              <p className="mt-7 text-lg text-slate-600 max-w-xl leading-relaxed">DataMend checks rain-gauge data, flags what looks wrong and shows the evidence behind every flag, so a reviewer can decide in seconds.</p>
              <div className="mt-8 flex flex-wrap items-center gap-6"><Cta>Sign in</Cta><Cta quiet>See how it works</Cta></div>
              <p className="mt-6 text-sm text-slate-500">Rainfall only.</p>
            </div>
            <Illustration />
          </div>
        </section>

        <section id="how" className="mx-auto max-w-6xl px-5 py-20 grid md:grid-cols-[1fr_2fr] gap-10 border-b border-slate-200">
          <div>
            <h2 className="text-3xl font-semibold tracking-tight">Check, flag, audit</h2>
            <p className="mt-3 text-slate-600 max-w-xs">One loop for every station, from the first row to the reviewer's decision.</p>
          </div>
          <ol>
            {STEPS.map(({ title, text }, i) => (
              <li key={title} className="grid grid-cols-[3.5rem_1fr] gap-4 py-6 border-t border-slate-200 first:border-t-0 first:pt-0">
                <span className="text-4xl leading-none font-semibold text-teal-700/50">{i + 1}</span>
                <div><h3 className="text-xl font-semibold">{title}</h3><p className="mt-1.5 text-slate-600 leading-relaxed max-w-xl">{text}</p></div>
              </li>))}
          </ol>
        </section>

        <section id="checks" className="mx-auto max-w-6xl px-5 py-20 grid md:grid-cols-[1fr_2fr] gap-10 border-b border-slate-200">
          <div>
            <h2 className="text-3xl font-semibold tracking-tight">What it checks</h2>
            <p className="mt-3 text-slate-600 max-w-xs">Rules and statistics, not a black box. Thresholds are design choices and the score is not a probability. A check that cannot run says so.</p>
          </div>
          <dl>
            {CHECKS.map(([title, text]) => (
              <div key={title} className="grid sm:grid-cols-[14rem_1fr] gap-x-6 gap-y-1 py-4 border-t border-slate-200 first:border-t-0 first:pt-0">
                <dt className="font-semibold text-slate-900">{title}</dt><dd className="text-slate-600 leading-relaxed">{text}</dd>
              </div>))}
          </dl>
        </section>

        <section id="data" className="mx-auto max-w-6xl px-5 py-20 grid md:grid-cols-[1fr_2fr] gap-10 border-b border-slate-200">
          <div>
            <h2 className="text-3xl font-semibold tracking-tight">Where the data comes from</h2>
            <p className="mt-3 text-slate-600 max-w-xs">Each run says where its rows came from. Synthetic data is always labelled synthetic.</p>
          </div>
          <ul>
            {SOURCES.map(({ tag, title, text }) => (
              <li key={tag} className="py-5 border-t border-slate-200 first:border-t-0 first:pt-0">
                <div className="flex items-baseline gap-3"><h3 className="text-xl font-semibold">{title}</h3><span className="text-[11px] font-mono tracking-wide text-slate-600 border border-slate-300 rounded px-1.5">{tag}</span></div>
                <p className="mt-1.5 text-slate-600 leading-relaxed max-w-xl">{text}</p>
              </li>))}
          </ul>
        </section>

        <section>
          <div className="mx-auto max-w-6xl px-5 py-16 flex flex-wrap items-center gap-x-10 gap-y-4 justify-between">
            <h2 className="text-2xl font-semibold tracking-tight max-w-xl">Every gauge is on the map, with where it stands in check, flag and audit.</h2>
            <Cta>Sign in</Cta>
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

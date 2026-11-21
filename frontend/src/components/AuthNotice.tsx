// Shown when the server refused a write with 401 or 403: the action needs an admin sign-in. Never a silent failure.
export function AuthNotice({ text = 'This action needs an admin sign-in.' }: { text?: string }) {
  return (
    <div role="alert" className="p-2.5 rounded-xl bg-amber-500/15 border border-amber-500/40 text-amber-900 text-xs flex flex-wrap items-center justify-between gap-2 font-mono">
      <span>{text} The session may be missing or expired.</span>
      <button onClick={() => { window.location.hash = '#/login'; }} className="px-3 py-1 rounded-lg bg-sky-500 hover:bg-sky-400 text-slate-950 font-bold">
        Sign in
      </button>
    </div>
  );
}

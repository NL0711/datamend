// Admin sign-in. One small store (the session token and email live in localStorage, so a refresh or a new tab stays signed in until the
// server expires the session after 12 hours or you sign out) and one form used
// wherever a write needs it (imports, cleaning, the review box, training). Reading the dashboard never needs a sign-in.
import { useEffect, useSyncExternalStore, useState } from 'react';
import { LogIn, LogOut } from 'lucide-react';
import { getMe, login, logout, rememberToken, storedToken } from './api';
import { Notice, formatError } from './ui';

const EMAIL_KEY = 'datamend-admin-email';
const listeners = new Set<() => void>();
const emit = () => listeners.forEach((l) => l());

export const adminEmail = () => localStorage.getItem(EMAIL_KEY) ?? '';
const snapshot = () => `${storedToken()}|${adminEmail()}`;

export function useAdmin() {
  const snap = useSyncExternalStore((cb) => { listeners.add(cb); return () => { listeners.delete(cb); }; }, snapshot);
  const [token, email] = snap.split('|');
  useEffect(() => {              // a session the server no longer knows (restart, expiry) is dropped, not trusted
    if (!token) return;
    getMe(token).then((m) => { if (!m.signed_in) { rememberToken(''); localStorage.removeItem(EMAIL_KEY); emit(); } }).catch(() => undefined);
  }, [token]);
  return { token, email, signedIn: token.length > 0 };
}

export async function signIn(email: string, password: string) {
  const r = await login(email, password);
  rememberToken(r.token); localStorage.setItem(EMAIL_KEY, r.email); emit();
}
export async function signOut() {
  const t = storedToken();
  rememberToken(''); localStorage.removeItem(EMAIL_KEY); emit();
  if (t) await logout(t).catch(() => undefined);
}

const field = 'text-sm border border-slate-300 rounded px-3 py-2 w-full bg-white';

export function LoginForm({ why }: { why?: string }) {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true); setError('');
    try { await signIn(email, password); setPassword(''); } catch (err) { setError(formatError(err)); } finally { setBusy(false); }
  };
  return (
    <form onSubmit={(e) => void submit(e)} className="space-y-3 max-w-sm" aria-label="admin sign in">
      {why && <p className="text-sm text-slate-600">{why}</p>}
      <label className="block text-xs font-semibold text-slate-700 space-y-1"><span>Email</span>
        <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="username" required className={field} /></label>
      <label className="block text-xs font-semibold text-slate-700 space-y-1"><span>Password</span>
        <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" required className={field} /></label>
      {error && <Notice tone="error">{error}</Notice>}
      <button type="submit" disabled={busy} className="inline-flex items-center gap-2 px-4 py-2 rounded bg-teal-700 text-white text-sm font-semibold disabled:opacity-40">
        <LogIn className="w-4 h-4" />{busy ? 'Signing in…' : 'Sign in'}</button>
    </form>);
}

/** The rail footer: who is signed in, and a way out. */
export function AdminChip({ onSignIn }: { onSignIn: () => void }) {
  const { signedIn, email } = useAdmin();
  return signedIn ? (
    <div className="px-3 py-2 text-xs font-mono text-slate-600 border-t border-[#D3DCE7] mt-2">
      <div className="truncate" title={email}>Signed in as <b className="text-slate-900">{email}</b></div>
      <button onClick={() => { void signOut(); window.location.hash = '#/'; }} className="mt-1 inline-flex items-center gap-1 text-slate-700 underline"><LogOut className="w-3.5 h-3.5" />Sign out</button>
    </div>) : (
    <div className="px-3 py-2 border-t border-[#D3DCE7] mt-2"><button onClick={onSignIn} className="w-full flex items-center gap-3 px-3 py-2 rounded-lg text-xs font-semibold text-slate-600 hover:text-slate-900 hover:bg-[#EDF1F7]"><LogIn className="w-4 h-4 text-sky-600" />Sign in</button></div>);
}

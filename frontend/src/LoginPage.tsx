// The admin sign-in page (#/login). After a sign-in it goes straight to the dashboard. Reading the dashboard never needs it.
import { useEffect } from 'react';
import { ArrowLeft } from 'lucide-react';
import { LoginForm, signOut, useAdmin } from './validation/Login';

export function LoginPage() {
  const { signedIn, email } = useAdmin();
  const next = () => { window.location.hash = '#/app'; };
  useEffect(() => { if (signedIn) next(); }, [signedIn]);
  return (
    <div className="min-h-screen bg-white flex flex-col">
      <header className="h-14 border-b border-slate-200 flex items-center px-5">
        <a href="#/" className="inline-flex items-center gap-2 text-sm text-slate-600 hover:text-slate-900"><ArrowLeft className="w-4 h-4" />Home</a>
      </header>
      <main className="flex-1 flex items-center justify-center px-5 py-12">
        <div className="w-full max-w-sm">
          <svg width="32" height="32" viewBox="0 0 24 24" aria-hidden="true">
            <path d="M12 2.2c3.4 4.4 6.2 7.7 6.2 11.3a6.2 6.2 0 1 1-12.4 0c0-3.6 2.8-6.9 6.2-11.3z" fill="#0E7490" />
          </svg>
          <h1 className="mt-4 text-2xl font-semibold tracking-tight">Admin sign in</h1>
          <p className="mt-2 text-sm text-slate-600">Needed to change settings, record review decisions and load the replay. Reading the dashboard needs no account.</p>
          <div className="mt-6">
            {signedIn
              ? <p className="text-sm">Signed in as <b>{email}</b>. <button onClick={() => void signOut()} className="underline">Sign out</button></p>
              : <LoginForm />}
          </div>
          <p className="mt-6 text-sm"><a href="#/app" className="text-teal-700 font-semibold hover:underline">Continue to the dashboard without signing in</a></p>
        </div>
      </main>
    </div>);
}

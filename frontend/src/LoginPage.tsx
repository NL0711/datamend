// The sign-in page (#/login). The dashboard is only shown after signing in; a sign-in goes straight to it.
import { useEffect } from 'react';
import { ArrowLeft } from 'lucide-react';
import { LoginForm, useAdmin } from './validation/Login';

export function LoginPage() {
  const { signedIn } = useAdmin();
  useEffect(() => { if (signedIn && !window.location.hash.startsWith('#/app')) window.location.hash = '#/app'; }, [signedIn]);
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
          <h1 className="mt-4 text-2xl font-semibold tracking-tight">Sign in</h1>
          <p className="mt-2 text-sm text-slate-600">Sign in to open DataMend.</p>
          <div className="mt-6"><LoginForm /></div>
        </div>
      </main>
    </div>);
}

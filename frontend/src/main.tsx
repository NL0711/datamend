import React, { useEffect, useState } from 'react';
import ReactDOM from 'react-dom/client';
import { Landing } from './Landing';
import { LoginPage } from './LoginPage';
import { useAdmin } from './validation/Login';
import { ValidationApp } from './validation/ValidationApp';
import './index.css';
import './rain.css';

// The home page is at "/", the dashboard at "/#/app" and the admin sign-in at "/#/login" (hash routes, so the static host needs no rewrite rule).
// The legacy temperature/pressure/humidity dashboard (src/App.tsx and src/components) is no longer mounted and is deleted in slice 9.
const page = () => (window.location.hash.startsWith('#/app') ? 'app' : window.location.hash.startsWith('#/login') ? 'login' : 'home');

function Root() {
  const { signedIn } = useAdmin();
  const [p, setP] = useState(page());
  useEffect(() => {
    const on = () => { setP(page()); if (page() === 'home' && !/^#(how|checks|data)$/.test(window.location.hash)) window.scrollTo(0, 0); };
    window.addEventListener('hashchange', on);
    return () => window.removeEventListener('hashchange', on);
  }, []);
  // the dashboard is only shown to a signed-in user; anyone else is asked to sign in first
  if (p === 'app') return signedIn ? <ValidationApp /> : <LoginPage />;
  return p === 'login' ? <LoginPage /> : <Landing />;
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <Root />
  </React.StrictMode>
);

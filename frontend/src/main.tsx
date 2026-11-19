import React, { useEffect, useState } from 'react';
import ReactDOM from 'react-dom/client';
import { Landing } from './Landing';
import { ValidationApp } from './validation/ValidationApp';
import './index.css';
import './rain.css';

// The home page is at "/" and the dashboard at "/#/app" (a hash route, so the static host needs no rewrite rule for it).
// The legacy temperature/pressure/humidity dashboard (src/App.tsx and src/components) is no longer mounted and is deleted in slice 9.
const inApp = () => window.location.hash.startsWith('#/app');

function Root() {
  const [app, setApp] = useState(inApp());
  useEffect(() => {
    const on = () => { setApp(inApp()); if (!inApp() && !/^#(how|checks|data)$/.test(window.location.hash)) window.scrollTo(0, 0); };
    window.addEventListener('hashchange', on);
    return () => window.removeEventListener('hashchange', on);
  }, []);
  return app ? <ValidationApp /> : <Landing />;
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <Root />
  </React.StrictMode>
);

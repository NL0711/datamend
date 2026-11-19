import React from 'react';
import ReactDOM from 'react-dom/client';
import { ValidationApp } from './validation/ValidationApp';
import './index.css';

// The rainfall validation platform (spec slice 7). The legacy temperature/pressure/humidity dashboard (src/App.tsx and src/components)
// is no longer mounted and is deleted in slice 9.
ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <ValidationApp />
  </React.StrictMode>
);

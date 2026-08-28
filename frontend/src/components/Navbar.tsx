'use client';

import React from 'react';
import { Activity, AlertCircle, CheckCircle, Loader2, PlayCircle } from 'lucide-react';

interface NavbarProps {
  status: 'idle' | 'loading_scores' | 'scores_ready' | 'analyzing' | 'completed' | 'error';
  statusMessage?: string;
}

export const Navbar: React.FC<NavbarProps> = ({ status, statusMessage }) => {
  const renderStatusChip = () => {
    switch (status) {
      case 'loading_scores':
        return (
          <span
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: 5,
              padding: '3px 9px',
              fontSize: '0.6875rem',
              fontWeight: 700,
              textTransform: 'uppercase',
              letterSpacing: '0.04em',
              borderRadius: 4,
              backgroundColor: '#0284c7',
              color: '#ffffff',
            }}
          >
            <Loader2 size={12} className="spin" />
            Loading
          </span>
        );
      case 'scores_ready':
        return (
          <span
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: 5,
              padding: '3px 9px',
              fontSize: '0.6875rem',
              fontWeight: 700,
              textTransform: 'uppercase',
              letterSpacing: '0.04em',
              borderRadius: 4,
              backgroundColor: '#0d9488',
              color: '#ffffff',
            }}
          >
            <CheckCircle size={12} />
            Scores ready
          </span>
        );
      case 'analyzing':
        return (
          <span
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: 5,
              padding: '3px 9px',
              fontSize: '0.6875rem',
              fontWeight: 700,
              textTransform: 'uppercase',
              letterSpacing: '0.04em',
              borderRadius: 4,
              backgroundColor: '#d97706',
              color: '#ffffff',
            }}
          >
            <Activity size={12} className="spin" />
            Analyzing
          </span>
        );
      case 'completed':
        return (
          <span
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: 5,
              padding: '3px 9px',
              fontSize: '0.6875rem',
              fontWeight: 700,
              textTransform: 'uppercase',
              letterSpacing: '0.04em',
              borderRadius: 4,
              backgroundColor: '#16a34a',
              color: '#ffffff',
            }}
          >
            <CheckCircle size={12} />
            Completed
          </span>
        );
      case 'error':
        return (
          <span
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: 5,
              padding: '3px 9px',
              fontSize: '0.6875rem',
              fontWeight: 700,
              textTransform: 'uppercase',
              letterSpacing: '0.04em',
              borderRadius: 4,
              backgroundColor: '#dc2626',
              color: '#ffffff',
            }}
          >
            <AlertCircle size={12} />
            Error
          </span>
        );
      case 'idle':
      default:
        return (
          <span
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: 5,
              padding: '3px 9px',
              fontSize: '0.6875rem',
              fontWeight: 700,
              textTransform: 'uppercase',
              letterSpacing: '0.04em',
              borderRadius: 4,
              backgroundColor: '#334155',
              color: '#e2e8f0',
            }}
          >
            <span style={{ width: 6, height: 6, borderRadius: '50%', backgroundColor: '#94a3b8' }} />
            Idle
          </span>
        );
    }
  };

  return (
    <header
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '10px 24px',
        backgroundColor: '#1c4b5a',
        borderBottom: '1px solid #153843',
        color: '#ffffff',
        position: 'sticky',
        top: 0,
        zIndex: 50,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{ fontSize: '1.125rem', fontWeight: 800, color: '#ffffff', letterSpacing: '-0.01em' }}>
              DataMend
            </span>
          </div>
          <p style={{ fontSize: '0.6875rem', color: '#94a3b8', margin: 0, marginTop: 1 }}>
            Time-Series Anomaly Detection Platform
          </p>
        </div>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        {statusMessage && (
          <span
            style={{
              fontSize: '0.75rem',
              color: '#99f6e4',
              maxWidth: 400,
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
            }}
            title={statusMessage}
          >
            {statusMessage}
          </span>
        )}
        {renderStatusChip()}
      </div>
    </header>
  );
};

/**
 * frontend/src/design-system/tokens.ts
 * SkyGuard AI — Atmospheric Scientific Command Center Design Tokens.
 */

export const COLORS = {
  // Atmospheric Slate & Navy Canvas Foundation (No pure pitch black)
  bg: {
    base: '#0F1726',       // Deep mission space canvas
    surface1: '#152033',   // Primary panel & container background
    surface2: '#1B2A44',   // Elevated cards, drawers, and headers
    surface3: '#233656',   // Hover surfaces, active states, popovers
    inset: '#0C1320',      // Muted technical wells and table zebra rows
  },

  // Refined Translucent Hairline Borders
  border: {
    subtle: 'rgba(255, 255, 255, 0.08)',
    strong: '#263B5E',
    focus: '#0284C7',
    glow: 'rgba(2, 132, 199, 0.25)',
  },

  // Primary Operational Accents
  primary: {
    marine: '#0284C7',     // Main operational action
    sky: '#38BDF8',        // Accent highlights and focus lines
    indigo: '#6366F1',     // Deep analytical accent
  },

  // Strict WMO / Scientific Semantic Status Palette
  status: {
    nominal: {
      text: '#10B981',
      bg: 'rgba(16, 185, 129, 0.12)',
      border: 'rgba(16, 185, 129, 0.35)',
      badge: '#059669',
    },
    info: {
      text: '#38BDF8',
      bg: 'rgba(56, 189, 248, 0.12)',
      border: 'rgba(56, 189, 248, 0.35)',
      badge: '#0284C7',
    },
    warning: {
      text: '#F59E0B',
      bg: 'rgba(245, 158, 11, 0.12)',
      border: 'rgba(245, 158, 11, 0.35)',
      badge: '#D97706',
    },
    critical: {
      text: '#EF4444',
      bg: 'rgba(239, 68, 68, 0.14)',
      border: 'rgba(239, 68, 68, 0.40)',
      badge: '#DC2626',
    },
    extremeMet: {
      text: '#06B6D4',
      bg: 'rgba(6, 182, 212, 0.14)',
      border: 'rgba(6, 182, 212, 0.40)',
      badge: '#0891B2',
    },
    neutral: {
      text: '#94A3B8',
      bg: 'rgba(148, 163, 184, 0.10)',
      border: 'rgba(148, 163, 184, 0.25)',
      badge: '#64748B',
    },
  },

  // Channel Specific Indicator Accents
  channels: {
    temperature: '#F59E0B',  // Amber / Warm
    pressure: '#38BDF8',     // Sky Blue / Barometric
    humidity: '#818CF8',     // Indigo / Moisture
    dewPoint: '#34D399',     // Emerald / Dew Point
  },
} as const;

export const CHANNELS = {
  temperature: {
    label: 'Air Temperature',
    unit: '°C',
    color: COLORS.channels.temperature,
    minNormal: -10,
    maxNormal: 50,
    maxStepDelta: 3.0, // °C/step WMO rate-of-change
  },
  pressure: {
    label: 'Atmospheric Pressure',
    unit: 'hPa',
    color: COLORS.channels.pressure,
    minNormal: 870,
    maxNormal: 1085,
    maxStepDelta: 2.0, // hPa/step WMO rate-of-change
  },
  humidity: {
    label: 'Relative Humidity',
    unit: '%',
    color: COLORS.channels.humidity,
    minNormal: 0,
    maxNormal: 100,
    maxStepDelta: 15.0, // %/step WMO rate-of-change
  },
} as const;

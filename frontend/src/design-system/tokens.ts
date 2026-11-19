/**
 * frontend/src/design-system/tokens.ts
 * DataMend — Light Operations Theme Design Tokens.
 */

export const COLORS = {
  // Light Canvas Foundation
  bg: {
    base: '#F4F6FA',       // Page canvas
    surface1: '#FFFFFF',   // Primary panel & container background
    surface2: '#EDF1F7',   // Elevated cards, drawers, and headers
    surface3: '#E2E8F2',   // Hover surfaces, active states, popovers
    inset: '#E8EDF4',      // Muted technical wells and table zebra rows
  },

  // Refined Hairline Borders
  border: {
    subtle: 'rgba(15, 23, 42, 0.10)',
    strong: '#D3DCE7',
    focus: '#0284C7',
    glow: 'rgba(2, 132, 199, 0.18)',
  },

  // Primary Operational Accents
  primary: {
    marine: '#0284C7',     // Main operational action
    sky: '#38BDF8',        // Accent highlights and focus lines
    indigo: '#6366F1',     // Deep analytical accent
  },

  // Strict WMO / Scientific Semantic Status Palette (light-background text)
  status: {
    nominal: {
      text: '#047857',
      bg: 'rgba(16, 185, 129, 0.10)',
      border: 'rgba(16, 185, 129, 0.35)',
      badge: '#047857',
    },
    info: {
      text: '#0369A1',
      bg: 'rgba(56, 189, 248, 0.12)',
      border: 'rgba(56, 189, 248, 0.35)',
      badge: '#0369A1',
    },
    warning: {
      text: '#B45309',
      bg: 'rgba(245, 158, 11, 0.12)',
      border: 'rgba(245, 158, 11, 0.35)',
      badge: '#B45309',
    },
    critical: {
      text: '#BE123C',
      bg: 'rgba(239, 68, 68, 0.10)',
      border: 'rgba(239, 68, 68, 0.40)',
      badge: '#BE123C',
    },
    extremeMet: {
      text: '#0E7490',
      bg: 'rgba(6, 182, 212, 0.10)',
      border: 'rgba(6, 182, 212, 0.40)',
      badge: '#0891B2',
    },
    neutral: {
      text: '#64748B',
      bg: 'rgba(148, 163, 184, 0.14)',
      border: 'rgba(148, 163, 184, 0.35)',
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

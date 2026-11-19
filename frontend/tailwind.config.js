/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        datamend: {
          base: '#F4F6FA',
          surface1: '#FFFFFF',
          surface2: '#EDF1F7',
          surface3: '#E2E8F2',
          inset: '#E8EDF4',
          border: 'rgba(15, 23, 42, 0.10)',
          borderStrong: '#D3DCE7',
          primary: '#0284C7',
          primaryLight: '#38BDF8',
          nominal: '#10B981',
          warning: '#F59E0B',
          critical: '#EF4444',
          extreme: '#06B6D4',
        }
      },
      fontFamily: {
        sans: ['Inter', '-apple-system', 'BlinkMacSystemFont', 'Segoe UI', 'Roboto', 'sans-serif'],
        mono: ['ui-monospace', 'SFMono-Regular', 'Menlo', 'Monaco', 'Consolas', 'monospace'],
      }
    },
  },
  plugins: [],
}

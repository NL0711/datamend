/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        skyguard: {
          base: '#0F1726',
          surface1: '#152033',
          surface2: '#1B2A44',
          surface3: '#233656',
          inset: '#0C1320',
          border: 'rgba(255, 255, 255, 0.08)',
          borderStrong: '#263B5E',
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

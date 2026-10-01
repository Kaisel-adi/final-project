/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./app/templates/**/*.html",
    "./app/static/js/**/*.js",
  ],
  theme: {
    extend: {
      colors: {
        brand: {
          50: '#f0fdf4',
          100: '#dcfce7',
          200: '#bbf7d0',
          300: '#86efac',
          400: '#4ade80',
          500: '#22c55e', // Primary green
          600: '#16a34a', // Primary hover
          700: '#15803d',
          800: '#166534',
          900: '#14532d',
        },
        header: {
          teal: '#0d9488',
          'teal-dark': '#0f766e',
        },
        dark: {
          rail: '#181a1b',
          card: '#1e2022',
          surface: '#242729',
          border: '#2e3235',
        },
        status: {
          reported: '#ef4444',
          'reported-bg': '#fee2e2',
          verified: '#f59e0b',
          'verified-bg': '#fef3c7',
          complained: '#8b5cf6',
          'complained-bg': '#ede9fe',
          resolved: '#10b981',
          'resolved-bg': '#d1fae5',
          urgent: '#dc2626',
        }
      },
      fontFamily: {
        sans: ['"Plus Jakarta Sans"', 'Inter', '-apple-system', 'BlinkMacSystemFont', 'sans-serif'],
      },
      boxShadow: {
        'card': '0 1px 3px rgba(0,0,0,0.06), 0 1px 2px rgba(0,0,0,0.04)',
        'floating': '0 10px 15px -3px rgba(0,0,0,0.1), 0 4px 6px -2px rgba(0,0,0,0.05)',
      }
    },
  },
  plugins: [],
}

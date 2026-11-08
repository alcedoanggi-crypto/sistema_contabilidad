/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        tinta: { 50: '#f3f6fa', 100: '#e4eaf2', 200: '#c9d5e4', 400: '#6b85a8', 600: '#2f4b73', 700: '#22395b', 800: '#1a2c47', 900: '#121f33' },
        menta: { 50: '#ecfdf6', 100: '#d1fae8', 500: '#10b981', 600: '#059669', 700: '#047857' },
      },
      fontFamily: { sans: ['Inter', 'system-ui', 'Segoe UI', 'sans-serif'], mono: ['"JetBrains Mono"', 'Consolas', 'monospace'] },
    },
  },
  plugins: [],
}

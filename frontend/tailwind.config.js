/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        brand: {
          DEFAULT: '#0EA5E9',
          hover: '#0284C7',
          light: '#E0F2FE',
        },
        accent: '#F97316',
        surface: 'var(--color-surface)',
        glass: 'var(--color-glass)',
        hover: 'var(--color-hover)',
        primary: 'var(--color-primary)',
        secondary: 'var(--color-secondary)',
        muted: 'var(--color-muted)',
        border: 'var(--color-border)',
      },
      fontFamily: {
        sans: ['Inter', '-apple-system', 'BlinkMacSystemFont', 'sans-serif'],
        mono: ['Geist Mono', 'SF Mono', 'monospace'],
      },
      borderRadius: {
        'sm': '8px',
        'md': '12px',
        'lg': '16px',
        'xl': '20px',
      },
    },
  },
  plugins: [],
}

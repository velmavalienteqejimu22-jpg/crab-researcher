/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        brand: { DEFAULT: '#0EA5E9', hover: '#0284C7', light: '#E0F7FF' },
        accent: { DEFAULT: '#F97316', light: '#FFF3E8' },
      },
      fontFamily: {
        heading: ['Space Grotesk', 'system-ui', 'sans-serif'],
        body: ['DM Sans', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'monospace'],
      },
      borderRadius: {
        sm: '10px',
        md: '14px',
        lg: '20px',
        xl: '28px',
      },
      animation: {
        'fade-in': 'fade-in 0.5s ease forwards',
        'fade-in-scale': 'fade-in-scale 0.4s ease forwards',
        'float': 'float 3s ease-in-out infinite',
        'glow': 'pulse-glow 3s ease-in-out infinite',
      },
    },
  },
  plugins: [],
}

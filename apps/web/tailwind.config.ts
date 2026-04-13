import type { Config } from 'tailwindcss';

const config: Config = {
  content: [
    './app/**/*.{ts,tsx}',
    './components/**/*.{ts,tsx}',
    '../../packages/ui/src/**/*.{ts,tsx}',
  ],
  theme: {
    extend: {
      colors: {
        background: '#f5f5f4',
        foreground: '#1c1917',
        primary: {
          DEFAULT: '#0f766e',
          foreground: '#f0fdfa',
        },
        muted: {
          DEFAULT: '#e7e5e4',
          foreground: '#57534e',
        },
        card: '#ffffff',
        border: '#d6d3d1',
        accent: '#f59e0b',
      },
      borderRadius: {
        lg: '0.8rem',
        md: '0.55rem',
        sm: '0.4rem',
      },
      boxShadow: {
        panel: '0 10px 30px rgba(0,0,0,0.06)',
      },
      fontFamily: {
        sans: ['Nunito Sans', 'system-ui', 'sans-serif'],
        heading: ['Manrope', 'system-ui', 'sans-serif'],
      },
    },
  },
  plugins: [],
};

export default config;

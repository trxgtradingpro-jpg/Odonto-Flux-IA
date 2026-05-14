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
        background: 'rgb(var(--theme-background) / <alpha-value>)',
        foreground: 'rgb(var(--theme-foreground) / <alpha-value>)',
        primary: {
          DEFAULT: 'rgb(var(--theme-primary) / <alpha-value>)',
          foreground: 'rgb(var(--theme-primary-foreground) / <alpha-value>)',
        },
        secondary: 'rgb(var(--theme-secondary) / <alpha-value>)',
        muted: {
          DEFAULT: 'rgb(var(--theme-muted) / <alpha-value>)',
          foreground: 'rgb(var(--theme-muted-foreground) / <alpha-value>)',
        },
        card: 'rgb(var(--theme-card) / <alpha-value>)',
        border: 'rgb(var(--theme-border) / <alpha-value>)',
        accent: 'rgb(var(--theme-accent) / <alpha-value>)',
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

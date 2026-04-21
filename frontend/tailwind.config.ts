import type { Config } from 'tailwindcss';

const config: Config = {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        base: 'var(--bg-base)',
        surface: 'var(--bg-surface)',
        elevated: 'var(--bg-elevated)',
        'row-hover': 'var(--bg-row-hover)',
        border: {
          subtle: 'var(--border-subtle)',
          DEFAULT: 'var(--border-default)',
          strong: 'var(--border-strong)',
        },
        text: {
          primary: 'var(--text-primary)',
          secondary: 'var(--text-secondary)',
          muted: 'var(--text-muted)',
          disabled: 'var(--text-disabled)',
        },
        up: {
          DEFAULT: 'var(--accent-up)',
          bg: 'var(--accent-up-bg)',
        },
        down: {
          DEFAULT: 'var(--accent-down)',
          bg: 'var(--accent-down-bg)',
        },
        flat: 'var(--accent-flat)',
        brand: {
          DEFAULT: 'var(--accent-brand)',
          hover: 'var(--accent-brand-hover)',
        },
        focus: 'var(--accent-focus)',
        success: 'var(--accent-success)',
        warn: 'var(--accent-warn)',
        danger: 'var(--accent-danger)',
        info: 'var(--accent-info)',
        grade: {
          a: 'var(--grade-a)',
          b: 'var(--grade-b)',
          c: 'var(--grade-c)',
          d: 'var(--grade-d)',
        },
      },
      fontFamily: {
        ui: 'var(--font-ui)',
        mono: 'var(--font-mono)',
      },
      fontSize: {
        xs: ['11px', { lineHeight: '14px' }],
        sm: ['12px', { lineHeight: '16px' }],
        base: ['13px', { lineHeight: '18px' }],
        md: ['14px', { lineHeight: '20px' }],
        lg: ['16px', { lineHeight: '22px' }],
        xl: ['20px', { lineHeight: '26px' }],
        '2xl': ['28px', { lineHeight: '34px' }],
      },
      borderRadius: {
        sm: 'var(--radius-sm)',
        md: 'var(--radius-md)',
        lg: 'var(--radius-lg)',
      },
      spacing: {
        '4.5': '18px',
      },
      boxShadow: {
        card: 'var(--shadow-card)',
        elevated: 'var(--shadow-elevated)',
      },
      transitionDuration: {
        DEFAULT: '150ms',
      },
    },
  },
  plugins: [],
};

export default config;

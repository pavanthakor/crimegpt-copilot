import type { Config } from "tailwindcss";

/**
 * Design tokens ported from the CrimeGPT Stitch reference set
 * (D:\frontexndd\stitch_crimegpt_investigative_intelligence_suite — reference only).
 *
 * - Colours: the full Material-3-derived token set from the reference tailwind.config,
 *   ported verbatim so `bg-surface`, `text-on-surface-variant`, `border-outline-variant`
 *   etc. resolve exactly as the screens do.
 * - Type scale: the reference fontSize scale (display-case … mono-sm). Combined
 *   typography utilities (.font-headline-md …) live in globals.css; these keep the raw
 *   `text-headline-md` sizes available too.
 * - Fonts: semantic families backed by next/font CSS variables (layout.tsx). Body is
 *   Noto Sans (per this slice's brief), not the reference's Inter. Gujarati + Devanagari
 *   are folded into the sans stack so Indic strings never fall back to boxes.
 */
const config: Config = {
  darkMode: "class",
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        "surface-container-lowest": "#ffffff",
        tertiary: "#000000",
        "inverse-on-surface": "#f0f1f2",
        "primary-fixed": "#dae2fd",
        "on-error": "#ffffff",
        "on-surface": "#191c1d",
        "on-primary": "#ffffff",
        "on-tertiary-fixed": "#410002",
        "on-secondary-fixed-variant": "#3a485c",
        secondary: "#515f74",
        "secondary-fixed": "#d5e3fd",
        "secondary-fixed-dim": "#b9c7e0",
        "surface-bright": "#f8f9fa",
        "surface-container": "#edeeef",
        "surface-tint": "#565e74",
        "tertiary-fixed": "#ffdad6",
        "outline-variant": "#c6c6cd",
        "on-secondary-fixed": "#0d1c2f",
        "on-surface-variant": "#45464d",
        "secondary-container": "#d5e3fd",
        "surface-variant": "#e1e3e4",
        "tertiary-container": "#410002",
        primary: "#000000",
        "on-primary-fixed-variant": "#3f465c",
        "surface-dim": "#d9dadb",
        surface: "#f8f9fa",
        "on-tertiary-fixed-variant": "#93000b",
        outline: "#76777d",
        error: "#ba1a1a",
        "surface-container-high": "#e7e8e9",
        "error-container": "#ffdad6",
        "on-secondary": "#ffffff",
        "on-primary-container": "#7c839b",
        "primary-fixed-dim": "#bec6e0",
        "inverse-primary": "#bec6e0",
        "inverse-surface": "#2e3132",
        "surface-container-low": "#f3f4f5",
        "on-tertiary": "#ffffff",
        "on-primary-fixed": "#131b2e",
        "on-tertiary-container": "#ef453c",
        "tertiary-fixed-dim": "#ffb4ab",
        "on-background": "#191c1d",
        "surface-container-highest": "#e1e3e4",
        background: "#f8f9fa",
        "on-secondary-container": "#57657b",
        "on-error-container": "#93000a",
        "primary-container": "#131b2e",
        // Khaki accent — the legal-highlight marker drawn across the narrative
        // (used at ~22% opacity for the wash, full strength for the underline).
        accent: "#8a7c3f",
        "accent-strong": "#6f6330",
      },
      fontFamily: {
        // Semantic families backed by next/font variables (see app/layout.tsx).
        serif: ["var(--font-noto-serif)", "Noto Serif", "serif"],
        sans: [
          "var(--font-noto-sans)",
          "var(--font-noto-gujarati)",
          "var(--font-noto-devanagari)",
          "Noto Sans",
          "system-ui",
          "sans-serif",
        ],
        mono: ["var(--font-jetbrains-mono)", "JetBrains Mono", "monospace"],
        gujarati: ["var(--font-noto-gujarati)", "Noto Sans Gujarati", "sans-serif"],
        devanagari: ["var(--font-noto-devanagari)", "Noto Sans Devanagari", "sans-serif"],
      },
      fontSize: {
        "display-case": ["40px", { lineHeight: "48px", letterSpacing: "-0.02em", fontWeight: "700" }],
        "headline-lg": ["30px", { lineHeight: "36px", fontWeight: "700" }],
        "headline-lg-mobile": ["24px", { lineHeight: "30px", fontWeight: "700" }],
        "headline-md": ["20px", { lineHeight: "28px", fontWeight: "600" }],
        "body-lg": ["16px", { lineHeight: "24px", fontWeight: "400" }],
        "body-md": ["14px", { lineHeight: "20px", fontWeight: "400" }],
        "label-caps": ["12px", { lineHeight: "16px", letterSpacing: "0.05em", fontWeight: "600" }],
        "mono-data": ["13px", { lineHeight: "18px", fontWeight: "500" }],
        "mono-sm": ["11px", { lineHeight: "14px", fontWeight: "400" }],
      },
      borderRadius: {
        DEFAULT: "0.25rem",
        lg: "0.5rem",
        xl: "0.75rem",
        full: "9999px",
      },
      spacing: {
        unit: "4px",
        gutter: "1px",
        "container-max": "1440px",
        "edge-margin": "32px",
        "stack-sm": "8px",
        "stack-md": "16px",
        "stack-lg": "32px",
      },
    },
  },
  plugins: [],
};

export default config;

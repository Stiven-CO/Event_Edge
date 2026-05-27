import type { Config } from "tailwindcss";

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        surface: {
          base:    "#0a0e1a",
          raised:  "#0f1629",
          overlay: "#141c35",
          border:  "#1e2d4f",
          muted:   "#0d1225",
        },
        accent: "#00d2c8",
        gold:   "#e8b04b",
        ink: {
          DEFAULT:   "#e8edf5",   // text-ink → ink-primary
          primary:   "#e8edf5",
          secondary: "#8ea3c3",
          muted:     "#4a6080",
        },
        status: {
          success: "#10b981",
          warning: "#f59e0b",
          error:   "#ef4444",
          info:    "#3b82f6",
        },
        // legacy aliases (borrar cuando los componentes viejos estén migrados)
        paper:  "#0f1629",
        "ink-legacy": "#e8edf5",
        slate:  "#8ea3c3",
        sea:    "#00d2c8",
        coral:  "#ef4444",
        amber:  "#e8b04b",
        panel:  "#141c35",
        border: "#1e2d4f",
      },
      fontFamily: {
        display: ["'Space Grotesk'", "ui-sans-serif", "system-ui"],
        body:    ["Inter", "ui-sans-serif", "system-ui"],
        mono:    ["'JetBrains Mono'", "ui-monospace", "monospace"],
      },
      boxShadow: {
        card:          "0 4px 20px rgba(0,210,200,0.05), 0 1px 4px rgba(0,0,0,0.4)",
        "accent-glow": "0 0 20px rgba(0,210,200,0.25)",
        panel:         "0 4px 20px rgba(0,210,200,0.05), 0 1px 4px rgba(0,0,0,0.4)",
      },
      backgroundImage: {
        grain: "linear-gradient(rgba(30,45,79,0.25) 1px, transparent 1px), linear-gradient(90deg, rgba(30,45,79,0.25) 1px, transparent 1px)",
      },
      animation: {
        "slide-in-l": "slideInL 0.2s ease-out",
        "fade-in":    "fadeIn 0.2s ease-out",
      },
      keyframes: {
        slideInL: {
          "0%":   { transform: "translateX(-10px)", opacity: "0" },
          "100%": { transform: "translateX(0)",      opacity: "1" },
        },
        fadeIn: {
          "0%":   { opacity: "0" },
          "100%": { opacity: "1" },
        },
      },
    },
  },
  plugins: [],
} satisfies Config;

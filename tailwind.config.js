/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./src/static/*.html", "./src/static/*.js"],
  theme: {
    extend: {
      colors: {
        // Keep the existing page colors instead of adopting v4's new palette.
        slate: {
          100: "#f1f5f9",
          200: "#e2e8f0",
          300: "#cbd5e1",
          400: "#94a3b8",
          500: "#64748b",
          600: "#475569",
          700: "#334155",
        },
        red: {
          300: "#fca5a5",
          400: "#f87171",
          500: "#ef4444",
          950: "#450a0a",
        },
        ink: {
          950: "#0a0a0f",
          900: "#12121a",
          800: "#1a1a26",
          700: "#252536",
        },
        accent: {
          DEFAULT: "#a78bfa",
          dim: "#7c5fd4",
          glow: "#c4b5fd",
        },
        mint: {
          DEFAULT: "#34d399",
          dim: "#059669",
        },
      },
      blur: {
        sm: "4px",
      },
      fontFamily: {
        display: ['"SF Pro Display"', "ui-sans-serif", "system-ui", "sans-serif"],
        mono: ['"SF Mono"', "ui-monospace", "monospace"],
      },
      boxShadow: {
        card: "0 4px 24px -4px rgba(0,0,0,0.5), 0 0 0 1px rgba(255,255,255,0.04)",
        glow: "0 0 40px -10px rgba(167,139,250,0.35)",
      },
    },
  },
  plugins: [],
};

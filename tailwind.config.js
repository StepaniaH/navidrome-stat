/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./src/static/*.html", "./src/static/*.js"],
  theme: {
    extend: {
      colors: {
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

import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/app/**/*.{ts,tsx}",
    "./src/components/**/*.{ts,tsx}",
    "./src/lib/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        brand: {
          DEFAULT: "#0ea5e9",
          dark: "#0369a1",
          light: "#7dd3fc",
        },
        surface: {
          900: "#0b1120",
          800: "#0f172a",
          700: "#111c34",
          600: "#152141",
          card: "#0f1a30",
          border: "#1f2c4a",
        },
        accent: {
          green: "#22c55e",
          yellow: "#facc15",
          orange: "#f97316",
          red: "#ef4444",
        },
      },
      boxShadow: {
        card: "0 1px 0 rgba(255,255,255,0.04) inset, 0 8px 24px -12px rgba(8,12,28,0.6)",
        ring: "0 0 0 1px rgba(14,165,233,0.4), 0 8px 32px -8px rgba(14,165,233,0.35)",
      },
    },
  },
  plugins: [],
};

export default config;

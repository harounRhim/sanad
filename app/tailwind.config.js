/** @type {import('tailwindcss').Config} */
export default {
  darkMode: "class",
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        brand: {
          emerald: "#0E5A4A",
          emeraldDark: "#0A4034",
          emeraldLight: "#137A64",
          gold: "#C9A227",
          goldLight: "#E0BE4A",
          red: "#E5392B",
          cream: "#F7F3EA",
          surface: "#FFFFFF",
          ink: "#1B2A2A",
          muted: "#5C6B6B",
          dark: "#10161C",
          darkSurface: "#161D25",
          darkInk: "#E8EDEA",
          darkMuted: "#8A97A0",
        },
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
        quran: ["'Amiri Quran'", "'Scheherazade New'", "serif"],
        arabic: ["'Noto Naskh Arabic'", "serif"],
      },
      boxShadow: {
        soft: "0 2px 16px rgba(16, 22, 28, 0.08)",
      },
    },
  },
  plugins: [],
};

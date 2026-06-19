/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        sentinel: {
          background: "#0f172a",
          panel: "#1e293b",
          border: "#334155",
          accent: "#06b6d4",
          text: "#f8fafc",
          muted: "#94a3b8",
        },
      },
    },
  },
  plugins: [],
};

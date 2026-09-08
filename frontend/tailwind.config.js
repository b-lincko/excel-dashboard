/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  darkMode: "class",
  theme: {
    extend: {
      fontFamily: {
        sans: [
          "DM Sans",
          "ui-sans-serif",
          "system-ui",
          "-apple-system",
          "Segoe UI",
          "Roboto",
          "Helvetica Neue",
          "Arial",
          "sans-serif",
        ],
      },
      colors: {
        ink: {
          950: "#07111F",
          900: "#0B1220",
          800: "#111A2C",
          700: "#1A2740",
        },
        brand: {
          50: "#E6F7F3",
          100: "#C5EEE6",
          400: "#2BBFA8",
          500: "#12A38C",
          600: "#0D9F8A",
          700: "#0B7A6A",
          800: "#085E52",
        },
      },
      boxShadow: {
        card: "0 1px 2px rgba(15, 23, 42, 0.05), 0 6px 16px rgba(15, 23, 42, 0.04)",
      },
    },
  },
  plugins: [],
};

/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  darkMode: "class",
  theme: {
    extend: {
      fontFamily: {
        sans: [
          "Inter",
          "ui-sans-serif",
          "system-ui",
          "-apple-system",
          "Segoe UI",
          "Roboto",
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
          50: "#E8F6FA",
          100: "#CDEAF3",
          500: "#1D6A96",
          600: "#155A80",
          700: "#0F3D5E",
          800: "#0C314C",
        },
      },
      boxShadow: {
        card: "0 1px 2px rgba(15, 23, 42, 0.06), 0 8px 24px rgba(15, 23, 42, 0.04)",
      },
    },
  },
  plugins: [],
};

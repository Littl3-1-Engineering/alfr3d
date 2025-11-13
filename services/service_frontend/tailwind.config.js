/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        'exo2': ['Exo 2', 'sans-serif'],
      },
      colors: {
        'navy-dark': '#0A0F14',
        'charcoal': '#05070A',
      },
    },
  },
  plugins: [],
}
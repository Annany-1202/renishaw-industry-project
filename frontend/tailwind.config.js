/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: 'class',
  theme: {
    extend: {
      fontFamily: {
        sans: ['Inter', 'sans-serif'],
      },
      colors: {
        notion: {
          light: '#ffffff',
          dark: '#191919',
          sidebarLight: '#f7f7f5',
          sidebarDark: '#202020',
          borderLight: '#e9e9e7',
          borderDark: '#2f2f2f',
          hoverLight: '#efefed',
          hoverDark: '#2a2a2a',
          textLight: '#37352f',
          textDark: '#d4d4d4',
          mutedLight: '#787774',
          mutedDark: '#9b9a97'
        }
      }
    },
  },
  plugins: [],
}

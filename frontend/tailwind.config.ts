import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        primary: {
          50: "#f3f8f1",
          100: "#e5f0e4",
          200: "#cce2cf",
          300: "#a6ccb2",
          400: "#6fa78c",
          500: "#3b876c",
          600: "#226c59",
          700: "#155e53",
          800: "#124c43",
          900: "#113e37",
        },
        accent: {
          50: "#fffaf0",
          100: "#fff0dc",
          200: "#ffe0b7",
          300: "#f9ca94",
          400: "#edb270",
          500: "#d99147",
          600: "#b46e2f",
          700: "#915425",
          800: "#714321",
          900: "#58361e",
        },
      },
      backgroundImage: {
        'gradient-radial': 'radial-gradient(var(--tw-gradient-stops))',
        'gradient-mesh': 'linear-gradient(135deg, #226c59 0%, #155e53 100%)',
      },
      backdropBlur: {
        xs: '2px',
      },
      animation: {
        'slide-in': 'slide-in 0.3s ease-out',
        'slide-up': 'slide-up 0.4s ease-out',
        'fade-in': 'fade-in 0.5s ease-out',
        'scale-in': 'scale-in 0.3s ease-out',
        'float': 'float 3s ease-in-out infinite',
      },
      keyframes: {
        'slide-in': {
          '0%': { transform: 'translateX(100%)', opacity: '0' },
          '100%': { transform: 'translateX(0)', opacity: '1' },
        },
        'slide-up': {
          '0%': { transform: 'translateY(20px)', opacity: '0' },
          '100%': { transform: 'translateY(0)', opacity: '1' },
        },
        'fade-in': {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
        'scale-in': {
          '0%': { transform: 'scale(0.95)', opacity: '0' },
          '100%': { transform: 'scale(1)', opacity: '1' },
        },
        'float': {
          '0%, 100%': { transform: 'translateY(0px)' },
          '50%': { transform: 'translateY(-10px)' },
        },
      },
    },
  },
  plugins: [],
};
export default config;


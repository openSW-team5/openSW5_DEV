/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./app/templates/**/*.html",
    "./app/static/js/**/*.js",
  ],
  theme: {
    extend: {
      colors: {
        primary: '#B4DE00',
        background: '#F0F0F0',
        text: '#1B1B1B',
        success: '#4CAF50',
        warning: '#AF4C4E',
        gray: {
          DEFAULT: '#878787',
          light: '#C4C4C4',
        },
        blue: '#63A1FF',
      },
      fontFamily: {
        sans: ['Pretendard', 'Noto Sans KR', 'sans-serif'],
      },
    },
  },
  plugins: [],
}

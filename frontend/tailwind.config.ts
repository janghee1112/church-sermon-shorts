import type { Config } from "tailwindcss";

export default {
  content: ["./app/**/*.{js,ts,jsx,tsx}", "./components/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#17201c",
        cream: "#f7f4ec",
        moss: "#315f4b",
        mint: "#dcebe1",
        gold: "#d6a94b"
      },
      boxShadow: { soft: "0 18px 60px rgba(32, 52, 43, 0.10)" }
    }
  },
  plugins: []
} satisfies Config;


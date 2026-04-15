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
        bg:    "#080808",
        bg1:   "#0f0f0f",
        bg2:   "#141414",
        bg3:   "#1a1a1a",
        t1:    "#e0e0e0",
        t2:    "#888888",
        t3:    "#606060",
        red:   "#c94040",
        amber: "#ffab00",
        green: "#00e676",
      },
      fontFamily: {
        mono: ["JetBrains Mono", "monospace"],
        sans: ["JetBrains Mono", "monospace"],
      },
      borderRadius: { card: "3px" },
    },
  },
  plugins: [],
};

export default config;

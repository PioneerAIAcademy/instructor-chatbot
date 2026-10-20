import type { Config } from "tailwindcss";
import { fontFamily } from "tailwindcss/defaultTheme";

const config: Config = {
  darkMode: ["class"],
  content: ["app/**/*.{ts,tsx}", "components/**/*.{ts,tsx}"],
  theme: {
    container: {
      center: true,
      padding: "2rem",
      screens: {
        "2xl": "1400px",
      },
    },
    extend: {
      colors: {
        border: "hsl(var(--border))",
        input: "hsl(var(--input))",
        ring: "hsl(var(--ring))",
        // Keyboard-focus ring: amber, theme-aware (see --focus-ring in globals.css).
        "focus-ring": "var(--focus-ring)",
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        primary: {
          DEFAULT: "hsl(var(--primary))",
          foreground: "hsl(var(--primary-foreground))",
        },
        secondary: {
          DEFAULT: "hsl(var(--secondary))",
          foreground: "hsl(var(--secondary-foreground))",
        },
        destructive: {
          DEFAULT: "hsl(var(--destructive) / <alpha-value>)",
          foreground: "hsl(var(--destructive-foreground) / <alpha-value>)",
        },
        muted: {
          DEFAULT: "hsl(var(--muted))",
          foreground: "hsl(var(--muted-foreground))",
        },
        accent: {
          DEFAULT: "hsl(var(--accent))",
          foreground: "hsl(var(--accent-foreground))",
        },
        popover: {
          DEFAULT: "hsl(var(--popover))",
          foreground: "hsl(var(--popover-foreground))",
        },
        card: {
          DEFAULT: "hsl(var(--card))",
          foreground: "hsl(var(--card-foreground))",
        },
        // Direction D palette and roles (app/globals.css). Use these, not raw hex.
        ia: {
          "gold-1": "var(--ia-gold-1)",
          "gold-3": "var(--ia-gold-3)",
          "gray-1": "var(--ia-gray-1)",
          "gray-2": "var(--ia-gray-2)",
          "gray-3": "var(--ia-gray-3)",
          "gray-4": "var(--ia-gray-4)",
          "gray-5": "var(--ia-gray-5)",
          "blue-1": "var(--ia-blue-1)",
          "blue-2": "var(--ia-blue-2)",
          "blue-3": "var(--ia-blue-3)",
          "blue-4": "var(--ia-blue-4)",
          "navy-4": "var(--ia-navy-4)",
          "green-3": "var(--ia-green-3)",
          "red-3": "var(--ia-red-3)",
          bg: "var(--ia-bg)",
          surface: "var(--ia-surface)",
          text: "var(--ia-text)",
          "text-strong": "var(--ia-text-strong)",
          border: "var(--ia-border)",
          "border-strong": "var(--ia-border-strong)",
          link: "var(--ia-link)",
          focus: "var(--ia-focus)",
          "header-bg": "var(--ia-header-bg)",
          "header-text": "var(--ia-header-text)",
          "header-border": "var(--ia-header-border)",
          bubble: "var(--ia-bubble)",
        },
      },
      boxShadow: {
        "ia-pop": "var(--ia-shadow-pop)",
        "ia-panel": "var(--ia-shadow-panel)",
      },
      borderRadius: {
        xl: `calc(var(--radius) + 4px)`,
        lg: `var(--radius)`,
        md: `calc(var(--radius) - 2px)`,
        sm: "calc(var(--radius) - 4px)",
      },
      fontFamily: {
        // Provide a fallback in var() so unresolved --font-inter never collapses to serif defaults.
        sans: ["var(--font-mulish, Mulish)", ...fontFamily.sans],
        // Crimson Pro: the greeting and answer headings (direction D).
        display: ["var(--font-crimson, 'Crimson Pro')", "Georgia", "serif"],
        georgia: ["Georgia", "serif"],
      },
      keyframes: {
        "accordion-down": {
          from: { height: "0" },
          to: { height: "var(--radix-accordion-content-height)" },
        },
        "accordion-up": {
          from: { height: "var(--radix-accordion-content-height)" },
          to: { height: "0" },
        },
        "errorSlideIn": {
          from: { opacity: "0", transform: "translateY(8px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
      },
      animation: {
        "accordion-down": "accordion-down 0.2s ease-out",
        "accordion-up": "accordion-up 0.2s ease-out",
        "error-slide-in": "errorSlideIn 0.3s ease-out",
      },
    },
  },
  plugins: [],
};
export default config;

import type { Plugin } from "vite";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Local-first hardening: Carbon's prebuilt CSS ships ~100 @font-face rules that
// fetch IBM Plex glyph subsets (Pi/Cyrillic/Greek…) from IBM's CDN
// (1.www.s81c.com). The Latin text the UI actually renders is self-hosted via
// @fontsource, so we strip the CDN @font-face rules to keep the promise that
// nothing leaves the machine (and to survive strict-CSP / air-gapped installs).
// Missing exotic glyphs fall back to the system font — never observed in the UI.
function stripCdnFonts(): Plugin {
  const CDN = /@font-face\s*\{[^}]*1\.www\.s81c\.com[^}]*\}/g;
  return {
    name: "strip-carbon-cdn-fonts",
    enforce: "pre",
    transform(code, id) {
      if (id.includes("@carbon") && id.endsWith(".css") && code.includes("s81c.com")) {
        return { code: code.replace(CDN, ""), map: null };
      }
      return null;
    },
  };
}

// Local-first: dev server proxies /api to the local backend. In Docker the
// frontend is served by nginx which proxies /api to the backend service.
export default defineConfig({
  plugins: [stripCdnFonts(), react()],
  server: {
    host: "0.0.0.0",
    port: 3000,
    proxy: {
      "/api": {
        target: process.env.VITE_API_TARGET || "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: "dist",
    sourcemap: false,
  },
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: ["./tests/setup.ts"],
    css: false,
  },
});

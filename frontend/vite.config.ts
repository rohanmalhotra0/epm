import type { Plugin } from "vite";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
// @ts-expect-error — plain .mjs build helper, no type declarations.
import { buildExtensionZip } from "./scripts/build-extension-zip.mjs";

// Stable, unversioned URL the "Browser Agent" page links to. The download is
// served with a versioned filename via Content-Disposition / the anchor's
// download attribute.
const EXTENSION_ZIP_PATH = "/epm-wizard-extension.zip";

// Package extension/ into a downloadable zip so the web app can offer it
// directly (no repo clone needed). Serves it in dev via middleware and emits it
// into dist/ on build. Rebuilt lazily and cached; dev cache is cleared on
// SIGINT is unnecessary since the process is short-lived.
function extensionZip(): Plugin {
  let cached: { fileName: string; buffer: Buffer } | null = null;
  const zip = () => (cached ??= buildExtensionZip());
  return {
    name: "epmw-extension-zip",
    configureServer(server) {
      server.middlewares.use(EXTENSION_ZIP_PATH, (_req, res) => {
        // Rebuild every request in dev so edits to extension/ are picked up.
        const { fileName, buffer } = buildExtensionZip();
        res.setHeader("Content-Type", "application/zip");
        res.setHeader("Content-Disposition", `attachment; filename="${fileName}"`);
        res.setHeader("Content-Length", String(buffer.length));
        res.end(buffer);
      });
    },
    generateBundle() {
      const { buffer } = zip();
      this.emitFile({
        type: "asset",
        fileName: EXTENSION_ZIP_PATH.replace(/^\//, ""),
        source: buffer,
      });
    },
  };
}

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
  define: {
    __EXTENSION_ZIP_URL__: JSON.stringify(EXTENSION_ZIP_PATH),
    __EXTENSION_ZIP_NAME__: JSON.stringify(buildExtensionZip().fileName),
  },
  plugins: [stripCdnFonts(), react(), extensionZip()],
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

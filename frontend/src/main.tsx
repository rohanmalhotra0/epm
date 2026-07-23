import "@fontsource/ibm-plex-sans/400.css";
import "@fontsource/ibm-plex-sans/500.css";
import "@fontsource/ibm-plex-sans/600.css";
import "@fontsource/ibm-plex-mono/400.css";
import "@fontsource/ibm-plex-mono/500.css";
import "./styles/global.css";

import React, { lazy, Suspense } from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";

const App = lazy(() => import("./App").then(({ App }) => ({ default: App })));
const LandingPage = lazy(() => import("./pages/LandingPage").then(({ LandingPage }) => ({ default: LandingPage })));
const DocsPage = lazy(() => import("./pages/DocsPage").then(({ DocsPage }) => ({ default: DocsPage })));

// Public landing (/) vs. the authenticated app (/app/*). The app is served
// under the /app basename so the oauth2-proxy front door (epmw-auth) can gate
// exactly those paths while leaving the landing page and static assets public.
// React Router's basename keeps every in-app route string (/c/:id, /settings…)
// unchanged — they resolve under /app automatically. This is a single-bundle
// SPA, so which tree we mount is decided by the entry path at load time.
const APP_BASENAME = "/app";
const isApp =
  window.location.pathname === APP_BASENAME ||
  window.location.pathname.startsWith(`${APP_BASENAME}/`);

// global.css locks the document to the viewport for the app shell
// (body{overflow:hidden}, html/body/#root{height:100%}) because the chat UI
// manages its own internal scroll regions. The public pages (landing + docs)
// are normal, taller-than-viewport documents, so tag <html> to release that
// lock (see landing.css) — otherwise everything below the fold is clipped and
// unscrollable.
if (!isApp) document.documentElement.classList.add("landing-doc");

const root = ReactDOM.createRoot(document.getElementById("root")!);

// The public tree is a small router of its own: "/" is the marketing landing
// and "/docs" is public product documentation (both reachable without the auth
// gate — see deploy/fly/auth.fly.toml). Neither is under /app, so oauth2-proxy
// leaves them alone; nginx's SPA fallback serves index.html for a direct /docs
// hit. Cross-tree links to /app stay plain <a> so they pass through the gate.
function PublicRoutes() {
  return (
    <Routes>
      <Route path="/" element={<LandingPage />} />
      <Route path="/docs" element={<DocsPage />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

function EntryLoading() {
  return (
    <main className="page" role="status" aria-live="polite" aria-busy="true">
      Loading EPM Wizard…
    </main>
  );
}

root.render(
  <React.StrictMode>
    <Suspense fallback={<EntryLoading />}>
      {isApp ? (
        <BrowserRouter basename={APP_BASENAME}>
          <App />
        </BrowserRouter>
      ) : (
        <BrowserRouter>
          <PublicRoutes />
        </BrowserRouter>
      )}
    </Suspense>
  </React.StrictMode>,
);

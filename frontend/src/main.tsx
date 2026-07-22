import "@carbon/styles/css/styles.css";
import "@fontsource/ibm-plex-sans/400.css";
import "@fontsource/ibm-plex-sans/500.css";
import "@fontsource/ibm-plex-sans/600.css";
import "@fontsource/ibm-plex-mono/400.css";
import "@fontsource/ibm-plex-mono/500.css";
import "./styles/global.css";
import "./artifacts/artifacts.css";

import React from "react";
import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter } from "react-router-dom";
import { App } from "./App";
import { LandingPage } from "./pages/LandingPage";

const queryClient = new QueryClient({
  defaultOptions: { queries: { staleTime: 15_000, refetchOnWindowFocus: false, retry: 1 } },
});

// Public landing (/) vs. the authenticated app (/app/*). The app is served
// under the /app basename so the oauth2-proxy front door (epmw-auth) can gate
// exactly those paths while leaving the landing page and static assets public.
// React Router's basename keeps every in-app route string (/c/:id, /settings…)
// unchanged — they resolve under /app automatically. This is a single-bundle
// SPA, so which tree we mount is decided by the entry path at load time.
const APP_BASENAME = "/app";
const isApp = window.location.pathname.startsWith(APP_BASENAME);

const root = ReactDOM.createRoot(document.getElementById("root")!);

root.render(
  <React.StrictMode>
    {isApp ? (
      <QueryClientProvider client={queryClient}>
        <BrowserRouter basename={APP_BASENAME}>
          <App />
        </BrowserRouter>
      </QueryClientProvider>
    ) : (
      <LandingPage />
    )}
  </React.StrictMode>,
);

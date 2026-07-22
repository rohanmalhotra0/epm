// Bridge from the EPM Wizard web app to the "Narrated Browser Agent" Chrome
// extension. The extension injects a content script (content/site-bridge.js) on
// this origin that relays window CustomEvents to/from its service worker, so the
// page never needs the extension's (unstable) id.
//
// Event contract mirrors extension/common/protocol.js `SITE`.

const SITE = {
  PING: "epmw:ping",
  CONFIGURE: "epmw:configure",
  LAUNCH: "epmw:launch",
  READY: "epmw:extension",
} as const;

export interface ExtensionInfo {
  installed: boolean;
  version?: string;
}

export interface AgentHandoff {
  /** Backend the extension should call. Defaults to this app's origin. */
  backendUrl?: string;
  /** EPM Wizard project id → selects that project's active AI provider. */
  projectId?: string;
  /** Optional goal to prefill in the agent panel. */
  goal?: string;
}

/**
 * Detect whether the extension is installed. Resolves fast via the synchronous
 * DOM marker the content script sets at document_start, then falls back to a
 * ping/READY round-trip with a short timeout.
 */
export function detectExtension(timeoutMs = 600): Promise<ExtensionInfo> {
  const marker = document.documentElement.dataset.epmwExtension;
  if (marker) return Promise.resolve({ installed: true, version: marker });

  return new Promise((resolve) => {
    let settled = false;
    const onReady = (e: Event) => {
      if (settled) return;
      settled = true;
      window.removeEventListener(SITE.READY, onReady as EventListener);
      const detail = (e as CustomEvent).detail || {};
      resolve({ installed: true, version: detail.version });
    };
    window.addEventListener(SITE.READY, onReady as EventListener);
    window.dispatchEvent(new CustomEvent(SITE.PING));
    setTimeout(() => {
      if (settled) return;
      settled = true;
      window.removeEventListener(SITE.READY, onReady as EventListener);
      resolve({ installed: !!document.documentElement.dataset.epmwExtension });
    }, timeoutMs);
  });
}

function payload(h: AgentHandoff) {
  return {
    backendUrl: h.backendUrl ?? window.location.origin,
    projectId: h.projectId ?? "",
    ...(h.goal ? { goal: h.goal } : {}),
  };
}

/** Push backend URL + project id (+ optional goal) into the extension. */
export function configureExtension(h: AgentHandoff = {}): void {
  window.dispatchEvent(new CustomEvent(SITE.CONFIGURE, { detail: payload(h) }));
}

/** Configure and ask the extension to open its side panel. */
export function launchAgent(h: AgentHandoff = {}): void {
  window.dispatchEvent(new CustomEvent(SITE.LAUNCH, { detail: payload(h) }));
}

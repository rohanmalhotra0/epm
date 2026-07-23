// Backend-origin trust policy for the EPM Wizard site bridge.
//
// The page-to-extension bridge is intentionally available on only a small set
// of product origins. A content-script message still is not trusted merely
// because `sender.id` is this extension: a page XSS could dispatch the bridge's
// CustomEvents. We therefore bind each bridge origin to the backend origin(s)
// it may select silently. Valid self-hosted origins remain supported, but an
// extension-owned UI must explicitly approve the change.

export const TRUSTED_SITE_BACKEND_BINDINGS = Object.freeze({
  "https://epmw-auth.fly.dev": Object.freeze([
    "https://epmw-auth.fly.dev",
  ]),
  // Keep the legacy frontend deployment usable while the auth front door is
  // the preferred hosted backend.
  "https://epmw-frontend.fly.dev": Object.freeze([
    "https://epmw-frontend.fly.dev",
    "https://epmw-auth.fly.dev",
  ]),
  "http://localhost:3000": Object.freeze([
    "http://localhost:3000",
    "http://localhost:8000",
  ]),
  "http://localhost:8000": Object.freeze([
    "http://localhost:8000",
  ]),
  "http://127.0.0.1:3000": Object.freeze([
    "http://127.0.0.1:3000",
    "http://127.0.0.1:8000",
  ]),
  "http://127.0.0.1:8000": Object.freeze([
    "http://127.0.0.1:8000",
  ]),
});

export const TRUSTED_SITE_ORIGINS = Object.freeze(
  Object.keys(TRUSTED_SITE_BACKEND_BINDINGS),
);

function parseHttpUrl(value) {
  if (typeof value !== "string" || !value.trim()) return null;
  try {
    const parsed = new URL(value);
    if (!["http:", "https:"].includes(parsed.protocol)) return null;
    if (parsed.username || parsed.password) return null;
    return parsed;
  } catch {
    return null;
  }
}

function isLoopbackHostname(hostname) {
  return hostname === "localhost"
    || hostname === "127.0.0.1";
}

/**
 * Validate and canonicalize a backend URL. Backends are origin-bound: paths,
 * query strings, fragments, and embedded credentials are rejected rather than
 * silently discarded. Plain HTTP is allowed only for loopback development.
 */
export function normalizeBackendOrigin(value) {
  const parsed = parseHttpUrl(value);
  if (!parsed) return null;
  if (parsed.protocol === "http:" && !isLoopbackHostname(parsed.hostname)) return null;
  if (parsed.pathname !== "/" || parsed.search || parsed.hash) return null;
  return parsed.origin;
}

function originFromDocumentUrl(value) {
  return parseHttpUrl(value)?.origin || null;
}

function strictClaimedOrigin(value) {
  const parsed = parseHttpUrl(value);
  if (!parsed) return null;
  if (parsed.pathname !== "/" || parsed.search || parsed.hash) return null;
  return parsed.origin;
}

/**
 * Resolve the actual document origin reported by Chrome. If Chrome supplies
 * multiple sender fields they must agree; disagreement is treated as spoofing.
 */
export function getSenderPageOrigin(sender = {}) {
  const candidates = [sender.origin, sender.url, sender.tab?.url]
    .filter((value) => typeof value === "string" && value)
    .map(originFromDocumentUrl);
  if (!candidates.length || candidates.some((origin) => !origin)) return null;
  return new Set(candidates).size === 1 ? candidates[0] : null;
}

function decision(disposition, reason, fields = {}) {
  return Object.freeze({
    ok: disposition === "allow",
    disposition,
    requiresApproval: disposition === "confirm",
    reason,
    ...fields,
  });
}

/**
 * Authorize a `site.configure` / `site.launch` runtime message.
 *
 * `approvedBackendOrigin` must come from extension-owned UI/state. Never pass
 * a value copied from page event detail: doing so would let an untrusted page
 * approve itself.
 */
export function evaluateSiteBridgeRequest({
  message,
  sender,
  runtimeId,
  currentBackendUrl = "",
  approvedBackendOrigin = "",
} = {}) {
  if (!message || !["site.configure", "site.launch"].includes(message.kind)) {
    return decision("deny", "Unsupported site-bridge message.");
  }
  if (!runtimeId || sender?.id !== runtimeId) {
    return decision("deny", "Message was not relayed by this extension.");
  }

  const senderOrigin = getSenderPageOrigin(sender);
  const claimedOrigin = strictClaimedOrigin(message.pageOrigin);
  if (!senderOrigin || !claimedOrigin || senderOrigin !== claimedOrigin) {
    return decision("deny", "Claimed page origin does not match the sender document.");
  }
  const bindings = TRUSTED_SITE_BACKEND_BINDINGS[senderOrigin];
  if (!bindings) {
    return decision("deny", "The sender is not a trusted EPM Wizard site.");
  }

  const requestedValue = message.data?.backendUrl;
  if (requestedValue == null || requestedValue === "") {
    return decision("allow", "Trusted site message has no backend-origin change.", {
      pageOrigin: senderOrigin,
      backendUrl: null,
      originChanged: false,
      clearCredentials: false,
    });
  }

  const requestedOrigin = normalizeBackendOrigin(requestedValue);
  if (!requestedOrigin) {
    return decision("deny", "Backend must be an HTTPS origin or a loopback HTTP origin.", {
      pageOrigin: senderOrigin,
    });
  }

  const currentOrigin = normalizeBackendOrigin(currentBackendUrl);
  // Treat a non-empty but invalid legacy value as a different origin. It must
  // never cause credentials to survive a transition merely because it could
  // not be parsed by today's stricter policy.
  const hasCurrentBackend = typeof currentBackendUrl === "string"
    && currentBackendUrl.trim() !== "";
  const originChanged = hasCurrentBackend && currentOrigin !== requestedOrigin;
  const fields = {
    pageOrigin: senderOrigin,
    backendUrl: requestedOrigin,
    originChanged,
    // An API token scoped by convention to one server must never ride a
    // backend-origin change. The caller must clear it before any fetch.
    clearCredentials: originChanged,
  };

  if (bindings.includes(requestedOrigin)) {
    return decision("allow", "Backend is bound to the trusted site origin.", fields);
  }

  const approvedOrigin = normalizeBackendOrigin(approvedBackendOrigin);
  if (approvedOrigin && approvedOrigin === requestedOrigin) {
    return decision("allow", "Backend-origin change was explicitly approved in extension UI.", fields);
  }

  return decision(
    "confirm",
    `The site requested an unbound backend origin (${requestedOrigin}).`,
    fields,
  );
}

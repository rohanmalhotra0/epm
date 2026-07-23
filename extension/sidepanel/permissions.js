const SUPPORTED_PROTOCOLS = new Set(["https:", "http:"]);

function isLoopback(hostname) {
  return hostname === "localhost" || hostname === "127.0.0.1";
}

export function currentSitePermission(url) {
  if (typeof url !== "string" || !url.trim()) {
    throw new Error(
      "Chrome has not exposed the current page yet. Open the Oracle tab and use the extension’s site-access control in the address bar, then try again.",
    );
  }

  let parsed;
  try {
    parsed = new URL(url);
  } catch {
    throw new Error("The current tab does not have a valid web address. Open the Oracle page and try again.");
  }

  if (
    !SUPPORTED_PROTOCOLS.has(parsed.protocol)
    || (parsed.protocol === "http:" && !isLoopback(parsed.hostname))
  ) {
    throw new Error("Open an HTTPS Oracle page first. HTTP access is limited to local development.");
  }

  return {
    origin: parsed.origin,
    pattern: `${parsed.origin}/*`,
  };
}

export async function requestCurrentSiteAccess(chromeApi) {
  const [tab] = await chromeApi.tabs.query({ active: true, lastFocusedWindow: true });
  if (!tab?.id) throw new Error("No active browser tab is available.");

  if (!tab.url) {
    if (typeof chromeApi.permissions.addHostAccessRequest === "function") {
      await chromeApi.permissions.addHostAccessRequest({ tabId: tab.id });
      return {
        granted: false,
        pendingBrowserApproval: true,
        tabId: tab.id,
      };
    }
    currentSitePermission(tab.url);
  }

  const site = currentSitePermission(tab.url);
  const request = { origins: [site.pattern] };
  const alreadyGranted = await chromeApi.permissions.contains(request);
  const granted = alreadyGranted || await chromeApi.permissions.request(request);
  return {
    ...site,
    granted,
    alreadyGranted,
    pendingBrowserApproval: false,
    tabId: tab.id,
  };
}

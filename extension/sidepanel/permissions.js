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

async function currentTabUrl(chromeApi, tab) {
  if (typeof tab?.url === "string" && tab.url.trim()) return tab.url;

  // Chrome can withhold tabs.Tab.url until activeTab or host access exists,
  // which otherwise creates a circular permission flow. The debugger
  // permission is already install-time for optional canvas control; getTargets
  // does not attach to the page or show the debugger banner. Keep only the URL
  // whose tabId matches the active tab and discard all other target metadata.
  if (typeof chromeApi.debugger?.getTargets !== "function") return "";
  try {
    const targets = await chromeApi.debugger.getTargets();
    const activeTarget = targets.find((target) => (
      target?.tabId === tab.id
      && target?.type === "page"
      && typeof target.url === "string"
      && target.url.trim()
    ));
    return activeTarget?.url || "";
  } catch {
    return "";
  }
}

export async function requestCurrentSiteAccess(chromeApi) {
  const [tab] = await chromeApi.tabs.query({ active: true, lastFocusedWindow: true });
  if (!tab?.id) throw new Error("No active browser tab is available.");

  const tabUrl = await currentTabUrl(chromeApi, tab);
  if (!tabUrl) {
    if (typeof chromeApi.permissions.addHostAccessRequest === "function") {
      await chromeApi.permissions.addHostAccessRequest({ tabId: tab.id });
      return {
        granted: false,
        pendingBrowserApproval: true,
        tabId: tab.id,
      };
    }
    currentSitePermission(tabUrl);
  }

  const site = currentSitePermission(tabUrl);
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

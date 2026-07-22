// ENFORCED safety guardrail for the narrated agent.
//
// The system prompt *asks* the model not to fire destructive Oracle actions
// (deploy-to-PROD, delete, clear, run rule …). That is advice, not a guarantee:
// a wrong model decision could still click the button. This module turns the
// rule into a HARD GATE — the service worker consults it before executing every
// action and, when it flags one, the action is HELD until a human explicitly
// approves it in the side panel. Nothing destructive fires on the model's word
// alone.
//
// Two independent triggers:
//   1. Destructive target — the element the agent is about to click/type has an
//      accessible name matching a destructive verb (deploy, delete, clear, run
//      rule, refresh database, push to prod, …).
//   2. PROD context — the tab looks like a production tenant. On PROD, ANY write
//      (click/type), including blind coordinate clicks whose target we cannot
//      read, is held for confirmation.
//
// Read-only actions (scroll, wait, screenshot, navigate to a URL, done) are
// never gated.

// Destructive / irreversible verbs, matched against the target's accessible
// name (case-insensitive). Kept tight so it flags real mutations, not every
// button. Word-boundaried to avoid matching inside unrelated words.
const DESTRUCTIVE_PATTERNS = [
  /\bdeploy\b/i,
  /\bundeploy\b/i,
  /\bdelete\b/i,
  /\bremove\b/i,
  /\bdrop\b/i,
  /\bclear\b/i,
  /\bpurge\b/i,
  /\breset\b/i,
  /\bwipe\b/i,
  /\bpush\b/i,
  /\bpromote\b/i,
  /\bpublish\b/i,
  /\bmigrate\b/i,
  /\boverwrite\b/i,
  /\brefresh\s+database\b/i,
  /\bcreate\s+database\b/i,
  /\b(run|launch|execute)\s+(rule|ruleset|business rule|job|batch)\b/i,
  /\bconsolidat/i,        // consolidate / consolidation run
  /\btranslate\b/i,       // FCC translation run
];

// Signals that the current tab is a PRODUCTION tenant. Deliberately broad — a
// false "this is prod" only costs one extra confirmation click.
const PROD_HINTS = [
  /\bprod\b/i,
  /\bproduction\b/i,
  /-prd\b/i,
  /\bprd-/i,
  /\blive\b/i,
];

/** Does the current tab look like a production environment? */
export function isProdContext(url = "", title = "") {
  const hay = `${url} ${title}`;
  return PROD_HINTS.some((re) => re.test(hay));
}

/** Does this accessible name / text read as a destructive control? */
export function isDestructiveLabel(label = "") {
  if (!label) return false;
  return DESTRUCTIVE_PATTERNS.some((re) => re.test(label));
}

// Actions that never mutate the page — always safe to run unattended.
const READ_ONLY = new Set(["scroll", "wait", "screenshot", "navigate", "done"]);

/**
 * Decide whether an action must be held for human approval.
 *
 * @param {object} action  the Step's action ({type, ref, x, y, text, …})
 * @param {object} ctx     { label?: string, url?: string, title?: string }
 * @returns {{hold: boolean, reason?: string, label?: string}}
 */
export function assessAction(action, ctx = {}) {
  const type = action?.type;
  if (!type || READ_ONLY.has(type)) return { hold: false };

  const label = (ctx.label || "").trim();
  const prod = isProdContext(ctx.url, ctx.title);

  // 1) Destructive target by name — held everywhere.
  if (isDestructiveLabel(label)) {
    return {
      hold: true,
      label,
      reason: `Target "${truncate(label)}" looks destructive/irreversible`,
    };
  }

  // 2) Any write on a PROD tenant — held, even blind coordinate clicks we can't
  //    read (that opacity is exactly why PROD writes need a human).
  if (prod) {
    const where = label ? `"${truncate(label)}"` : (action.ref != null ? `ref=${action.ref}` : `(${action.x}, ${action.y})`);
    return {
      hold: true,
      label,
      reason: `Write action on a PRODUCTION tenant (${type} ${where})`,
    };
  }

  return { hold: false };
}

function truncate(s, n = 60) {
  return s.length > n ? `${s.slice(0, n - 1)}…` : s;
}

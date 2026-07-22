# Chrome Web Store submission pack

Everything you need to publish **EPM Wizard — Narrated Browser Agent** to the
Chrome Web Store. Copy the fields below into the Developer Dashboard listing;
follow the checklist at the bottom before hitting **Submit for review**.

> Reality check before you publish: this extension requests broad host access
> and the `debugger` permission and it drives a real application's UI. Reviewers
> scrutinise both. The justifications below are written to pass review, but the
> single biggest thing that gets an extension like this **removed** post-launch
> is behaving beyond its stated single purpose — so keep the behaviour matching
> the description. See also the honesty note in `README.md`: this has not been
> validated against a live Oracle tenant.

---

## Listing fields

**Name**
`EPM Wizard — Narrated Browser Agent`

**Summary** (max 132 chars)
`Watches and narrates as it drives Oracle EPM Cloud's web UI, with an enforced production-safety gate.`

**Category:** Workflow & Planning (or Developer Tools)
**Language:** English

**Detailed description**
```
EPM Wizard's Browser Agent drives Oracle EPM Cloud's web interface for you and
narrates every step in a side panel, so you can watch exactly what it does.

How it works
• It reads the page's accessibility tree — element roles, names and values — to
  decide what to click or type, targeting elements semantically rather than by
  fragile pixel coordinates.
• When a view has no accessibility information (for example canvas data grids),
  it falls back to a screenshot and a vision model.
• Each step is explained in plain language in the side panel, with optional
  spoken narration. You can pause, resume or stop at any time.

Built-in safety
• A production-safety gate is ENFORCED, not advisory: destructive actions
  (deploy, delete, clear, run rule…) and any write on a production tenant are
  held for your explicit approval before they run.

Setup
• Point the panel at your EPM Wizard backend (or launch it directly from the
  EPM Wizard web app, which configures it automatically) and type a goal.

This is an independent tool. Oracle and EPM Cloud are trademarks of Oracle. This
extension is not made, endorsed, or sponsored by Oracle.
```

**Single purpose** (required field)
```
Automate and narrate step-by-step interactions with a web-based enterprise
performance management UI (Oracle EPM Cloud), driving the page on the user's
behalf while explaining each action in a side panel.
```

**Privacy policy URL**
Host `PRIVACY.md` at a public URL and paste it here (e.g. your repo's raw file
or a docs page). Required because the extension handles website content.

---

## Permission justifications (paste into the review form)

- **`debugger`** — Captures a screenshot of the active tab
  (`Page.captureScreenshot`) as fallback grounding when a view has no
  accessibility information, and dispatches coordinate mouse clicks
  (`Input.dispatchMouseEvent`) on those same views. Not used to read network
  traffic or inspect other tabs.
- **`activeTab`** — Grants access to the tab the user is actively driving.
- **`scripting`** — Injects the content script that reads the accessibility tree
  and performs click/type/scroll actions by element reference.
- **`tabs`** — Identifies the active tab to drive and re-injects the content
  script after navigation.
- **`sidePanel`** — Presents the step-by-step narration UI.
- **`storage`** — Stores the user's settings and the current run transcript
  locally.
- **Host permission `https://*/*`** — The target application (Oracle EPM Cloud)
  can be hosted on any HTTPS domain and tenant subdomain, so the agent must be
  able to read and act on the page the user chooses. It operates only on the tab
  the user actively drives.
- **Host permission `http://localhost/*`** — Local development against a
  localhost backend/app.

## Data-usage disclosures (Privacy tab)

- **Does the item collect user data?** Yes — website content.
- **What is collected:** Website content (accessibility snapshots + screenshots
  of the active tab) and user-typed goals, sent to the user-configured backend.
- **Not collected/used for:** No personally identifiable info beyond page
  content, no health/financial data collection by the extension itself, no
  location, no authentication credentials read or stored by the extension.
- **Sold to third parties:** No.
- **Used for purposes unrelated to core functionality:** No.
- **Used for creditworthiness / lending:** No.

Check all three certification boxes (no selling, no unrelated use, no
creditworthiness use) — they are true for this extension.

---

## Assets you must produce

- **Store icon:** 128×128 — already in `icons/icon128.png`.
- **Screenshots:** at least one, 1280×800 or 640×400 PNG/JPEG. Capture the side
  panel mid-run (narration feed visible) and the enforced-guardrail confirmation
  banner — the safety gate is a selling point and reviewers like seeing it.
- **Small promo tile (optional):** 440×280.

## Pre-submission checklist

- [ ] `manifest.json` version bumped for this release.
- [ ] `icons/` present (16/32/48/128) and referenced by `icons` + `action.default_icon`.
- [ ] Privacy policy hosted at a public URL and pasted into the listing.
- [ ] Permission justifications pasted (above).
- [ ] Screenshots uploaded (panel + guardrail banner).
- [ ] Zip built with `scripts/package.sh` and uploaded.
- [ ] Tested load-unpacked end to end in a clean Chrome profile.
- [ ] Description matches actual behaviour (single-purpose compliance).
- [ ] If pointing at a hosted backend, that backend's privacy terms are linked.

## Build the upload zip

```bash
cd extension
./scripts/package.sh          # → dist/epm-wizard-extension-<version>.zip
```

Upload that zip in the Developer Dashboard → **Package** → **Upload new package**.

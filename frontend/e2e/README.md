# Human-style browser testing

This harness runs the real React app, nginx proxy, FastAPI service, database
migrations, and deterministic local AI provider in Chromium. The local stack is
isolated from normal development data: its backend `/data` directory is a Docker
`tmpfs` and vanishes when the test stack stops.

## First run

Prerequisites: Docker Desktop (or Docker Engine + Compose), Node 20+, and npm.

```bash
cd frontend
npm ci
npx playwright install chromium
npm run e2e
```

Useful interactive modes:

```bash
npm run e2e:headed
npm run e2e:ui
npm run e2e:debug
npm run e2e:report
```

Failures retain a Playwright trace, screenshot, video, browser console errors,
failed API requests, and an axe accessibility report under `test-results/` and
`playwright-report/`. Both directories are ignored by git.

## OAuth without sharing credentials with an agent

Local and CI runs do not weaken or patch production OAuth. They run without the
external login gate and inject `X-Forwarded-Email`, exactly the identity header
the trusted `oauth2-proxy` supplies. The backend still runs with
`EPMW_MULTI_USER=true`, and the suite verifies that two identities cannot see
one another's projects.

For a deployed staging environment, capture a real provider session once in a
headed browser:

```bash
E2E_BASE_URL=https://epmw-auth.example.test npm run e2e:auth
```

Complete Google/GitHub login and MFA yourself. Playwright saves only the browser
session to `playwright/.auth/user.json`; that directory is gitignored because
the cookie can impersonate the test user. Agents can then reuse it:

```bash
E2E_BASE_URL=https://epmw-auth.example.test npm run e2e
```

Use a dedicated, least-privileged staging account. Delete
`playwright/.auth/user.json` to revoke the local copy, and capture it again when
the session expires. Never commit the file or give the suite passwords, MFA
seeds, OAuth client secrets, or a personal production session.

The Oracle EPM credential screen is separate from the website's Google/GitHub
gate. Offline E2E tests choose **Continue without Oracle** and use the demo
connector. The backend's OAuth client-credential exchange has deterministic
unit coverage. A live Oracle journey should use a dedicated non-production
tenant and secrets supplied by the CI secret store, never values in test files.

## Configuration

| Variable | Purpose |
| --- | --- |
| `E2E_BASE_URL` | Test a deployed origin instead of starting Docker locally |
| `E2E_STORAGE_STATE` | Override the OAuth state file path |
| `E2E_USER_EMAIL` | Local simulated proxy identity |
| `E2E_SLOW_MO` | Delay each browser action by N milliseconds |
| `E2E_IGNORE_HTTPS_ERRORS=1` | Allow a staging origin with a private certificate |

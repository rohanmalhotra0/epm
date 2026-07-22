# Deploying EPM Wizard on Fly.io

The hosting direction (rationale, model choices, phased build order) is in
[`docs/OPENCLAW_PLAN.md`](../../docs/OPENCLAW_PLAN.md) — read it first. This
directory holds the executable pieces for the Fly.io hosting target: two apps
(frontend + backend) on private `.internal` networking, an optional
oauth2-proxy login gate, and external Neon Postgres.

## Layout

```
deploy/fly/
├── backend.fly.toml     backend app: FastAPI on 8000, PRIVATE, always-warm
│                        (min_machines_running=1 so SSE never cold-starts),
│                        persistent /data volume
├── frontend.fly.toml    frontend app: nginx on 3000, PUBLIC, scale-to-zero;
│                        proxies /api to the backend over 6PN
├── auth.fly.toml        optional oauth2-proxy front door (Google/GitHub + email
│                        allowlist) — the only public entry point when enabled
├── deploy-fly.sh        bootstrap: create apps, volume, set secrets, deploy both,
│                        print the public URL. Idempotent. `deploy` / `teardown`.
└── README.md            this file
```

The apps reuse the existing images — `backend/Dockerfile` (uvicorn on
`0.0.0.0:8000`) and `frontend/Dockerfile` (nginx on 3000, whose `nginx.conf`
proxies `/api` to `${BACKEND_URL}`). Nothing in the app source changes.

## Architecture

```
Users ──► https://epmw-auth.fly.dev   (oauth2-proxy, PUBLIC, optional)
              │  Google/GitHub OAuth + email allowlist
              │  injects X-Forwarded-Email
              ▼  http://epmw-frontend.internal:3000   (6PN)
          frontend (nginx, PRIVATE once auth is on)
              │  proxies /api, forwards X-Forwarded-Email
              ▼  http://epmw-backend.internal:8000     (6PN)
          backend (FastAPI, PRIVATE, always warm)
              ├──► Together AI            (TOGETHER_API_KEY)
              └──► Neon Postgres          (EPMW_DATABASE_URL, sslmode=require)
```

Without the auth app, the **frontend** is the public entry point (fine for a
quick demo, not for real data — see §6).

---

## 1. Install flyctl and log in

```bash
# macOS/Linux
curl -L https://fly.io/install.sh | sh
# then add flyctl to PATH per the installer's instructions

fly auth login          # opens a browser
fly auth whoami         # confirm
```

`deploy-fly.sh` refuses to run until both `flyctl` is on PATH and you are
logged in.

## 2. Get a Neon Postgres database (recommended over Fly MPG)

Neon is external, cheap (a free tier covers 3–5 light users), and needs no
custom certificate bundle — plain `sslmode=require` is enough (no
`verify-full` + CA path to mount).

1. Create a project at <https://neon.tech> and copy its connection string.
2. Rewrite the driver prefix to the one the backend uses (`postgresql+psycopg`)
   and keep `sslmode=require`:

   ```
   postgresql+psycopg://USER:PASSWORD@ep-xxx.REGION.aws.neon.tech/neondb?sslmode=require
   ```

   The backend already supports this via `EPMW_DATABASE_URL` (see
   `backend/app/config.py`); when unset it falls back to SQLite on the volume.
   The app runs its Alembic migrations on startup, so the empty Neon database is
   populated automatically on first boot.

Fly Managed Postgres (MPG) is a fine alternative if you prefer everything on
Fly, but per `OPENCLAW_PLAN.md` Neon is the cheaper default at this scale.

## 3. Export the secrets

The deploy script reads three values from your environment and pushes them to
Fly as secrets (never written to any `.toml`):

```bash
export TOGETHER_API_KEY='sk-...'                    # Together AI key
export EPMW_DATABASE_URL='postgresql+psycopg://USER:PASSWORD@ep-xxx.REGION.aws.neon.tech/neondb?sslmode=require'
export EPMW_SECRET_MASTER_KEY="$(openssl rand -base64 32)"   # stable — save it
```

`EPMW_SECRET_MASTER_KEY` encrypts the app's local secret store (provider keys
entered in-app). Set it once and keep it: rotating it makes previously stored
in-app secrets unreadable.

## 4. Deploy

```bash
cd /path/to/epm            # repo root — the script finds itself either way
./deploy/fly/deploy-fly.sh
```

The script (idempotent — re-run any time to ship a new image):

1. checks `flyctl` + login,
2. creates `epmw-backend` and its `epmw_data` volume if missing,
3. stages the three secrets on the backend,
4. deploys the backend from the repo root (`--ha=false`, single machine to
   match the single volume), then releases any public IP so it is 6PN-only,
5. creates + deploys the public `epmw-frontend`,
6. prints `https://epmw-frontend.fly.dev`.

Override app names/region with `BACKEND_APP`, `FRONTEND_APP`, `FLY_REGION`,
`FLY_ORG` env vars. If you rename the backend app, also change `BACKEND_URL` in
`frontend.fly.toml`.

**Rollback.** List releases and redeploy a previous image:

```bash
fly releases --app epmw-backend
fly deploy --app epmw-backend --image <registry.fly.io/...:deployment-XXXX>
```

**Teardown** (destroys both apps + the volume):

```bash
./deploy/fly/deploy-fly.sh teardown
```

## 5. Verify

```bash
fly logs --app epmw-backend            # watch startup + migrations
fly ssh console --app epmw-backend -C 'wget -qO- http://localhost:8000/api/health'
open https://epmw-frontend.fly.dev
```

## 6. Add the oauth2-proxy login gate (before sharing the URL)

This is the recommended auth for a few known users (no password storage) — the
Fly equivalent of the old IBM App ID gate. It puts `epmw-auth` in front as the
only public app; the frontend becomes private.

1. **Create an OAuth client.**
   - Google: <https://console.cloud.google.com> → *APIs & Services →
     Credentials* → OAuth client (Web application). Authorized redirect URI:
     `https://epmw-auth.fly.dev/oauth2/callback`.
   - (GitHub works too — set `OAUTH2_PROXY_PROVIDER=github` in `auth.fly.toml`
     and use `https://epmw-auth.fly.dev/oauth2/callback` as the callback.)

2. **Create the app + secrets.** No volume needed — the default config keeps
   the proxy stateless. The cookie secret MUST be URL-safe base64:
   oauth2-proxy only auto-decodes the URL-safe alphabet, so plain
   `openssl rand -base64 32` output (44 chars with `+/`) is read as 44 raw
   bytes and the proxy crash-loops with
   `cookie_secret must be 16, 24, or 32 bytes`.

   ```bash
   fly apps create epmw-auth --org personal
   fly secrets set --app epmw-auth --stage \
     OAUTH2_PROXY_CLIENT_ID='<client-id>' \
     OAUTH2_PROXY_CLIENT_SECRET='<client-secret>' \
     OAUTH2_PROXY_COOKIE_SECRET="$(openssl rand -base64 32 | tr -- '+/' '-_')"
   fly deploy --config deploy/fly/auth.fly.toml --app epmw-auth --ha=false --yes
   ```

3. **Set the allowlist** — who may sign in. Either:
   - **Google test-users (default, simplest)**: keep the OAuth consent screen
     in *Testing* mode and add each allowed email under *Test users* — only
     they can clear the Google sign-in.
   - **whole domain**: set `OAUTH2_PROXY_EMAIL_DOMAINS = "yourcompany.com"` in
     `auth.fly.toml` and redeploy.
   - **proxy-enforced file** (optional hardening): uncomment
     `OAUTH2_PROXY_AUTHENTICATED_EMAILS_FILE` and the `[mounts]` block in
     `auth.fly.toml`, create the volume, redeploy, then write
     `/etc/oauth2-proxy/emails.txt` (one email per line) via
     `fly ssh console --app epmw-auth`.

4. **Make the frontend private** so the gate can't be bypassed:

   ```bash
   fly ips list --app epmw-frontend        # note the public addresses
   fly ips release <addr> --app epmw-frontend   # release each public IP
   ```

   The frontend stays reachable at `epmw-frontend.internal:3000`, which is
   exactly what `OAUTH2_PROXY_UPSTREAMS` in `auth.fly.toml` targets.

Now the public URL is **`https://epmw-auth.fly.dev`**. Identity flows
oauth2-proxy → nginx (`X-Forwarded-Email`) → backend, which scopes each user's
projects because `EPMW_MULTI_USER=true` is set in `backend.fly.toml`.

## 7. Invite a user

Add their email to the allowlist (Google *Test users* by default; a domain
covers them automatically if you set one), then send them
`https://epmw-auth.fly.dev`. They sign in with Google/GitHub in the browser —
nothing to install.

---

## Cost

~$10–20/mo on Fly (backend warm 24/7 on `shared-cpu-1x`/1GB; frontend + auth
scale to zero) plus external Neon Postgres (free tier at this scale). Together
AI inference is billed per token separately — see the cost table in
`docs/OPENCLAW_PLAN.md`.

## Notes / caveats

- **Backend must stay a single machine** while it uses one volume
  (`--ha=false`, baked into the script). To run HA later, add a second volume
  and move durable state to Postgres + object storage.
- **The `/data` volume is required even with Neon** — artifacts, contexts, the
  encrypted secret store, RAG indexes and SQLite backups live there.
- **Backend privacy is best-effort in the script** (it releases public IPs
  after deploy). Confirm with `fly ips list --app epmw-backend`; there should be
  no `public` rows.
- **`.internal` 6PN DNS** requires both apps in the same Fly org. That is the
  default; override with `FLY_ORG` consistently for all apps.

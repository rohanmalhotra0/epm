# Security model

EPM Wizard is local-first. The threat model centers on **never leaking secrets**
to the model, logs, git, or generated artifacts, and on **never letting the model
execute anything** outside a typed, allowlisted surface.

## Secrets never reach the model or logs

Protected: Oracle passwords, AI provider API keys, OAuth tokens, EPM Automate
encrypted password files, session cookies, encryption keys, authorization headers.

- **Centralized redaction** (`app/security/redaction.py`) scrubs every structured
  log line, tool result, error message, and diagnostics bundle. It matches common
  patterns (Bearer/Basic auth, `sk-…`, `sk-ant-…`, AWS/Google keys, `password=…`,
  `user:pass@host`, private-key blocks) and also scrubs **exact registered
  secrets** (a password entered this session, a stored key).
- A structlog processor runs redaction on every event, so logs cannot leak
  credentials even accidentally.
- If a user message looks like a pasted credential, it is **redacted before it is
  stored** and the assistant warns the user; the raw value is never persisted or
  sent to the model.

## Secret storage

Preference order (degrading gracefully):

1. OS keychain (optional `keyring`; unavailable in most containers)
2. **Encrypted local store** (Fernet) at `<data>/secrets/secrets.enc` — the
   portable default
3. Process memory for the current session (passwords that must not persist)

Raw passwords are **never** written to SQLite. The "password in memory" auth
method keeps the password only for the session; "remember" writes it to the
encrypted store. Set `EPMW_SECRET_MASTER_KEY` for a stable key across volume
resets (otherwise a key is generated and stored `0600` on first run).

## No arbitrary execution

- The model selects from **narrow, typed tools** only. There is no generic command
  endpoint and no `subprocess.run(model_output, shell=True)`.
- The EPM Automate runner uses a strict **command allowlist** and subprocess
  **argument arrays** (never a shell string).
- Every argument that reaches the connector is validated: identifiers reject shell
  metacharacters and `..`; filenames reject path separators/traversal; URLs must be
  http(s); timeouts are bounded.
- Package building refuses to include secret-like keys; `.epwcontext` export
  asserts no `password`/`token`/`apikey`/`cookie`/`authorization` keys are present.

## Approval & production safeguards

- Any Oracle-modifying action requires an explicit approval card stating the
  environment, DEV/TEST/PROD classification, application, artifact, operation,
  overwrite/backup status, validation status, and context freshness.
- A previous vague message is never treated as standing permission.
- **Production** shows a persistent high-visibility PROD badge and requires typing
  an exact confirmation phrase (the form name), passing validation, matching
  context, and records an audit event. A plain "confirm deploy" will **not** deploy
  to production (enforced and tested in
  `tests/test_orchestrator.py::test_production_safeguard_requires_confirmation_phrase`).

## Redaction self-test

The Diagnostics endpoint runs a redaction self-test on every call and reports
`redactionHealthy`. The downloadable diagnostics bundle is itself passed through
the redactor before download.

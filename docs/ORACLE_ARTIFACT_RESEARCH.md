# Oracle artifact research & the deployment honesty policy

EPM Wizard does **not** guess the exact Oracle Cloud form-package representation,
and it does **not** claim automated form deployment to a live tenant works until
that has been validated against a development tenant.

## Current status

| Capability | Demo Mode | Live tenant (Oracle REST) |
|---|---|---|
| List applications / cubes / dimensions | ✅ fixtures | ✅ documented Planning REST |
| Search members | ✅ | ⚠️ where the API exposes members |
| List forms / rules / variables | ✅ | ⚠️ rules & vars via REST; forms via Migration |
| Run a business rule + poll job | ✅ simulated | ✅ documented REST jobs |
| Build package / preview / validate | ✅ deterministic | ✅ deterministic (local) |
| **Import / deploy a form** | ✅ simulated + verified | 🚫 `not_supported` until validated |
| Verify a deployed form | ✅ | 🚫 until deployment is validated |

The `OracleRestConnector` raises a clear `not_supported` error (with guidance) for
upload/import on a live tenant. This is deliberate: a deployment is only reported
as **verified** after the artifact is confirmed to exist — never because an import
command exited 0.

## The workflow to enable validated deployment

Follow this against a **development** tenant before flipping the
`realOracleDeployment` feature flag:

1. Create a small test form manually in a development environment.
2. Export only that form through Oracle Migration (LCM).
3. Download the package; inspect its directory structure, manifests, and artifact
   files.
4. Sanitize confidential values; save sanitized fixtures under
   `backend/fixtures/` (never commit real tenant data or secrets).
5. Build a parser: package → `FormSpecification`.
6. Re-render without changes; compare packages (should be byte-identical modulo
   allowed timestamps/IDs).
7. Change one controlled property; repackage; import into development.
8. Verify the result via the connector's `verify_form`.
9. Document supported vs unsupported fields.

EPM Wizard already implements the deterministic half of this loop (render → parse
→ re-render → compare, all reproducible). What remains is mapping EPM Wizard's
normalized form XML to Oracle's exact Migration package layout, which requires a
real development tenant to observe.

## Normalized form XML

`app/artifacts/renderer.py` emits EPM Wizard's **normalized** form XML (built with
ElementTree, stable attribute order). `app/artifacts/parser.py` round-trips it
exactly (covered by `tests/test_artifacts.py::test_xml_roundtrip_is_lossless`).
This is *not* a claim about Oracle's Cloud package layout — it is the canonical
interchange format the documented Migration workflow converts.

## No undocumented endpoints

Undocumented browser endpoints are not used. Prefer documented Oracle mechanisms
(Planning REST, Migration/EPM Automate). Any experimental path must sit behind an
explicit feature flag and be clearly labelled unsupported.

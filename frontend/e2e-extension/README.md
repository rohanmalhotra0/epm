# Installed extension E2E

This suite launches Playwright's bundled Chromium with the repository's
`extension/` directory loaded as an unpacked MV3 extension. It does not mock the
Chrome extension APIs.

```bash
npx playwright install chromium
npm run e2e:extension
```

Use `npm run e2e:extension:headed` to watch the browser. The suite derives the
extension ID from the real MV3 service worker, serves an isolated Oracle-like
fixture, and supplies a local SSE backend. No Docker stack or external account is
required.

The tests intentionally run with one worker because Chrome persistent profiles
and the local mock's action sequence are stateful within each test.

Playwright cannot click Chrome's own toolbar to create an `activeTab` grant. The
fixture therefore loads a temporary copy of the unpacked extension with only the
isolated fixture origin pre-granted. The checked-in manifest's required
`debugger` permission is left unchanged, and canvas control is enabled through
the same side-panel toggle as production. The agent content script is still
absent until the test sends the same user-triggered Start command as the side
panel.

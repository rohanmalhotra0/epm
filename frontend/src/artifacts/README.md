# Artifacts panel (drop-in module)

Claude-style **artifacts panel** for EPM Wizard forms & reports. Self-contained
and namespaced (`.epmw-*` CSS, global zustand store) so it drops into the app
shell without collisions. **Opt-in**: the panel starts closed and only opens when
the user clicks a toggle or "Open in panel" — it never auto-opens when an
artifact streams into chat (this is the behaviour the request asked for).

Built against the generated types in `../schemas/types.ts` and the backend
endpoints in `backend/app/api/routes_reports.py` (already implemented + tested).

## Files

| File | Role |
|---|---|
| `store.ts` | zustand store: open/closed, active tab, current artifact, projectId |
| `api.ts` | typed client: `promptEdit`, `reportPreview`, `formPreview`, `reportRender`, `reportDownload` |
| `ArtifactsPanel.tsx` | the panel shell: header, View/Edit tabs, Download, close |
| `ReportView.tsx` | Oracle-EPM report grid + **per-cell & per-table inline prompts** |
| `FormView.tsx` | form structural preview (POV/Pages bar + grid) |
| `EditTab.tsx` | whole-artifact prompt box + quick hints + raw spec |
| `blocks.tsx` | `ArtifactBlock` (inline chat card + "Open in panel") and `ArtifactToggle` (top-right button) |
| `artifacts.css` | Carbon-aligned styles, light/dark |

## Two integration seams (all you need to wire)

### 1. Render artifact blocks in your ChatBlock switch

```tsx
import { ArtifactBlock, isArtifactBlock } from "./artifacts/blocks";

// inside your block renderer:
if (isArtifactBlock(block.type)) {
  return <ArtifactBlock block={block} messageId={message.id} />;
}
```

Handles `reportSpecification`, `reportPreview`, `formSpecification`, `formPreview`.
`*Specification` blocks carry an editable `spec` (+ optional `preview`) and get an
**Open in panel** button; `*Preview` blocks render a compact summary card.

### 2. Mount the panel + the top-right toggle in the chat layout

```tsx
import "./artifacts/artifacts.css";
import { ArtifactsPanel } from "./artifacts/ArtifactsPanel";
import { ArtifactToggle } from "./artifacts/blocks";
import { useArtifacts } from "./artifacts/store";

function ChatScreen() {
  const setProjectId = useArtifacts((s) => s.setProjectId);
  useEffect(() => setProjectId(activeProjectId), [activeProjectId]); // optional; falls back to default project

  return (
    <div className="chat-layout" style={{ display: "flex", height: "100%" }}>
      <div className="chat-column">
        <header className="chat-header">
          {/* ...existing header... */}
          <ArtifactToggle />           {/* top-right, like Claude */}
        </header>
        {/* ...messages + composer... */}
      </div>
      <ArtifactsPanel />                {/* renders only when open */}
    </div>
  );
}
```

`ArtifactToggle` shows only once an artifact has been opened; clicking it
show/hides the panel for the most-recent artifact. `ArtifactsPanel` returns
`null` while closed, so the flex column collapses automatically.

## Data flow

- **Chat generation** (unchanged): `/reports` or "create a … report" streams
  `reportPreview` + `reportSpecification` blocks over SSE (already wired in the
  reports skill). The user clicks **Open in panel** to inspect/edit.
- **View tab** renders the Oracle-EPM grid from the preview the backend already
  smart-formatted (scale, `$`/`%`, red/parenthesis negatives, conditional
  colours), so it matches the downloaded HTML byte-for-byte.
- **Per-cell / per-table prompts**: click a cell (or the `✎ table` button) →
  inline prompt → `POST /api/artifact/edit` with `scope: "cell" | "table"` →
  fresh preview replaces the grid.
- **Edit tab**: whole-artifact prompt → `scope: "artifact"`. Works for forms too.
- **Download** (reports): `POST /api/reports/download` writes a ZIP artifact
  (HTML + CSV + JSON + Markdown) and the browser fetches
  `/api/artifacts/{id}/download`.

## Endpoints used

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/artifact/edit` | prompt-edit a form/report (artifact/table/cell scope) |
| POST | `/api/reports/preview` | rebuild a report preview from a spec |
| POST | `/api/forms/preview` | rebuild a form preview from a spec |
| POST | `/api/reports/render` | server-rendered `{ html, csv }` |
| POST | `/api/reports/download` | package + persist a report, returns `downloadUrl` |
| GET | `/api/artifacts/{id}/download` | stream the ZIP |

All accept an optional `?projectId=`; without it the backend uses the default
project (Demo Mode).

## Notes / not-yet-done

- This module is **not yet compiled** — it was written while the app shell,
  `tsconfig`, `vite.config` and `node_modules` are being set up in parallel. Once
  the shell exists, `npm i && npm run typecheck` should validate it; expect only
  minor path/lint tweaks.
- A Vite dev proxy (or `VITE_API_BASE`) should point `/api` at the backend
  (`http://localhost:8000`).
- Charts render in the downloaded HTML (inline SVG). The in-panel `ReportView`
  shows the grid; add `grid.chartType`-driven SVG here later if you want the
  chart inside the panel too (the data is already in the preview).

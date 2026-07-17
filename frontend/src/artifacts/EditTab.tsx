// Edit tab: whole-artifact prompt box + the raw spec, matching the wizard's
// vocabulary. For reports this complements the per-cell/table prompts in the
// grid; for forms this is the primary edit surface.

import { useState } from "react";
import { promptEdit } from "./api";
import { useArtifacts } from "./store";

const HINTS: Record<string, string[]> = {
  reportSpec: ["show as millions", "2 decimals", "red negatives", "add a bar chart", "use descendants instead of children", "highlight values over 500000 red"],
  formSpec: ["hide March", "move Entity to POV", "use level-zero descendants of Total Payroll", "only show five members", "attach the IR rule"],
};

export function EditTab() {
  const { artifact, projectId, update } = useArtifacts();
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [log, setLog] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  if (!artifact) return null;

  async function apply(instruction: string) {
    setBusy(true);
    setError(null);
    try {
      const res = await promptEdit(
        { artifactKind: artifact!.kind, scope: "artifact", instruction, spec: artifact!.spec },
        projectId,
      );
      if (res.changed && res.spec) {
        update(res.spec, res.preview ?? undefined);
        setLog((l) => [...(res.changes ?? []).map((c) => `✓ ${c}`), ...l]);
        setText("");
      } else {
        setError(res.questions?.[0] ?? "No change was applied — try rephrasing.");
      }
    } catch (e) {
      setError(String((e as Error).message));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="epmw-edit">
      <div className="epmw-editbar">
        <input
          value={text}
          placeholder="Describe a change…"
          disabled={busy}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter" && text.trim()) apply(text.trim()); }}
        />
        <button disabled={busy || !text.trim()} onClick={() => apply(text.trim())}>{busy ? "…" : "Apply"}</button>
      </div>
      <div className="epmw-hints">
        {(HINTS[artifact.kind] ?? []).map((h) => (
          <button key={h} className="epmw-hint" disabled={busy} onClick={() => apply(h)}>{h}</button>
        ))}
      </div>
      {error && <div className="epmw-error">{error}</div>}
      {log.length > 0 && <ul className="epmw-changelog">{log.map((c, i) => <li key={i}>{c}</li>)}</ul>}
      <pre className="epmw-spec">{JSON.stringify(artifact.spec, null, 2)}</pre>
    </div>
  );
}

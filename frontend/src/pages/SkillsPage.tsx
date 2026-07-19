// Skills catalog: what the assistant can do, with copyable example prompts.

import { useQuery } from "@tanstack/react-query";
import { Tile } from "@carbon/react";
import { api } from "../api/client";
import { toast } from "../store/toast";
import "../styles/feature-pages.css";

interface SkillInfo {
  name: string;
  title: string;
  description: string;
  examples: string[];
}

async function copyText(text: string): Promise<void> {
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(text);
    return;
  }
  // clipboard API unavailable (http:// origin) — legacy fallback
  const ta = document.createElement("textarea");
  ta.value = text;
  document.body.appendChild(ta);
  ta.select();
  document.execCommand("copy");
  ta.remove();
}

export function SkillsPage() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["skillCatalog"],
    queryFn: () => api<{ skills: SkillInfo[] }>("/api/meta/skills"),
  });
  const skills = data?.skills ?? [];

  const copyExample = async (text: string) => {
    try {
      await copyText(text);
      toast.success("Copied — paste it in the chat", text);
    } catch {
      toast.error("Could not copy to clipboard");
    }
  };

  return (
    <div className="page">
      <h2>Skills</h2>
      <div className="page-sub">
        Everything the assistant can do for you. Click an example prompt to copy it, then paste it in the chat.
      </div>
      {isLoading && <div style={{ color: "var(--cds-text-secondary, #8d8d8d)", fontSize: 13 }}>Loading skills…</div>}
      {error != null && (
        <div style={{ color: "var(--cds-support-error, #fa4d56)", fontSize: 13 }}>
          Could not load the skill catalog: {(error as Error).message}
        </div>
      )}
      <div className="skills-grid">
        {skills.map((s) => (
          <Tile key={s.name} className="skill-tile">
            <div className="skill-title">{s.title}</div>
            <div className="skill-desc">{s.description}</div>
            {s.examples.length > 0 && (
              <div className="skill-examples">
                {s.examples.map((ex) => (
                  <button
                    key={ex}
                    type="button"
                    className="skill-example"
                    title="Copy to clipboard"
                    onClick={() => copyExample(ex)}
                  >
                    <span>{ex}</span>
                    <span className="copy-hint">copy</span>
                  </button>
                ))}
              </div>
            )}
          </Tile>
        ))}
      </div>
    </div>
  );
}

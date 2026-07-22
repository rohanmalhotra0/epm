// Command palette (Ctrl/Cmd+K): quick actions when empty, project-wide search
// (conversations / messages / artifacts) once the user starts typing.

import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Add,
  Asleep,
  Chat,
  Compass,
  DataTable,
  Document,
  Help,
  Light,
  Notebook,
  Rocket,
  Search,
  Settings,
  SkillLevel,
} from "@carbon/icons-react";
import { searchProject, type SearchResult } from "../api/search";
import { useUi } from "../store/ui";

interface PaletteItem {
  key: string;
  group: string;
  label: string;
  sublabel?: string;
  icon?: React.ReactNode;
  run: () => void;
}

const GROUP_LABELS: Record<string, string> = {
  actions: "Quick actions",
  conversation: "Conversations",
  message: "Messages",
  artifact: "Artifacts",
};

export function CommandPalette({
  open,
  onClose,
  onNewChat,
}: {
  open: boolean;
  onClose: () => void;
  onNewChat: () => void;
}) {
  const nav = useNavigate();
  const projectId = useUi((s) => s.currentProjectId);
  const theme = useUi((s) => s.theme);
  const toggleTheme = useUi((s) => s.toggleTheme);

  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [sel, setSel] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const seqRef = useRef(0);

  // Reset on open.
  useEffect(() => {
    if (open) {
      setQuery("");
      setResults([]);
      setSel(0);
      setLoading(false);
      // Focus after the overlay mounts.
      setTimeout(() => inputRef.current?.focus(), 0);
    }
  }, [open]);

  // Debounced search.
  useEffect(() => {
    if (!open) return;
    const q = query.trim();
    if (!q || !projectId) {
      setResults([]);
      setLoading(false);
      return;
    }
    setLoading(true);
    const seq = ++seqRef.current;
    const t = setTimeout(() => {
      searchProject(projectId, q, 20)
        .then((r) => {
          if (seqRef.current !== seq) return;
          setResults(r.results || []);
          setSel(0);
          setLoading(false);
        })
        .catch(() => {
          if (seqRef.current !== seq) return;
          setResults([]);
          setLoading(false);
        });
    }, 200);
    return () => clearTimeout(t);
  }, [query, projectId, open]);

  const goto = (path: string) => {
    nav(path);
    onClose();
  };

  const items: PaletteItem[] = useMemo(() => {
    if (!query.trim()) {
      return [
        { key: "new-chat", group: "actions", label: "New chat", icon: <Add size={16} />, run: onNewChat },
        { key: "contexts", group: "actions", label: "Contexts", icon: <Notebook size={16} />, run: () => goto("/contexts") },
        { key: "artifacts", group: "actions", label: "Artifacts", icon: <Document size={16} />, run: () => goto("/artifacts") },
        { key: "deployments", group: "actions", label: "Deployments", icon: <Rocket size={16} />, run: () => goto("/deployments") },
        { key: "skills", group: "actions", label: "Skills", icon: <SkillLevel size={16} />, run: () => goto("/skills") },
        { key: "explorer", group: "actions", label: "Explorer", icon: <Compass size={16} />, run: () => goto("/explorer") },
        { key: "data", group: "actions", label: "Data", icon: <DataTable size={16} />, run: () => goto("/data") },
        { key: "guide", group: "actions", label: "Guide", icon: <Help size={16} />, run: () => goto("/guide") },
        { key: "settings", group: "actions", label: "Settings", icon: <Settings size={16} />, run: () => goto("/settings") },
        {
          key: "toggle-theme",
          group: "actions",
          label: theme === "g100" ? "Toggle theme (switch to light)" : "Toggle theme (switch to dark)",
          icon: theme === "g100" ? <Light size={16} /> : <Asleep size={16} />,
          run: () => {
            toggleTheme();
            onClose();
          },
        },
      ];
    }
    return results.map((r) => ({
      key: `${r.type}-${r.id}`,
      group: r.type,
      label: r.title || "(untitled)",
      sublabel: r.snippet,
      icon: r.type === "conversation" ? <Chat size={16} /> : r.type === "artifact" ? <Document size={16} /> : <Search size={16} />,
      run: () => {
        if (r.type === "conversation") goto(`/c/${r.id}`);
        else if (r.type === "message") goto(`/c/${r.conversationId}`);
        else goto("/artifacts");
      },
    }));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [query, results, theme]);

  // Keep the selected row visible.
  useEffect(() => {
    const el = listRef.current?.querySelector(".cmdk-item.active");
    el?.scrollIntoView?.({ block: "nearest" });
  }, [sel, items.length]);

  if (!open) return null;

  const onKey = (e: React.KeyboardEvent) => {
    if (e.key === "Escape") {
      e.preventDefault();
      onClose();
      return;
    }
    if (e.key === "ArrowDown") {
      e.preventDefault();
      if (items.length) setSel((i) => (i + 1) % items.length);
      return;
    }
    if (e.key === "ArrowUp") {
      e.preventDefault();
      if (items.length) setSel((i) => (i - 1 + items.length) % items.length);
      return;
    }
    if (e.key === "Enter") {
      e.preventDefault();
      items[sel]?.run();
    }
  };

  // Group items (in first-seen order) for rendering; selection index stays flat.
  const groups: Array<{ group: string; items: Array<{ item: PaletteItem; flat: number }> }> = [];
  items.forEach((item, flat) => {
    const last = groups[groups.length - 1];
    if (last && last.group === item.group) last.items.push({ item, flat });
    else groups.push({ group: item.group, items: [{ item, flat }] });
  });

  return (
    <div className="cmdk-overlay" onMouseDown={onClose}>
      <div className="cmdk" role="dialog" aria-modal="true" aria-label="Command palette" onMouseDown={(e) => e.stopPropagation()}>
        <div className="cmdk-input-row">
          <Search size={16} />
          <input
            ref={inputRef}
            value={query}
            placeholder="Search conversations, messages, artifacts…"
            aria-label="Command palette search"
            onChange={(e) => {
              setQuery(e.target.value);
              setSel(0);
            }}
            onKeyDown={onKey}
          />
          {loading && <span className="spinner" aria-label="Searching" />}
        </div>
        <div className="cmdk-list" ref={listRef}>
          {groups.map((g) => (
            <div key={g.group}>
              <div className="cmdk-group-label">{GROUP_LABELS[g.group] || g.group}</div>
              {g.items.map(({ item, flat }) => (
                <div
                  key={item.key}
                  className={`cmdk-item ${flat === sel ? "active" : ""}`}
                  onMouseEnter={() => setSel(flat)}
                  onClick={() => item.run()}
                >
                  <span className="ic">{item.icon}</span>
                  <span className="lbl">{item.label}</span>
                  {item.sublabel && <span className="sub">{item.sublabel}</span>}
                </div>
              ))}
            </div>
          ))}
          {query.trim() && !loading && items.length === 0 && <div className="cmdk-empty">No results for “{query.trim()}”</div>}
        </div>
        <div className="cmdk-foot">
          <span>
            <kbd>↑</kbd>
            <kbd>↓</kbd> navigate
          </span>
          <span>
            <kbd>Enter</kbd> open
          </span>
          <span>
            <kbd>Esc</kbd> close
          </span>
        </div>
      </div>
    </div>
  );
}

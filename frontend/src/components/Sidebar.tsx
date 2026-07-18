import { useState } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";
import {
  Add,
  Search,
  Chat,
  Folder,
  DataTable,
  Rocket,
  Settings,
  Information,
  Pin,
  PinFilled,
  TrashCan,
} from "@carbon/icons-react";
import { useConversations, useCreateConversation, useDeleteConversation, useUpdateConversation } from "../api/hooks";
import { useUi } from "../store/ui";

const NAV = [
  { to: "/contexts", label: "Contexts", icon: DataTable },
  { to: "/artifacts", label: "Artifacts", icon: Folder },
  { to: "/deployments", label: "Deployments", icon: Rocket },
  { to: "/settings", label: "Settings", icon: Settings },
  { to: "/about", label: "About", icon: Information },
];

export function Sidebar() {
  const projectId = useUi((s) => s.currentProjectId);
  const collapsed = useUi((s) => s.sidebarCollapsed);
  const [search, setSearch] = useState("");
  const { data: conversations = [] } = useConversations(projectId ?? undefined, search);
  const create = useCreateConversation(projectId ?? undefined);
  const del = useDeleteConversation(projectId ?? undefined);
  const update = useUpdateConversation(projectId ?? undefined);
  const nav = useNavigate();
  const { id } = useParams();
  const loc = useLocation();

  const newChat = async () => {
    const conv = await create.mutateAsync();
    nav(`/c/${conv.id}`);
  };

  if (collapsed) return null;

  return (
    <aside className="epmw-sidebar">
      <div className="sidebar-section">
        <button className="conv-item" style={{ border: "1px solid var(--cds-border-subtle,#393939)", fontWeight: 600 }} onClick={newChat}>
          <Add size={16} /> New chat
        </button>
        <div style={{ position: "relative", marginTop: 8 }}>
          <Search size={14} style={{ position: "absolute", left: 8, top: 9, color: "#8d8d8d" }} />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search chats"
            style={{ width: "100%", padding: "6px 8px 6px 28px", background: "var(--cds-field,#262626)", color: "inherit", border: "1px solid var(--cds-border-subtle,#393939)", fontSize: 12 }}
          />
        </div>
      </div>
      <div className="conv-list">
        {conversations.map((c) => (
          <div key={c.id} className={`conv-item ${id === c.id ? "active" : ""}`} onClick={() => nav(`/c/${c.id}`)}>
            <Chat size={14} />
            <span className="title">{c.title}</span>
            <span
              onClick={(e) => {
                e.stopPropagation();
                update.mutate({ id: c.id, pinned: !c.pinned });
              }}
              title="Pin"
            >
              {c.pinned ? <PinFilled size={13} /> : <Pin size={13} />}
            </span>
            <span
              onClick={(e) => {
                e.stopPropagation();
                if (confirm(`Delete "${c.title}"?`)) del.mutate(c.id);
              }}
              title="Delete"
            >
              <TrashCan size={13} />
            </span>
          </div>
        ))}
        {conversations.length === 0 && <div style={{ fontSize: 12, color: "#8d8d8d", padding: 12 }}>No chats yet.</div>}
      </div>
      <nav className="sidebar-nav">
        {NAV.map((n) => (
          <Link key={n.to} to={n.to} className={`nav-link ${loc.pathname === n.to ? "active" : ""}`}>
            <n.icon size={16} /> {n.label}
          </Link>
        ))}
      </nav>
    </aside>
  );
}

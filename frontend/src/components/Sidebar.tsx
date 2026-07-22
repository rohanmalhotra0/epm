import { useState } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";
import { Modal, OverflowMenu, OverflowMenuItem, TextInput } from "@carbon/react";
import {
  Add,
  Search,
  Bot,
  Chat,
  ChevronDown,
  ChevronRight,
  DataBase,
  DataTable,
  Folder,
  Help,
  Rocket,
  Settings,
  Information,
  PinFilled,
} from "@carbon/icons-react";
import {
  useArchivedConversations,
  useConversations,
  useCreateConversation,
  useDeleteConversation,
  useUpdateConversation,
} from "../api/hooks";
import { useUi } from "../store/ui";
import { toast } from "../store/toast";
import type { ConversationOut } from "../schemas/types";

const NAV = [
  { to: "/contexts", label: "Contexts", icon: DataTable },
  { to: "/artifacts", label: "Artifacts", icon: Folder },
  { to: "/deployments", label: "Deployments", icon: Rocket },
  { to: "/data", label: "Data", icon: DataBase },
  { to: "/agent", label: "Browser Agent", icon: Bot },
  { to: "/guide", label: "Guide", icon: Help },
  { to: "/settings", label: "Settings", icon: Settings },
  { to: "/about", label: "About", icon: Information },
];

/** Pinned first, then most recent — mirrors the backend ordering. */
function sortConversations(list: ConversationOut[]): ConversationOut[] {
  return [...list].sort((a, b) => {
    const pin = Number(b.pinned ?? false) - Number(a.pinned ?? false);
    if (pin !== 0) return pin;
    const ta = a.lastMessageAt ?? a.updatedAt;
    const tb = b.lastMessageAt ?? b.updatedAt;
    return tb.localeCompare(ta);
  });
}

export function Sidebar() {
  const projectId = useUi((s) => s.currentProjectId);
  const collapsed = useUi((s) => s.sidebarCollapsed);
  const [search, setSearch] = useState("");
  const [showArchived, setShowArchived] = useState(false);
  const [renameTarget, setRenameTarget] = useState<ConversationOut | null>(null);
  const [renameValue, setRenameValue] = useState("");
  const [deleteTarget, setDeleteTarget] = useState<ConversationOut | null>(null);
  const { data: conversations = [] } = useConversations(projectId ?? undefined, search);
  const { data: archived = [] } = useArchivedConversations(projectId ?? undefined, showArchived);
  const create = useCreateConversation(projectId ?? undefined);
  const del = useDeleteConversation(projectId ?? undefined);
  const update = useUpdateConversation(projectId ?? undefined);
  const nav = useNavigate();
  const { id } = useParams();
  const loc = useLocation();

  const sorted = sortConversations(conversations);

  const newChat = async () => {
    const conv = await create.mutateAsync();
    nav(`/c/${conv.id}`);
  };

  const openRename = (c: ConversationOut) => {
    setRenameValue(c.title);
    setRenameTarget(c);
  };

  const submitRename = () => {
    const title = renameValue.trim();
    if (!renameTarget || !title) return;
    update.mutate(
      { id: renameTarget.id, title },
      { onSuccess: () => toast.success("Conversation renamed", title) },
    );
    setRenameTarget(null);
  };

  const togglePin = (c: ConversationOut) => {
    update.mutate(
      { id: c.id, pinned: !c.pinned },
      { onSuccess: () => toast.success(c.pinned ? "Conversation unpinned" : "Conversation pinned", c.title) },
    );
  };

  const toggleArchive = (c: ConversationOut) => {
    update.mutate(
      { id: c.id, archived: !c.archived },
      { onSuccess: () => toast.success(c.archived ? "Conversation restored" : "Conversation archived", c.title) },
    );
  };

  const confirmDelete = () => {
    const target = deleteTarget;
    if (!target) return;
    setDeleteTarget(null);
    // If deleting the currently viewed chat, navigate away immediately to avoid
    // showing stale content while the deletion completes.
    if (id === target.id) {
      const remaining = sorted.filter((c) => c.id !== target.id);
      nav(remaining.length > 0 ? `/c/${remaining[0].id}` : "/", { replace: true });
    }
    del
      .mutateAsync(target.id)
      .then(() => {
        toast.success("Conversation deleted", target.title);
      })
      .catch(() => {
        /* error toast raised by the hook */
      });
  };

  const renderRow = (c: ConversationOut) => (
    <div key={c.id} className={`conv-item ${id === c.id ? "active" : ""}`} onClick={() => nav(`/c/${c.id}`)}>
      <Chat size={14} />
      <span className="title">{c.title}</span>
      {c.pinned && <PinFilled size={13} aria-label="Pinned" />}
      <span onClick={(e) => e.stopPropagation()} style={{ marginLeft: "auto" }}>
        <OverflowMenu size="sm" flipped iconDescription={`Options for ${c.title}`}>
          <OverflowMenuItem itemText="Rename" onClick={() => openRename(c)} />
          <OverflowMenuItem itemText={c.pinned ? "Unpin" : "Pin"} onClick={() => togglePin(c)} />
          <OverflowMenuItem itemText={c.archived ? "Unarchive" : "Archive"} onClick={() => toggleArchive(c)} />
          <OverflowMenuItem hasDivider isDelete itemText="Delete" onClick={() => setDeleteTarget(c)} />
        </OverflowMenu>
      </span>
    </div>
  );

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
        {sorted.map(renderRow)}
        {sorted.length === 0 && <div style={{ fontSize: 12, color: "#8d8d8d", padding: 12 }}>No chats yet.</div>}
      </div>
      <div style={{ borderTop: "1px solid var(--cds-border-subtle,#393939)", padding: "4px 8px" }}>
        <button
          className="conv-item"
          style={{ width: "100%", fontSize: 12, color: "var(--cds-text-secondary,#a8a8a8)" }}
          onClick={() => setShowArchived((v) => !v)}
          aria-expanded={showArchived}
        >
          {showArchived ? <ChevronDown size={14} /> : <ChevronRight size={14} />} Archived
        </button>
        {showArchived && (
          <div style={{ maxHeight: 180, overflowY: "auto" }}>
            {archived.map(renderRow)}
            {archived.length === 0 && (
              <div style={{ fontSize: 12, color: "#8d8d8d", padding: "4px 12px 8px" }}>No archived chats.</div>
            )}
          </div>
        )}
      </div>
      <nav className="sidebar-nav">
        {NAV.map((n) => (
          <Link key={n.to} to={n.to} className={`nav-link ${loc.pathname === n.to ? "active" : ""}`}>
            <n.icon size={16} /> {n.label}
          </Link>
        ))}
      </nav>
      {renameTarget && (
        <Modal
          open
          size="xs"
          modalHeading="Rename conversation"
          primaryButtonText="Rename"
          secondaryButtonText="Cancel"
          primaryButtonDisabled={!renameValue.trim()}
          onRequestClose={() => setRenameTarget(null)}
          onRequestSubmit={submitRename}
        >
          <TextInput
            id="rename-conversation-title"
            labelText="Title"
            value={renameValue}
            onChange={(e) => setRenameValue(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") submitRename();
            }}
          />
        </Modal>
      )}
      {deleteTarget && (
        <Modal
          open
          danger
          size="xs"
          modalHeading={`Delete "${deleteTarget.title}"?`}
          modalLabel="Conversations"
          primaryButtonText="Delete"
          secondaryButtonText="Cancel"
          onRequestClose={() => setDeleteTarget(null)}
          onRequestSubmit={confirmDelete}
        >
          <p style={{ fontSize: 13 }}>This permanently deletes the conversation and its messages.</p>
        </Modal>
      )}
    </aside>
  );
}

import { useCallback, useEffect, useRef, useState } from "react";
import { Button } from "@carbon/react";
import { Attachment, Document, Microphone, MicrophoneFilled, SendFilled, StopFilledAlt } from "@carbon/icons-react";
import { useSpeechRecognition } from "../stt/stt";
import {
  ACCEPTED_EXTENSIONS,
  attachmentKindLabel,
  uploadAttachment,
  validateAttachmentFile,
  type AttachmentOut,
} from "../api/attachments";
import { formatBytes } from "../utils/format";
import { toast } from "../store/toast";

const SLASH = [
  { cmd: "/forms", desc: "Build, preview, edit and deploy a data form" },
  { cmd: "/architecture", desc: "Visualize a cube's dimensions" },
  { cmd: "/rules", desc: "Search, explain and run business rules" },
  { cmd: "/run-rule", desc: "Run a business rule" },
  { cmd: "/context", desc: "Learn or refresh the EPM application" },
  { cmd: "/search", desc: "Find members, forms, rules, variables" },
  { cmd: "/explain", desc: "Explain a rule or calculation" },
  { cmd: "/compare", desc: "Compare cubes or context versions" },
  { cmd: "/deploy", desc: "Deploy / verify an artifact" },
  { cmd: "/rollback", desc: "Roll back the last deployment" },
  { cmd: "/help", desc: "What EPM Wizard can do" },
];

/** A file being (or done being) uploaded, shown as a chip above the textarea. */
interface PendingAttachment {
  localId: string;
  filename: string;
  sizeBytes: number;
  uploading: boolean;
  attachment?: AttachmentOut;
}

export function Composer({
  onSend,
  streaming,
  onStop,
  conversationId,
}: {
  onSend: (text: string, attachments?: AttachmentOut[]) => void;
  streaming: boolean;
  onStop: () => void;
  /** Enables file attachments (uploads are scoped to a conversation). */
  conversationId?: string;
}) {
  const [text, setText] = useState("");
  const [menuIdx, setMenuIdx] = useState(0);
  const [pending, setPending] = useState<PendingAttachment[]>([]);
  const [dragOver, setDragOver] = useState(false);
  const dragDepth = useRef(0);
  const ref = useRef<HTMLTextAreaElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const showMenu = text.startsWith("/") && !text.includes(" ");
  const filtered = SLASH.filter((s) => s.cmd.startsWith(text.toLowerCase()));

  // Voice dictation (Web Speech API). Interim results preview in place; final
  // segments accumulate onto whatever was already typed when dictation started.
  const dictationBase = useRef("");
  const { supported: micSupported, listening, toggle } = useSpeechRecognition((t, isFinal) => {
    if (!t) return;
    if (isFinal) {
      dictationBase.current += t + " ";
      setText(dictationBase.current);
    } else {
      setText(dictationBase.current + t);
    }
    if (ref.current) ref.current.focus();
  });
  const toggleMic = () => {
    if (!listening) dictationBase.current = text.trim() ? text.trim() + " " : "";
    toggle();
  };

  useEffect(() => {
    if (ref.current) {
      ref.current.style.height = "auto";
      ref.current.style.height = Math.min(ref.current.scrollHeight, 200) + "px";
    }
  }, [text]);

  // Validate client-side, then upload each accepted file immediately; the chip
  // shows a spinner until the backend replies with the stored attachment.
  const addFiles = useCallback(
    (list: FileList | File[]) => {
      if (!conversationId) return;
      for (const file of Array.from(list)) {
        const reason = validateAttachmentFile(file);
        if (reason) {
          toast.error(`Cannot attach ${file.name}`, reason);
          continue;
        }
        const localId = Math.random().toString(36).slice(2) + Date.now().toString(36);
        setPending((p) => [...p, { localId, filename: file.name, sizeBytes: file.size, uploading: true }]);
        uploadAttachment(conversationId, file)
          .then((att) =>
            setPending((p) => p.map((x) => (x.localId === localId ? { ...x, uploading: false, attachment: att } : x))),
          )
          .catch((e: Error) => {
            toast.error(`Upload failed — ${file.name}`, e.message);
            setPending((p) => p.filter((x) => x.localId !== localId));
          });
      }
    },
    [conversationId],
  );

  // Drag-and-drop anywhere over the chat area/composer. Document-level listeners
  // (with a depth counter — dragenter/leave fire per nested element) so a file
  // dragged over the message list is caught too, not just the textarea.
  useEffect(() => {
    if (!conversationId) return;
    const hasFiles = (e: DragEvent) => Array.from(e.dataTransfer?.types || []).includes("Files");
    const onEnter = (e: DragEvent) => {
      if (!hasFiles(e)) return;
      e.preventDefault();
      dragDepth.current += 1;
      setDragOver(true);
    };
    const onOver = (e: DragEvent) => {
      if (hasFiles(e)) e.preventDefault();
    };
    const onLeave = (e: DragEvent) => {
      if (!hasFiles(e)) return;
      dragDepth.current = Math.max(0, dragDepth.current - 1);
      if (dragDepth.current === 0) setDragOver(false);
    };
    const onDrop = (e: DragEvent) => {
      if (!hasFiles(e)) return;
      e.preventDefault();
      dragDepth.current = 0;
      setDragOver(false);
      if (e.dataTransfer?.files?.length) addFiles(e.dataTransfer.files);
    };
    document.addEventListener("dragenter", onEnter);
    document.addEventListener("dragover", onOver);
    document.addEventListener("dragleave", onLeave);
    document.addEventListener("drop", onDrop);
    return () => {
      document.removeEventListener("dragenter", onEnter);
      document.removeEventListener("dragover", onOver);
      document.removeEventListener("dragleave", onLeave);
      document.removeEventListener("drop", onDrop);
    };
  }, [conversationId, addFiles]);

  const ready = pending.filter((p) => p.attachment).map((p) => p.attachment!);
  const uploading = pending.some((p) => p.uploading);
  const activeSlashId = showMenu && filtered.length ? `slash-command-${menuIdx}` : undefined;

  const submit = () => {
    const t = text.trim();
    if (streaming || uploading) return;
    if (!t && ready.length === 0) return;
    // Arity matters: plain text sends keep the original single-arg call shape.
    if (ready.length) onSend(t || "Analyze the attached file.", ready);
    else onSend(t);
    setText("");
    setPending([]);
  };

  const onKey = (e: React.KeyboardEvent) => {
    if (showMenu && filtered.length) {
      if (e.key === "ArrowDown") {
        e.preventDefault();
        setMenuIdx((i) => (i + 1) % filtered.length);
        return;
      }
      if (e.key === "ArrowUp") {
        e.preventDefault();
        setMenuIdx((i) => (i - 1 + filtered.length) % filtered.length);
        return;
      }
      if (e.key === "Tab" || (e.key === "Enter" && filtered.length)) {
        e.preventDefault();
        setText(filtered[menuIdx].cmd + " ");
        return;
      }
    }
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  };

  return (
    <div className={`composer-wrap ${dragOver ? "drop-active" : ""}`}>
      <div className="composer">
        {showMenu && filtered.length > 0 && (
          <div className="slash-menu" id="slash-command-menu" role="listbox" aria-label="Slash commands">
            {filtered.map((s, i) => (
              <div
                key={s.cmd}
                id={`slash-command-${i}`}
                className={`slash-item ${i === menuIdx ? "active" : ""}`}
                role="option"
                aria-selected={i === menuIdx}
                onMouseDown={(e) => {
                  e.preventDefault();
                  setText(s.cmd + " ");
                  ref.current?.focus();
                }}
              >
                <span className="cmd">{s.cmd}</span> <span className="desc">— {s.desc}</span>
              </div>
            ))}
          </div>
        )}
        {pending.length > 0 && (
          <div className="attach-chips">
            {pending.map((a) => (
              <span className="attach-chip" key={a.localId}>
                {a.uploading ? <div className="spinner" /> : <Document size={14} />}
                <span className="name mono">{a.filename}</span>
                <span className="meta">{formatBytes(a.sizeBytes)}</span>
                {a.attachment && <span className="tag-inline">{attachmentKindLabel(a.attachment.kindGuess)}</span>}
                <button
                  className="attach-remove"
                  aria-label={`Remove ${a.filename}`}
                  title={`Remove ${a.filename}`}
                  onClick={() => setPending((p) => p.filter((x) => x.localId !== a.localId))}
                >
                  ✕
                </button>
              </span>
            ))}
          </div>
        )}
        {dragOver && <div className="drop-overlay">Drop {ACCEPTED_EXTENSIONS.join(" / ")} files to attach</div>}
        <textarea
          ref={ref}
          role="combobox"
          value={text}
          placeholder="Ask EPM Wizard to build, inspect, explain, or run something…"
          onChange={(e) => {
            setText(e.target.value);
            setMenuIdx(0);
          }}
          onKeyDown={onKey}
          aria-label="Message EPM Wizard"
          aria-autocomplete="list"
          aria-controls={showMenu && filtered.length ? "slash-command-menu" : undefined}
          aria-expanded={showMenu && filtered.length > 0}
          aria-activedescendant={activeSlashId}
        />
        <div className="composer-actions">
          {conversationId && (
            <>
              <input
                ref={fileRef}
                type="file"
                multiple
                accept={ACCEPTED_EXTENSIONS.join(",")}
                style={{ display: "none" }}
                aria-label="Attach spreadsheet files"
                onChange={(e) => {
                  if (e.target.files?.length) addFiles(e.target.files);
                  e.target.value = "";
                }}
              />
              <Button
                size="sm"
                kind="ghost"
                hasIconOnly
                iconDescription="Attach files"
                renderIcon={Attachment}
                onClick={() => fileRef.current?.click()}
              />
            </>
          )}
          {micSupported && (
            <Button
              size="sm"
              kind={listening ? "secondary" : "ghost"}
              hasIconOnly
              iconDescription={listening ? "Stop dictation" : "Dictate (voice input)"}
              renderIcon={listening ? MicrophoneFilled : Microphone}
              onClick={toggleMic}
            />
          )}
          {streaming ? (
            <Button size="sm" kind="secondary" hasIconOnly iconDescription="Stop" renderIcon={StopFilledAlt} onClick={onStop} />
          ) : (
            <Button
              size="sm"
              kind="primary"
              hasIconOnly
              iconDescription="Send"
              renderIcon={SendFilled}
              onClick={submit}
              disabled={(!text.trim() && ready.length === 0) || uploading}
            />
          )}
        </div>
      </div>
      <div className="composer-hint">
        {listening ? (
          <span style={{ color: "#fa4d56", display: "flex", alignItems: "center", gap: 6 }}>
            <span className="conn-dot on" style={{ background: "#fa4d56" }} /> Listening… click the mic to stop
          </span>
        ) : (
          <span>Enter to send · Shift+Enter for newline · / for commands · Ctrl+K palette{micSupported ? " · 🎤 to dictate" : ""}</span>
        )}
      </div>
    </div>
  );
}

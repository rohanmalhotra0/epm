import { useEffect, useRef, useState } from "react";
import { Button } from "@carbon/react";
import { SendFilled, StopFilledAlt } from "@carbon/icons-react";

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

export function Composer({
  onSend,
  streaming,
  onStop,
}: {
  onSend: (text: string) => void;
  streaming: boolean;
  onStop: () => void;
}) {
  const [text, setText] = useState("");
  const [menuIdx, setMenuIdx] = useState(0);
  const ref = useRef<HTMLTextAreaElement>(null);
  const showMenu = text.startsWith("/") && !text.includes(" ");
  const filtered = SLASH.filter((s) => s.cmd.startsWith(text.toLowerCase()));

  useEffect(() => {
    if (ref.current) {
      ref.current.style.height = "auto";
      ref.current.style.height = Math.min(ref.current.scrollHeight, 200) + "px";
    }
  }, [text]);

  const submit = () => {
    const t = text.trim();
    if (!t || streaming) return;
    onSend(t);
    setText("");
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
    <div className="composer-wrap">
      <div className="composer">
        {showMenu && filtered.length > 0 && (
          <div className="slash-menu">
            {filtered.map((s, i) => (
              <div
                key={s.cmd}
                className={`slash-item ${i === menuIdx ? "active" : ""}`}
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
        <textarea
          ref={ref}
          value={text}
          placeholder="Ask EPM Wizard to build, inspect, explain, or run something…"
          onChange={(e) => {
            setText(e.target.value);
            setMenuIdx(0);
          }}
          onKeyDown={onKey}
          aria-label="Message EPM Wizard"
        />
        <div className="composer-actions">
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
              disabled={!text.trim()}
            />
          )}
        </div>
      </div>
      <div className="composer-hint">
        <span>Enter to send · Shift+Enter for newline · / for commands</span>
      </div>
    </div>
  );
}

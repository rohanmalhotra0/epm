import { ToastNotification } from "@carbon/react";
import { useToasts } from "../store/toast";

const KIND_MAP = {
  success: "success",
  error: "error",
  info: "info",
  warning: "warning",
} as const;

/** Fixed, stacked toast notifications (bottom-right). Rendered once at app root. */
export function Toaster() {
  const toasts = useToasts((s) => s.toasts);
  const dismiss = useToasts((s) => s.dismiss);

  if (toasts.length === 0) return null;

  return (
    <div
      style={{
        position: "fixed",
        right: 16,
        bottom: 16,
        zIndex: 9000,
        display: "flex",
        flexDirection: "column",
        gap: 8,
        maxWidth: 380,
      }}
      role="status"
      aria-live="polite"
    >
      {toasts.map((t) => (
        <ToastNotification
          key={t.id}
          kind={KIND_MAP[t.kind]}
          title={t.title}
          subtitle={t.subtitle}
          lowContrast
          onClose={() => {
            dismiss(t.id);
            return false;
          }}
          onCloseButtonClick={() => dismiss(t.id)}
          style={{ minWidth: 320 }}
        />
      ))}
    </div>
  );
}

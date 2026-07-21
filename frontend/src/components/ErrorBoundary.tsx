import { Component, type ErrorInfo, type ReactNode } from "react";

interface Props {
  children: ReactNode;
  /** Changing this value resets the boundary (e.g. route pathname), so navigating
   *  away from a crashed page recovers without a full reload. */
  resetKey?: string;
  /** Optional label for the region that failed, shown in the fallback copy. */
  label?: string;
}

interface State {
  error: Error | null;
}

/**
 * Catches render/lifecycle errors in its subtree and shows a recovery card
 * instead of unmounting the whole React tree (which would leave a blank screen
 * that needs a manual reload). Placed around route content so the Header and
 * Sidebar stay usable and the user can navigate elsewhere.
 */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // Surface for diagnostics; the UI already degrades gracefully.
    console.error("ErrorBoundary caught an error", error, info.componentStack);
  }

  componentDidUpdate(prev: Props) {
    if (prev.resetKey !== this.props.resetKey && this.state.error) {
      this.setState({ error: null });
    }
  }

  render() {
    if (this.state.error) {
      return (
        <div className="main-col" style={{ padding: 32 }}>
          <div
            role="alert"
            style={{
              maxWidth: 560,
              margin: "48px auto",
              padding: 24,
              border: "1px solid var(--cds-border-subtle,#393939)",
              background: "var(--cds-layer,#1f1f1f)",
              borderRadius: 4,
            }}
          >
            <h2 style={{ fontSize: 18, marginBottom: 8 }}>
              Something went wrong{this.props.label ? ` in ${this.props.label}` : ""}
            </h2>
            <p style={{ fontSize: 13, color: "var(--cds-text-secondary,#a8a8a8)", lineHeight: 1.6 }}>
              This view hit an unexpected error and stopped rendering. Your data is safe. Try
              switching to another page from the sidebar, or reload the app.
            </p>
            <pre
              style={{
                marginTop: 12,
                padding: 10,
                fontSize: 11,
                color: "#ff8389",
                background: "var(--cds-field,#262626)",
                borderRadius: 3,
                overflowX: "auto",
                whiteSpace: "pre-wrap",
              }}
            >
              {this.state.error.message}
            </pre>
            <div style={{ marginTop: 16, display: "flex", gap: 8 }}>
              <button
                onClick={() => this.setState({ error: null })}
                style={{
                  padding: "8px 14px",
                  background: "#4589ff",
                  color: "#fff",
                  border: "none",
                  borderRadius: 3,
                  cursor: "pointer",
                  fontSize: 13,
                }}
              >
                Try again
              </button>
              <button
                onClick={() => window.location.reload()}
                style={{
                  padding: "8px 14px",
                  background: "transparent",
                  color: "var(--cds-text-primary,#f4f4f4)",
                  border: "1px solid var(--cds-border-subtle,#393939)",
                  borderRadius: 3,
                  cursor: "pointer",
                  fontSize: 13,
                }}
              >
                Reload app
              </button>
            </div>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}

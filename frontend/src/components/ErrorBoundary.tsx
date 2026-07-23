import { Component, type ErrorInfo, type ReactNode } from "react";
import { Button } from "@carbon/react";

interface Props {
  children: ReactNode;
  /** Changing this value resets the boundary (e.g. route pathname), so navigating
   *  away from a crashed page recovers without a full reload. */
  resetKey?: string;
  /** Optional label for the region that failed, shown in the fallback copy. */
  label?: string;
  /** Override the hard reload action (primarily useful for host integrations and tests). */
  onReload?: () => void;
}

interface State {
  error: Error | null;
}

const CHUNK_LOAD_ERROR_PATTERNS = [
  /Loading (?:CSS )?chunk [\w-]+ failed/i,
  /Failed to fetch dynamically imported module/i,
  /error loading dynamically imported module/i,
  /Importing a module script failed/i,
  /Unable to preload CSS/i,
  /Failed to load module script/i,
];

function isChunkLoadError(error: Error): boolean {
  if (error.name === "ChunkLoadError") return true;
  return CHUNK_LOAD_ERROR_PATTERNS.some((pattern) => pattern.test(error.message));
}

/**
 * Catches render/lifecycle errors in its subtree and shows a recovery card
 * instead of unmounting the whole React tree (which would leave a blank screen
 * that needs a manual reload). Placed around route content so the Header and
 * Sidebar stay usable and the user can navigate elsewhere.
 */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  private reload = () => {
    if (this.props.onReload) {
      this.props.onReload();
      return;
    }
    window.location.reload();
  };

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
      const chunkLoadFailed = isChunkLoadError(this.state.error);

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
              {chunkLoadFailed
                ? "Reload to finish updating"
                : `Something went wrong${this.props.label ? ` in ${this.props.label}` : ""}`}
            </h2>
            <p style={{ fontSize: 13, color: "var(--cds-text-secondary,#a8a8a8)", lineHeight: 1.6 }}>
              {chunkLoadFailed
                ? `A required part of ${this.props.label ?? "this view"} could not be loaded. This can happen after an app update or when the connection is interrupted. Reload to fetch the current app and retry.`
                : "This view hit an unexpected error and stopped rendering. Your data is safe. Try switching to another page from the sidebar, or reload the app."}
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
              {chunkLoadFailed ? (
                <Button size="sm" onClick={this.reload}>
                  Reload and retry
                </Button>
              ) : (
                <>
                  <Button size="sm" onClick={() => this.setState({ error: null })}>
                    Try again
                  </Button>
                  <Button size="sm" kind="tertiary" onClick={this.reload}>
                    Reload app
                  </Button>
                </>
              )}
            </div>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}

import { Component, type ErrorInfo, type ReactNode } from "react";
import { reportClientError } from "../lib/errorReporting";

interface Props {
  children: ReactNode;
}

interface State {
  error: Error | null;
}

/** Last-resort catch for render-time crashes anywhere in the tree — without
 * it a single thrown render error unmounts the ENTIRE app to a blank white
 * page with no way back but knowing to hit reload. Class component because
 * error boundaries still have no hook equivalent. Styled with plain inline
 * styles (not Tailwind classes) on purpose: if the crash came from something
 * as early as the CSS/theme layer, the fallback must not depend on it. */
export default class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // eslint-disable-next-line no-console
    console.error("[Sanad] Uncaught render error:", error, info.componentStack);
    reportClientError(error.message, error.stack, "render");
  }

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div
        style={{
          minHeight: "100vh",
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          gap: 12,
          padding: 24,
          textAlign: "center",
          background: "#F7F3EA",
          color: "#1B2A2A",
          fontFamily: "Inter, system-ui, sans-serif",
        }}
      >
        <p style={{ fontSize: 40, margin: 0 }}>سَنَد</p>
        <h1 style={{ fontSize: 18, margin: 0 }}>Something went wrong</h1>
        <p style={{ fontSize: 13, opacity: 0.7, maxWidth: 320, margin: 0 }}>
          The app hit an unexpected error. Your progress is saved to your
          account — reloading is safe.
        </p>
        <button
          onClick={() => window.location.reload()}
          style={{
            marginTop: 8,
            padding: "10px 28px",
            borderRadius: 999,
            border: "none",
            background: "#0E5A4A",
            color: "#fff",
            fontSize: 14,
            fontWeight: 600,
            cursor: "pointer",
          }}
        >
          Reload
        </button>
        <details style={{ marginTop: 16, fontSize: 11, opacity: 0.6, maxWidth: 360 }}>
          <summary style={{ cursor: "pointer" }}>Technical details</summary>
          <pre style={{ whiteSpace: "pre-wrap", textAlign: "left", overflowX: "auto" }}>
            {this.state.error.message}
          </pre>
        </details>
      </div>
    );
  }
}

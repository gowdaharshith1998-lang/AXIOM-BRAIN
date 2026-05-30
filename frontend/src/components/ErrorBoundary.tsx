import { Component } from "react";
import type { ErrorInfo, ReactNode } from "react";

interface ErrorBoundaryProps {
  children: ReactNode;
  /** Optional custom fallback. Falls back to a built-in message if omitted. */
  fallback?: ReactNode;
  /** Short label for the guarded area, used in the default fallback copy. */
  label?: string;
}

interface ErrorBoundaryState {
  hasError: boolean;
}

/**
 * Top-level React error boundary. A render/lifecycle throw inside the wrapped
 * subtree shows a fallback UI instead of a blank white screen, and the rest of
 * the app keeps running when only a subtree (e.g. the 3D Brain) fails.
 */
export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError(): ErrorBoundaryState {
    return { hasError: true };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo): void {
    // Surface for diagnostics. console.* is stripped from production bundles.
    console.error("ErrorBoundary caught an error:", error, errorInfo);
  }

  render(): ReactNode {
    if (this.state.hasError) {
      if (this.props.fallback) {
        return this.props.fallback;
      }
      return (
        <div
          role="alert"
          style={{
            padding: "1.5rem",
            margin: "1rem",
            borderRadius: "8px",
            background: "rgba(127, 29, 29, 0.15)",
            border: "1px solid rgba(248, 113, 113, 0.4)",
            color: "#fca5a5",
            fontFamily: "inherit",
          }}
        >
          <strong>
            Something went wrong{this.props.label ? ` in ${this.props.label}` : ""}.
          </strong>
          <p style={{ marginTop: "0.5rem", opacity: 0.85 }}>
            Try reloading the page. If the problem persists, the rest of the app
            should still be usable.
          </p>
        </div>
      );
    }

    return this.props.children;
  }
}

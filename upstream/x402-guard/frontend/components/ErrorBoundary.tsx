"use client";
import { Component, ReactNode } from "react";

interface Props { children: ReactNode; }
interface State { error: Error | null; }

// Extension errors to silently ignore (MetaMask, OKX wallet, etc.)
const EXTENSION_PATTERNS = [
  "MetaMask", "metamask", "chrome-extension://",
  "moz-extension://", "Failed to connect", "inpage.js",
  "ethereum", "okxwallet",
];

function isExtensionError(err: Error): boolean {
  const msg = err?.message || "";
  const stack = err?.stack || "";
  return EXTENSION_PATTERNS.some(p => msg.includes(p) || stack.includes(p));
}

export default class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    // Silently ignore browser extension errors
    if (isExtensionError(error)) return { error: null };
    return { error };
  }

  componentDidCatch(error: Error) {
    if (isExtensionError(error)) return; // suppress
    console.error("[x402guard] Runtime error:", error);
  }

  render() {
    if (this.state.error) {
      return (
        <div style={{
          display: "flex", alignItems: "center", justifyContent: "center",
          height: "100vh", flexDirection: "column", gap: 12,
          fontFamily: "var(--mono)", background: "var(--bg)", color: "var(--t1)",
        }}>
          <div style={{ fontSize: 10, color: "var(--red)" }}>[!] runtime error</div>
          <div style={{ fontSize: 9, color: "var(--t3)", maxWidth: 400, textAlign: "center" }}>
            {this.state.error.message}
          </div>
          <button onClick={() => this.setState({ error: null })}
            style={{ fontSize: 9, padding: "4px 12px", border: "1px solid var(--border2)",
              borderRadius: "var(--r)", background: "none", color: "var(--t2)",
              cursor: "pointer", fontFamily: "var(--mono)" }}>
            [ retry ]
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}

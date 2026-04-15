"use client";

// Global error handler — catches errors that escape page-level boundaries
// Suppresses browser extension errors (MetaMask, OKX wallet, etc.)

const EXTENSION_MSGS = ["MetaMask", "chrome-extension", "Failed to connect", "inpage.js", "ethereum"];

function isExtensionError(msg: string): boolean {
  return EXTENSION_MSGS.some(p => msg.includes(p));
}

export default function GlobalError({ error, reset }: { error: Error; reset: () => void }) {
  // Suppress extension errors entirely — auto reset
  if (isExtensionError(error.message || "")) {
    reset();
    return null;
  }

  return (
    <html>
      <body style={{ background: "#080808", color: "#f2f2f2", fontFamily: "monospace", display: "flex", alignItems: "center", justifyContent: "center", height: "100vh", flexDirection: "column", gap: 12 }}>
        <div style={{ fontSize: 10, color: "#c94040" }}>[!] runtime error</div>
        <div style={{ fontSize: 9, color: "#888", maxWidth: 400, textAlign: "center" }}>{error.message}</div>
        <button onClick={reset} style={{ fontSize: 9, padding: "4px 12px", border: "1px solid rgba(255,255,255,0.14)", borderRadius: 3, background: "none", color: "#b8b8b8", cursor: "pointer", fontFamily: "monospace" }}>
          [ retry ]
        </button>
      </body>
    </html>
  );
}

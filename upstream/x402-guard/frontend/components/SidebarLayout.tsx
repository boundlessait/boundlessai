"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const CONTRACT = "0xaC4bbC6A7bA52622c1dF942A309CB6D835D363bB";
const EXPLORER = `https://www.oklink.com/x-layer-testnet/address/${CONTRACT}`;

const NAV: { href: string; label: string; badge?: number }[] = [
  { href: "/",         label: "dashboard" },
  { href: "/policy",   label: "policy"    },
  { href: "/insights", label: "insights"  },
  { href: "/alerts",   label: "alerts" },
  { href: "/landing",  label: "about"     },
];

export default function SidebarLayout({ children }: { children: React.ReactNode }) {
  const path = usePathname();

  return (
    <>
      <div className="grid-bg" />
      <aside style={{
        position: "fixed", left: 0, top: 0, bottom: 0, width: 190,
        background: "var(--bg1)", borderRight: "1px solid var(--border)",
        display: "flex", flexDirection: "column", zIndex: 50,
      }}>
        {/* Logo */}
        <div style={{ padding: "18px 16px 14px", borderBottom: "1px solid var(--border)" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 3 }}>
            <span style={{ color: "var(--t2)", fontSize: 18, fontWeight: 400 }}>[</span>
            <span style={{ fontSize: 13, fontWeight: 700, color: "var(--t1)", letterSpacing: ".5px" }}>x402guard</span>
            <span style={{ color: "var(--t2)", fontSize: 18, fontWeight: 400 }}>]</span>
          </div>
          <div style={{ fontSize: 9, color: "var(--t3)", letterSpacing: 1 }}>v1.0.0 — TERMINAL</div>
          <div style={{ fontSize: 9, color: "var(--t3)", letterSpacing: ".8px", textTransform: "uppercase", marginTop: 3 }}>
            AI spending firewall
          </div>
        </div>

        {/* Nav */}
        <nav style={{ flex: 1, padding: "10px 8px", display: "flex", flexDirection: "column", gap: 2 }}>
          {NAV.map(({ href, label, badge }) => {
            const active = href === "/" ? path === "/" : path.startsWith(href);
            return (
              <Link key={href} href={href} style={{
                display: "flex", alignItems: "center", gap: 8,
                padding: "8px 10px", borderRadius: 3,
                fontSize: 11, fontWeight: 400, letterSpacing: ".3px",
                color: active ? "#d4ff00" : "var(--t2)",
                background: active ? "rgba(212,255,0,.06)" : "transparent",
                border: active ? "1px solid rgba(212,255,0,.12)" : "1px solid transparent",
                textDecoration: "none", transition: "all .1s",
              }}>
                <span style={{ color: active ? "#d4ff00" : "var(--t3)", fontSize: 10 }}>
                  {active ? ">> " : "> "}
                </span>
                {label}
                {badge && (
                  <span style={{
                    marginLeft: "auto", fontSize: 9, fontWeight: 700,
                    background: "var(--red-dim)", color: "var(--red)",
                    padding: "1px 5px", borderRadius: 2,
                    border: "1px solid rgba(180,50,50,.2)",
                  }}>{badge}</span>
                )}
              </Link>
            );
          })}
        </nav>

        {/* Footer */}
        <div style={{ padding: "10px 14px", borderTop: "1px solid var(--border)" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 5, marginBottom: 4 }}>
            <div className="dot-live" />
            <span style={{ fontSize: 9, color: "var(--t3)", letterSpacing: ".5px" }}>
              x-layer · testnet · 1952
            </span>
          </div>
          <a href={EXPLORER} target="_blank" rel="noopener noreferrer"
            style={{ fontSize: 9, color: "var(--t3)", letterSpacing: "-.2px", textDecoration: "none" }}>
            GuardLog <span style={{ color: "#888" }}>
              {CONTRACT.slice(0, 6)}…{CONTRACT.slice(-4)}
            </span>
          </a>
        </div>
      </aside>

      <main style={{ marginLeft: 190, minHeight: "100vh", position: "relative", zIndex: 1 }}>
        {children}
      </main>
    </>
  );
}

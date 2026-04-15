"use client";
import { useEffect, useState } from "react";
import Link from "next/link";

export default function LandingPage() {
  const [stats, setStats] = useState<{ tx: number; agents: number; blocked: number; saved: number } | null>(null);

  useEffect(() => {
    // Pull real numbers from API
    Promise.all([
      fetch("/api/dashboard/stats").then(r => r.ok ? r.json() : null).catch(() => null),
      fetch("/api/agents").then(r => r.ok ? r.json() : null).catch(() => null),
    ]).then(([s, agents]) => {
      if (!s && !agents) return;
      setStats({
        tx:      (s?.txApprovedToday ?? 0) + (s?.txFlaggedToday ?? 0) + (s?.txDeniedToday ?? 0),
        agents:  Array.isArray(agents) ? agents.length : (s?.totalAgents ?? 0),
        blocked: s?.txDeniedToday ?? 0,
        saved:   s ? (s.totalSpentToday / 100) : 0,
      });
    });
  }, []);

  return (
    <div style={{ position: "relative", zIndex: 1, fontFamily: "var(--mono)" }}>

      {/* ── Topbar ── */}
      <header style={{
        height: 44, background: "rgba(2,9,2,0.95)", borderBottom: "1px solid var(--border)",
        display: "flex", alignItems: "center", padding: "0 20px", gap: 12,
        position: "sticky", top: 0, zIndex: 40,
      }}>
        <span style={{ fontSize: 11, color: "var(--t2)" }}>
          root/<span style={{ color: "var(--t1)" }}>about</span>
        </span>
        <div style={{ marginLeft: "auto", display: "flex", gap: 8 }}>
          <Link href="/" style={{
            fontSize: 9, padding: "3px 10px", border: "1px solid var(--border2)",
            borderRadius: "var(--r)", color: "var(--t1)", textDecoration: "none",
            fontFamily: "var(--mono)",
          }}>
            [ → dashboard ]
          </Link>
        </div>
      </header>

      <div style={{ padding: "24px 20px", display: "flex", flexDirection: "column", gap: 16 }}>

        {/* ── Hero ── */}
        <div className="panel" style={{ padding: "32px 24px", textAlign: "center" }}>
          <div style={{ fontSize: 9, color: "var(--t3)", letterSpacing: 2, marginBottom: 12, textTransform: "uppercase" }}>
            x402 protocol · x layer testnet · eip155:1952
          </div>
          <h1 style={{ fontSize: "clamp(22px, 4vw, 42px)", fontWeight: 700, letterSpacing: "clamp(2px, 1vw, 6px)",
            lineHeight: 1.15, marginBottom: 20, textTransform: "uppercase", color: "var(--t1)" }}>
            AI BOT<br />
            <span style={{ color: "var(--red)" }}>SPENDING</span><br />
            FIREWALL
          </h1>
          <p style={{ fontSize: 11, color: "var(--t2)", maxWidth: 480, margin: "0 auto 24px", lineHeight: 1.9 }}>
            Guard every AI agent payment before execution. Enforce per-bot spending policies,
            get real-time alerts, and kill rogue bots instantly — all on-chain on X Layer.
          </p>
          <div style={{ display: "flex", gap: 8, justifyContent: "center", flexWrap: "wrap" }}>
            <Link href="/" style={{
              padding: "8px 20px", background: "var(--red)", color: "#fff",
              fontFamily: "var(--mono)", fontSize: 10, fontWeight: 700, letterSpacing: 1,
              textDecoration: "none", borderRadius: "var(--r)", textTransform: "uppercase",
            }}>[ launch dashboard ]</Link>
            <Link href="/policy" style={{
              padding: "8px 20px", background: "none", border: "1px solid var(--border2)",
              color: "var(--t1)", fontFamily: "var(--mono)", fontSize: 10,
              textDecoration: "none", borderRadius: "var(--r)",
            }}>[ edit policies ]</Link>
          </div>
          <div style={{ marginTop: 24, fontSize: 10, color: "var(--t3)" }}>
            {">"} guard.check(agent-beta, $26.00)
            <span style={{ animation: "termBlink 1s step-end infinite", color: "var(--red)", marginLeft: 6 }}>
              ▮ BLOCKED
            </span>
          </div>
        </div>

        {/* ── Live stats from real data ── */}
        <div className="panel">
          <div className="panel-head">
            <div className="panel-head-dot" />live stats — today
            <span style={{ marginLeft: "auto", fontSize: 9, color: "var(--t3)" }}>
              {stats ? "real data" : "loading..."}
            </span>
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)" }}>
            {[
              { label: "transactions guarded", val: stats?.tx ?? "—",      color: "var(--t1)"    },
              { label: "bots protected",        val: stats?.agents ?? "—",  color: "var(--t1)"    },
              { label: "blocked today",         val: stats?.blocked ?? "—", color: "var(--red)"   },
              { label: "spent today (USDC)",    val: stats ? `$${stats.saved.toFixed(2)}` : "—", color: "var(--amber)" },
            ].map(({ label, val, color }, i) => (
              <div key={label} style={{ padding: "16px 14px", borderRight: i < 3 ? "1px solid var(--border)" : "none" }}>
                <div style={{ fontFamily: "var(--mono)", fontSize: 24, fontWeight: 700, color, marginBottom: 4 }}>{val}</div>
                <div style={{ fontSize: 8, color: "var(--t3)", textTransform: "uppercase", letterSpacing: 1 }}>{label}</div>
              </div>
            ))}
          </div>
        </div>

        {/* ── Problem / Solution ── */}
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
          <div className="panel">
            <div className="panel-head"><div className="panel-head-dot" />problem</div>
            <div style={{ padding: "10px 14px", display: "flex", flexDirection: "column", gap: 0 }}>
              {[
                { sym: "[!]", title: "bots overspend",    desc: "No native spend cap. A runaway bot can drain your wallet in minutes." },
                { sym: "[?]", title: "zero visibility",   desc: "Can't see which bot spent what, when, or why. No audit trail." },
                { sym: "[x]", title: "no kill switch",    desc: "By the time you notice, damage is done. No way to stop bots instantly." },
              ].map(({ sym, title, desc }) => (
                <div key={title} style={{ padding: "10px 0", borderBottom: "1px solid var(--border)" }}>
                  <div style={{ display: "flex", gap: 8, alignItems: "baseline", marginBottom: 4 }}>
                    <span style={{ fontSize: 9, color: "var(--red)", fontWeight: 700, flexShrink: 0 }}>{sym}</span>
                    <span style={{ fontSize: 10, fontWeight: 700, color: "var(--t1)", textTransform: "uppercase", letterSpacing: 0.5 }}>{title}</span>
                  </div>
                  <div style={{ fontSize: 9, color: "var(--t2)", lineHeight: 1.7, paddingLeft: 20 }}>{desc}</div>
                </div>
              ))}
            </div>
          </div>

          <div className="panel">
            <div className="panel-head"><div className="panel-head-dot" />solution — 3 layers</div>
            <div style={{ padding: "10px 14px", display: "flex", flexDirection: "column", gap: 0 }}>
              {[
                { step: "01", title: "guard check",    desc: "Every payment hits guard before execution. Policy evaluation in milliseconds.", color: "var(--t2)" },
                { step: "02", title: "policy engine",  desc: "Per-agent daily limits, per-tx caps, domain allowlists. Approve, alert, or block.", color: "var(--amber)" },
                { step: "03", title: "kill switch",    desc: "One click kills all bots instantly. Onchain audit log on X Layer testnet.", color: "var(--red)" },
              ].map(({ step, title, desc, color }) => (
                <div key={step} style={{ padding: "10px 0", borderBottom: "1px solid var(--border)" }}>
                  <div style={{ display: "flex", gap: 8, alignItems: "baseline", marginBottom: 4 }}>
                    <span style={{ fontSize: 9, color: "var(--t3)", fontFamily: "var(--mono)", flexShrink: 0 }}>{step}</span>
                    <span style={{ fontSize: 10, fontWeight: 700, color, textTransform: "uppercase", letterSpacing: 0.5 }}>{title}</span>
                  </div>
                  <div style={{ fontSize: 9, color: "var(--t2)", lineHeight: 1.7, paddingLeft: 20 }}>{desc}</div>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* ── Features ── */}
        <div className="panel">
          <div className="panel-head"><div className="panel-head-dot" />features</div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(2, 1fr)" }}>
            {[
              { sym: "⚡", title: "Real-time Guard",      desc: "Live transaction feed. Every guard decision visible as it happens, with outcome and reason." },
              { sym: "◈",  title: "Per-Agent Policies",   desc: "Set daily budgets and per-tx caps per bot. Sniper, arb, prediction, sentiment — all different limits." },
              { sym: "✕",  title: "Kill Switch",          desc: "Emergency panel to kill all agents or individual bots. One click, immediate effect." },
              { sym: "⛓",  title: "Onchain Audit",        desc: "GuardLog contract on X Layer testnet. Every block and kill event written on-chain permanently." },
              { sym: "🤖", title: "OKX Agentic Wallet",   desc: "Integrates with OKX OnchainOS. Guard wraps the wallet — agents spend, guard enforces limits." },
              { sym: "🔔", title: "Smart Alerts",         desc: "Soft alerts at 80% limit, auto-pause at 95%, hard block at 100%. Telegram + Discord notifications." },
            ].map(({ sym, title, desc }, i) => (
              <div key={title} style={{
                padding: "14px 14px", borderBottom: i < 4 ? "1px solid var(--border)" : "none",
                borderRight: i % 2 === 0 ? "1px solid var(--border)" : "none",
              }}>
                <div style={{ display: "flex", gap: 8, marginBottom: 6, alignItems: "center" }}>
                  <span style={{ fontSize: 14 }}>{sym}</span>
                  <span style={{ fontSize: 10, fontWeight: 700, color: "var(--t1)", letterSpacing: 0.5 }}>{title}</span>
                </div>
                <div style={{ fontSize: 9, color: "var(--t2)", lineHeight: 1.7 }}>{desc}</div>
              </div>
            ))}
          </div>
        </div>

        {/* ── Tech / Contract ── */}
        <div className="panel">
          <div className="panel-head"><div className="panel-head-dot" />onchain — GuardLog.sol</div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 0 }}>
            {[
              { label: "contract",    val: "0xaC4bbC6A…63bB" },
              { label: "network",     val: "X Layer Testnet" },
              { label: "chain id",    val: "1952 (eip155:1952)" },
              { label: "explorer",    val: "oklink.com/x-layer-testnet" },
              { label: "backend",     val: "Python / FastAPI · port 8000" },
              { label: "frontend",    val: "Next.js 14 · port 3000" },
            ].map(({ label, val }, i) => (
              <div key={label} style={{
                display: "flex", justifyContent: "space-between", padding: "8px 14px",
                borderBottom: i < 4 ? "1px solid var(--border)" : "none",
                borderRight: i % 2 === 0 ? "1px solid var(--border)" : "none",
              }}>
                <span style={{ fontSize: 9, color: "var(--t3)" }}>{label}</span>
                <span style={{ fontSize: 9, color: "var(--t1)", fontFamily: "var(--mono)" }}>{val}</span>
              </div>
            ))}
          </div>
        </div>

        {/* ── CTA ── */}
        <div className="panel" style={{ padding: "24px", textAlign: "center" }}>
          <div style={{ fontSize: 9, color: "var(--t3)", marginBottom: 8 }}>open source · onchain · no custody</div>
          <div style={{ fontSize: 11, color: "var(--t2)", marginBottom: 16 }}>
            Deploy x402-guard in front of your AI agents today.
          </div>
          <div style={{ display: "flex", gap: 8, justifyContent: "center", flexWrap: "wrap" }}>
            <Link href="/" style={{
              padding: "8px 20px", background: "var(--red)", color: "#fff",
              fontFamily: "var(--mono)", fontSize: 10, fontWeight: 700, letterSpacing: 1,
              textDecoration: "none", borderRadius: "var(--r)", textTransform: "uppercase",
            }}>[ start protecting bots ]</Link>
            <a href="https://github.com/mintttch2/x402-guard" target="_blank" rel="noopener noreferrer" style={{
              padding: "8px 20px", border: "1px solid var(--border2)",
              color: "var(--t2)", fontFamily: "var(--mono)", fontSize: 10,
              textDecoration: "none", borderRadius: "var(--r)",
            }}>[ view on github ]</a>
          </div>
        </div>

      </div>
    </div>
  );
}

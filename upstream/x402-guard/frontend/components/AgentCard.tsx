"use client";

import { useState, useCallback, useEffect } from "react";
import { Agent, AgentStatus, formatUSD, formatTimestamp } from "@/lib/api";

interface Props {
  agent: Agent;
  onKill: (id: string) => void;
  onResume: (id: string) => void;
  onPause: (id: string) => void;
}

const BOT_ICONS: Record<string, string> = {
  sniper:     "⚡",
  arbitrage:  "⇄",
  prediction: "◈",
  sentiment:  "◉",
  custom:     "◆",
};

const GREEK: Record<string, string> = {
  "agent-alpha": "α", "agent-beta": "β",
  "agent-gamma": "γ", "agent-delta": "δ",
};

const STATUS_CFG: Record<AgentStatus, { dot: string; badge: string; label: string; accent: string }> = {
  active:  { dot: "dot-active",  badge: "badge-active",  label: "Active",  accent: "var(--green)" },
  paused:  { dot: "dot-paused",  badge: "badge-paused",  label: "Paused",  accent: "var(--amber)" },
  blocked: { dot: "dot-blocked", badge: "badge-blocked", label: "Blocked", accent: "var(--red)"   },
};

interface WalletBalance { okb: number; usdc: number; total_usd: number; }

function barColor(pct: number) {
  if (pct >= 90) return "var(--red)";
  if (pct >= 70) return "var(--amber)";
  return "var(--t2)";
}

export default function AgentCard({ agent, onKill, onResume, onPause }: Props) {
  const [loading, setLoading]   = useState<string | null>(null);
  const [balance, setBalance]   = useState<WalletBalance | null>(null);
  const [balLoad, setBalLoad]   = useState(false);

  const cfg      = STATUS_CFG[agent.status];
  const dailyPct = agent.dailyLimit > 0 ? Math.min(100, (agent.spentToday / agent.dailyLimit) * 100) : 0;
  const totalPct = agent.totalLimit > 0 ? Math.min(100, (agent.spentTotal / agent.totalLimit) * 100) : 0;

  // Fetch real wallet balance if address available
  useEffect(() => {
    const addr = (agent as any).walletAddress || (agent as any).wallet_address;
    if (!addr) return;
    // Small delay to not block initial render
    const t = setTimeout(() => {
      setBalLoad(true);
      fetch(`/api/wallet/balance/${addr}`)
        .then(r => r.ok ? r.json() : null)
        .then(d => { if (d && !d.error) setBalance(d); })
        .catch(() => null)
        .finally(() => setBalLoad(false));
    }, 500);
    return () => clearTimeout(t);
  }, [(agent as any).walletAddress || (agent as any).wallet_address]);

  const wrap = (key: string, fn: () => void) => async () => {
    setLoading(key); try { fn(); } finally { setTimeout(() => setLoading(null), 300); }
  };

  const botType = (agent as any).bot_type || (agent as any).botType;
  const icon    = BOT_ICONS[botType] ?? (GREEK[agent.id] ?? "◆");
  const isGreek = !BOT_ICONS[botType];

  return (
    <div style={{
      background: "var(--bg1)",
      border: `1px solid ${agent.status === "blocked" ? "rgba(180,50,50,.2)" : "var(--border)"}`,
      borderRadius: "var(--r)",
      padding: 12,
      display: "flex", flexDirection: "column", gap: 0,
      transition: "border-color .15s",
    }}>
      {/* Header */}
      <div style={{ display: "flex", alignItems: "flex-start", gap: 8, marginBottom: 10 }}>
        <div style={{
          width: 32, height: 32, borderRadius: 4, flexShrink: 0,
          background: agent.status === "blocked" ? "var(--red-dim)" : "var(--bg3)",
          border: `1px solid ${agent.status === "blocked" ? "rgba(180,50,50,.2)" : "var(--border2)"}`,
          display: "flex", alignItems: "center", justifyContent: "center",
          fontSize: isGreek ? 15 : 16,
          color: agent.status === "blocked" ? "var(--red)" : "var(--t1)",
          fontWeight: 700,
        }}>{icon}</div>

        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 2 }}>
            <span style={{ fontFamily: "var(--mono)", fontSize: 11, fontWeight: 700, color: "var(--t1)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
              {agent.name}
            </span>
            <div className={cfg.dot} />
          </div>
          <div style={{ fontFamily: "var(--mono)", fontSize: 9, color: "var(--t3)" }}>
            {agent.id}
            {botType && <span style={{ color: "var(--t3)", marginLeft: 6 }}>· {botType}</span>}
          </div>
        </div>

        <span className={cfg.badge}>{cfg.label}</span>
      </div>

      {/* Real wallet balance (if available) */}
      {balance && (
        <div style={{
          display: "flex", gap: 10, padding: "7px 10px", marginBottom: 10,
          background: "var(--bg3)", borderRadius: 3,
          border: "1px solid var(--border)",
        }}>
          <div>
            <div style={{ fontFamily: "var(--sans)", fontSize: 8, color: "var(--t3)", letterSpacing: "0.08em", textTransform: "uppercase" }}>OKB</div>
            <div style={{ fontFamily: "var(--mono)", fontSize: 12, fontWeight: 700, color: "var(--t1)" }}>
              {balance.okb.toFixed(4)}
            </div>
          </div>
          <div style={{ width: 1, background: "var(--border)" }} />
          <div>
            <div style={{ fontFamily: "var(--sans)", fontSize: 8, color: "var(--t3)", letterSpacing: "0.08em", textTransform: "uppercase" }}>USDC</div>
            <div style={{ fontFamily: "var(--mono)", fontSize: 12, fontWeight: 700, color: "var(--t1)" }}>
              {balance.usdc.toFixed(2)}
            </div>
          </div>

          {balLoad && !balance && (
            <div style={{ fontFamily: "var(--sans)", fontSize: 9, color: "var(--t3)" }}>loading...</div>
          )}
        </div>
      )}

      {/* Spend progress */}
      <div style={{ display: "flex", flexDirection: "column", gap: 8, marginBottom: 10 }}>
        {[
          { label: "DAILY",  spent: agent.spentToday,  limit: agent.dailyLimit,  pct: dailyPct },
          { label: "TOTAL",  spent: agent.spentTotal,   limit: agent.totalLimit,  pct: totalPct },
        ].map(({ label, spent, limit, pct }) => (
          <div key={label}>
            <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 3 }}>
              <span style={{ fontFamily: "var(--sans)", fontSize: 8, color: "var(--t3)", letterSpacing: "0.08em", textTransform: "uppercase" }}>{label}</span>
              <span style={{ fontFamily: "var(--mono)", fontSize: 10, color: pct >= 90 ? "var(--red)" : "var(--t2)" }}>
                {formatUSD(spent)} / {formatUSD(limit)}
              </span>
            </div>
            <div className="progress-track">
              <div className="progress-fill" style={{ width: `${pct}%`, background: barColor(pct) }} />
            </div>
          </div>
        ))}
      </div>

      {/* Footer */}
      <div style={{ display: "flex", alignItems: "center", gap: 6, borderTop: "1px solid var(--border)", paddingTop: 8 }}>
        <span style={{ fontFamily: "var(--mono)", fontSize: 9, color: "var(--t3)", flex: 1 }}>
          {agent.txCount} tx
        </span>
        {agent.status === "active" && (
          <button onClick={wrap("pause", () => onPause(agent.id))}
            disabled={loading === "pause"} className="btn" style={{ fontSize: 9, padding: "3px 8px" }}>
            [ {loading === "pause" ? "…" : "pause"} ]
          </button>
        )}
        {agent.status !== "active" && (
          <button onClick={wrap("resume", () => onResume(agent.id))}
            disabled={loading === "resume"} className="btn-green" style={{ fontSize: 9, padding: "3px 8px" }}>
            [ {loading === "resume" ? "…" : "resume"} ]
          </button>
        )}
        {agent.status !== "blocked" && (
          <button onClick={wrap("kill", () => onKill(agent.id))}
            disabled={loading === "kill"} className="btn-red" style={{ fontSize: 9, padding: "3px 8px" }}>
            [ {loading === "kill" ? "…" : "kill"} ]
          </button>
        )}
      </div>
    </div>
  );
}

"use client";

import { useEffect, useState, useCallback } from "react";

interface Trade {
  id:        string;
  bot:       string;
  bot_type:  string;
  agent_id:  string;
  action:    string;
  recipient: string;
  amount:    number;
  asset:     string;
  status:    string;
  reason:    string;
  timestamp: string;
}

const BOT_ICONS: Record<string, string> = {
  sniper: "⚡", arbitrage: "⇄", prediction: "◈", sentiment: "◉", custom: "◆",
};

const ACTION_COLOR: Record<string, string> = {
  SNIPE: "var(--p-dim)", ARB: "var(--p-dim)", LONG: "var(--p-dim)",
  BUY: "var(--p-dim)",   ENTRY: "var(--p-dim)",
  SWAP: "#448aff",       TRADE: "#448aff",
  HOLD: "var(--t2)",     SEND: "var(--t2)", PAY: "var(--t2)", TX: "var(--t2)",
  REJECTED: "var(--red)",
};

function timeAgo(ts: string): string {
  const d = Date.now() - new Date(ts).getTime();
  const m = Math.floor(d / 60000);
  if (m < 1) return "now";
  if (m < 60) return `${m}m`;
  return `${Math.floor(m / 60)}h`;
}

export default function TradeFeed() {
  const [trades, setTrades] = useState<Trade[]>([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try {
      const res = await fetch("/api/wallet/trades?limit=30");
      const data = await res.json();
      if (Array.isArray(data)) setTrades(data);
    } catch {}
    finally { setLoading(false); }
  }, []);

  useEffect(() => {
    load();
    const id = setInterval(load, 8000);   // refresh every 8s
    return () => clearInterval(id);
  }, [load]);

  const approved = trades.filter(t => t.status !== "blocked").length;
  const blocked  = trades.filter(t => t.status === "blocked").length;

  return (
    <div className="panel" style={{ display: "flex", flexDirection: "column", height: "100%" }}>
      {/* Header */}
      <div className="panel-head">
        <div className="panel-head-dot" style={{ animation: "blink 1.2s step-end infinite" }} />
        live trades
        <span style={{ marginLeft: "auto", fontFamily: "var(--mono)", fontSize: 10, color: "var(--t3)" }}>
          streaming
        </span>
      </div>

      {/* Feed */}
      <div style={{ flex: 1, overflowY: "auto", maxHeight: 280 }}>
        {loading ? (
          <div style={{ padding: 24, textAlign: "center", color: "var(--t3)", fontSize: 10 }}>loading...</div>
        ) : trades.length === 0 ? (
          <div style={{ padding: 24, textAlign: "center", color: "var(--t3)", fontSize: 10 }}>no trades yet</div>
        ) : trades.map((t) => {
          const icon     = BOT_ICONS[t.bot_type] ?? "◆";
          const actColor = ACTION_COLOR[t.action] ?? "var(--t2)";
          const isBlocked = t.status === "blocked";

          return (
            <div key={t.id} style={{
              padding: "8px 12px",
              borderBottom: "1px solid var(--border)",
              transition: "background .1s", cursor: "default",
              opacity: isBlocked ? 0.65 : 1,
            }}
              onMouseEnter={e => (e.currentTarget as HTMLDivElement).style.background = "var(--p-ghost)"}
              onMouseLeave={e => (e.currentTarget as HTMLDivElement).style.background = "transparent"}
            >
              {/* Row 1: icon + bot + action + amount */}
              <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 3 }}>
                <span style={{ fontSize: 11, width: 16, flexShrink: 0 }}>{icon}</span>
                <span style={{ fontFamily: "var(--mono)", fontSize: 10, color: "var(--t2)", flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {t.bot}
                </span>
                <span style={{
                  fontFamily: "var(--mono)", fontSize: 10, fontWeight: 700,
                  color: actColor, flexShrink: 0,
                  padding: "1px 5px", borderRadius: 2,
                  background: isBlocked ? "var(--red-dim)" : `${actColor}12`,
                  border: `1px solid ${actColor}28`,
                }}>
                  {t.action}
                </span>
                <span style={{ fontFamily: "var(--mono)", fontSize: 11, fontWeight: 700, color: "var(--t1)", flexShrink: 0 }}>
                  ${t.amount.toFixed(2)}
                </span>
              </div>
              {/* Row 2: recipient + time */}
              <div style={{ display: "flex", alignItems: "center", gap: 6, paddingLeft: 22 }}>
                <span style={{ fontFamily: "var(--mono)", fontSize: 9, color: "var(--t3)" }}>→</span>
                <span style={{ fontFamily: "var(--mono)", fontSize: 9, color: "var(--t3)", flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {t.recipient}
                </span>
                <span style={{ fontFamily: "var(--mono)", fontSize: 9, color: "var(--t3)", flexShrink: 0 }}>
                  {timeAgo(t.timestamp)}
                </span>
              </div>
              {/* Blocked reason */}
              {isBlocked && (
                <div style={{ display: "flex", gap: 4, paddingLeft: 22, marginTop: 2 }}>
                  <span style={{ fontFamily: "var(--sans)", fontSize: 9, color: "var(--red)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    {t.reason?.slice(0, 60)}
                  </span>
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Footer */}
      <div style={{ padding: "6px 12px", borderTop: "1px solid var(--border)", display: "flex", alignItems: "center", gap: 12 }}>
        <span style={{ display: "flex", alignItems: "center", gap: 4 }}>
          <span className="dot" style={{ background: "var(--p-dim)" }} />
          <span style={{ fontFamily: "var(--mono)", fontSize: 9, color: "var(--t3)" }}>{approved} executed</span>
        </span>
        <span style={{ display: "flex", alignItems: "center", gap: 4 }}>
          <span className="dot" style={{ background: "var(--red)" }} />
          <span style={{ fontFamily: "var(--mono)", fontSize: 9, color: "var(--t3)" }}>{blocked} rejected</span>
        </span>
        <span style={{ marginLeft: "auto" }}>
          <span className="live-badge" style={{ fontSize: 8 }}>● LIVE</span>
        </span>
      </div>
    </div>
  );
}

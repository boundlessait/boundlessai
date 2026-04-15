"use client";

import { useCallback } from "react";
import { Transaction, TransactionStatus, formatUSD, formatTimestamp } from "@/lib/api";

interface AlertTransaction extends Transaction {
  url?: string;
  agentName?: string;
  recipient?: string;
}

interface Props {
  transactions: AlertTransaction[];
  loading?: boolean;
  onRefresh?: () => void;
}

const ICONS: Record<string, { sym: string; cls: string }> = {
  approved:   { sym: "[+]", cls: "ok"    },
  denied:     { sym: "[!]", cls: "block" },
  flagged:    { sym: "[?]", cls: "flag"  },
  soft_alert: { sym: "[~]", cls: "flag"  },
  blocked:    { sym: "[!]", cls: "block" },
};
const LABELS: Record<string, string> = {
  approved: "approved", denied: "blocked", flagged: "flagged",
  soft_alert: "alert", blocked: "blocked",
};

const iconColor: Record<string, string> = {
  ok: "var(--t2)", block: "var(--red)", flag: "var(--amber)",
};
const badgeStyle: Record<string, React.CSSProperties> = {
  ok:    { background: "rgba(255,255,255,.04)", color: "var(--t2)",   border: "1px solid var(--border)" },
  block: { background: "var(--red-dim)",        color: "var(--red)",   border: "1px solid rgba(180,50,50,.2)" },
  flag:  { background: "rgba(255,170,0,.1)",    color: "var(--amber)", border: "1px solid rgba(255,170,0,.15)" },
};

export default function AlertFeed({ transactions, loading = false, onRefresh }: Props) {
  const openUrl = useCallback((url: string) => window.open(url, "_blank", "noopener,noreferrer"), []);

  return (
    <div className="panel" style={{ display: "flex", flexDirection: "column", height: "100%" }}>
      <div className="panel-head">
        <div className="panel-head-dot" />
        live feed
        <span style={{ marginLeft: "auto", fontSize: 9, color: "var(--t3)" }}>streaming</span>
        {onRefresh && (
          <button onClick={onRefresh} className="btn" style={{ padding: "2px 6px", fontSize: 9 }}>
            {loading ? "…" : "⟳"}
          </button>
        )}
      </div>

      <div style={{ flex: 1, overflowY: "auto", maxHeight: 260 }}>
        {transactions.length === 0 ? (
          <div style={{ padding: "24px 12px", textAlign: "center", color: "var(--t3)", fontSize: 10 }}>
            no transactions
          </div>
        ) : (
          transactions.map((tx) => {
              const { sym, cls } = ICONS[tx.status] ?? { sym: "[?]", cls: "flag" };
            return (
              <div key={tx.id}
                onClick={() => tx.url && openUrl(tx.url)}
                style={{
                  padding: "8px 12px",
                  borderBottom: "1px solid var(--border)",
                  cursor: "pointer", transition: "background .1s",
                }}
                onMouseEnter={e => (e.currentTarget as HTMLDivElement).style.background = "var(--p-ghost)"}
                onMouseLeave={e => (e.currentTarget as HTMLDivElement).style.background = "transparent"}
              >
                {/* Row 1 */}
                <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 3 }}>
                  <span style={{ fontSize: 9, width: 28, textAlign: "center", color: iconColor[cls], fontWeight: 500 }}>
                    {sym}
                  </span>
                  <span style={{ fontSize: 10, color: "var(--t2)", flex: 1 }}>
                    {tx.agentName ?? tx.agent_id} · {tx.recipient ?? tx.pay_to}
                  </span>
                  <span style={{ fontSize: 11, fontWeight: 700, color: "var(--t1)" }}>
                    {formatUSD(tx.amount)}
                  </span>
                </div>
                {/* Row 2 */}
                <div style={{ display: "flex", alignItems: "center", gap: 6, paddingLeft: 28 }}>
                  <span style={{ fontSize: 9, padding: "1px 6px", borderRadius: 1, ...badgeStyle[cls] }}>
                    {LABELS[tx.status]}
                  </span>
                  <span style={{ fontSize: 9, color: "var(--t3)", flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    {tx.reason}
                  </span>
                  <span style={{ fontSize: 9, color: "var(--t3)", marginLeft: "auto", flexShrink: 0 }}>
                    {formatTimestamp(tx.timestamp)}
                  </span>
                </div>
              </div>
            );
          })
        )}
      </div>

      {/* Footer */}
      <div style={{
        padding: "6px 12px", borderTop: "1px solid var(--border)",
        display: "flex", alignItems: "center", gap: 10,
      }}>
        {[
          { label: "ok",      count: transactions.filter(t => t.status === "approved").length, color: "var(--t2)"   },
          { label: "flagged", count: transactions.filter(t => t.status === "soft_alert").length,  color: "var(--amber)" },
          { label: "denied",  count: transactions.filter(t => t.status === "blocked").length,   color: "var(--red)"   },
        ].map(({ label, count, color }) => (
          <span key={label} style={{ fontSize: 9, color: "var(--t3)" }}>
            <span style={{ color }}>{count}</span> {label}
          </span>
        ))}
        <span style={{
          marginLeft: "auto", fontSize: 9, color: "var(--t1)",
          letterSpacing: ".5px",
        }}>LIVE</span>
      </div>
    </div>
  );
}

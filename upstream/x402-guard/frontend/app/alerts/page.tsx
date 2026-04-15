"use client";

import { useState, useEffect, useCallback } from "react";
import { RefreshCw, ExternalLink } from "lucide-react";

interface AlertItem {
  id: string;
  agent_id: string;
  amount: number;
  pay_to: string;
  status: "approved" | "soft_alert" | "blocked";
  reason: string;
  timestamp: string;
}

const STATUS: Record<string, { sym: string; label: string; color: string; badgeStyle: React.CSSProperties }> = {
  approved:   { sym: "[+]", label: "approved",   color: "var(--t2)",   badgeStyle: { background: "rgba(255,255,255,.04)", color: "var(--t2)",   border: "1px solid var(--border)"            } },
  soft_alert: { sym: "[~]", label: "alert",      color: "var(--amber)",badgeStyle: { background: "rgba(255,170,0,.1)",    color: "var(--amber)", border: "1px solid rgba(255,170,0,.15)"      } },
  blocked:    { sym: "[!]", label: "blocked",    color: "var(--red)",  badgeStyle: { background: "var(--red-dim)",        color: "var(--red)",   border: "1px solid rgba(180,50,50,.2)"       } },
};

function timeAgo(ts: string): string {
  const d = Date.now() - new Date(ts).getTime();
  const m = Math.floor(d / 60000);
  if (m < 1) return "now";
  if (m < 60) return `${m}m`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h`;
  return `${Math.floor(h / 24)}d`;
}

export default function AlertsPage() {
  const [alerts, setAlerts] = useState<AlertItem[]>([]);
  const [agentNames, setAgentNames] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<"all"|"blocked"|"soft_alert"|"approved">("all");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [txRes, agentRes] = await Promise.all([
        fetch("/api/transactions/alerts?limit=50"),
        fetch("/api/agents"),
      ]);
      const data = await txRes.json();
      setAlerts(Array.isArray(data) && data.length ? data : []);
      if (agentRes.ok) {
        const agents = await agentRes.json();
        const names: Record<string, string> = {};
        if (Array.isArray(agents)) agents.forEach((a: any) => { names[a.id] = a.name || a.id; });
        setAgentNames(names);
      }
    } catch { setAlerts([]); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const filtered = filter === "all" ? alerts : alerts.filter(a => a.status === filter);
  const counts = {
    all:       alerts.length,
    blocked:   alerts.filter(a => a.status === "blocked").length,
    soft_alert:alerts.filter(a => a.status === "soft_alert").length,
    approved:  alerts.filter(a => a.status === "approved").length,
  };

  const filterCfg: { key: typeof filter; label: string; color: string }[] = [
    { key: "all",       label: `All ${counts.all}`,             color: "var(--t2)"    },
    { key: "blocked",   label: `Blocked ${counts.blocked}`,     color: "var(--red)"   },
    { key: "soft_alert",label: `Alerts ${counts.soft_alert}`,   color: "var(--amber)" },
    { key: "approved",  label: `Approved ${counts.approved}`,   color: "var(--t2)"   },
  ];

  return (
    <div style={{ position: "relative", zIndex: 1 }}>
      {/* Topbar */}
      <header style={{
        height: 44, background: "rgba(2,9,2,0.95)", borderBottom: "1px solid var(--border)",
        display: "flex", alignItems: "center", padding: "0 20px", gap: 12,
        position: "sticky", top: 0, zIndex: 40,
      }}>
        <span style={{ fontSize: 11, color: "var(--t2)" }}>
          root/<span style={{ color: "var(--t1)" }}>alerts</span>
        </span>
        <div style={{ marginLeft: "auto", display: "flex", gap: 8 }}>
          <button onClick={load} className="btn" style={{ padding: "3px 8px", fontSize: 10 }}>
            <RefreshCw size={11} className={loading ? "animate-spin" : ""} />
          </button>
        </div>
      </header>

      <div style={{ padding: "16px 20px", display: "flex", flexDirection: "column", gap: 12 }}>

        {/* Filters */}
        <div style={{ display: "flex", gap: 6 }}>
          {filterCfg.map(({ key, label, color }) => (
            <button key={key} onClick={() => setFilter(key)}
              style={{
                fontFamily: "var(--mono)", fontSize: 9, padding: "3px 10px",
                borderRadius: 2, cursor: "pointer",
                background: filter === key ? "rgba(255,255,255,.06)" : "transparent",
                color: filter === key ? "var(--t1)" : color,
                border: filter === key ? "1px solid var(--border2)" : "1px solid var(--border)",
              }}>
              {label}
            </button>
          ))}
        </div>

        {/* List */}
        <div className="panel">
          {loading ? (
            <div style={{ padding: "40px", textAlign: "center", color: "var(--t3)", fontSize: 10 }}>
              loading...
            </div>
          ) : filtered.length === 0 ? (
            <div style={{ padding: "40px", textAlign: "center", color: "var(--t3)", fontSize: 10 }}>
              no transactions
            </div>
          ) : filtered.map(alert => {
            const s = STATUS[alert.status] ?? STATUS.approved;
            return (
              <div key={alert.id} style={{
                display: "flex", alignItems: "flex-start", gap: 12,
                padding: "10px 16px", borderBottom: "1px solid var(--border)",
                transition: "background .1s", cursor: "default",
              }}
                onMouseEnter={e => (e.currentTarget as HTMLDivElement).style.background = "var(--p-ghost)"}
                onMouseLeave={e => (e.currentTarget as HTMLDivElement).style.background = "transparent"}
              >
                {/* Icon */}
                <span style={{ fontSize: 10, color: s.color, width: 28, flexShrink: 0, fontWeight: 500, paddingTop: 1 }}>
                  {s.sym}
                </span>

                {/* Main */}
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
                    <span style={{ fontSize: 9, padding: "1px 6px", borderRadius: 1, ...s.badgeStyle }}>
                      {s.label}
                    </span>
                    <span style={{ fontFamily: "var(--mono)", fontSize: 11, fontWeight: 700, color: "var(--t1)" }}>
                      ${alert.amount.toFixed(2)} USDC
                    </span>
                    <span style={{ fontSize: 9, color: "var(--t3)" }}>→</span>
                    <span style={{ fontFamily: "var(--mono)", fontSize: 10, color: "var(--t2)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", maxWidth: 200 }}>
                      {alert.pay_to}
                    </span>
                    <a href={`https://www.oklink.com/x-layer-testnet/address/${alert.pay_to}`}
                      target="_blank" rel="noopener noreferrer"
                      style={{ color: "var(--t3)", flexShrink: 0 }}
                      title="View on OKLink">
                      <ExternalLink size={9} />
                    </a>
                  </div>
                  <p style={{ fontSize: 9, color: "var(--t3)", lineHeight: 1.5 }}>{alert.reason}</p>
                </div>

                {/* Meta */}
                <div style={{ flexShrink: 0, textAlign: "right" }}>
                  <div style={{ fontFamily: "var(--mono)", fontSize: 9, color: "var(--t2)" }}>{agentNames[alert.agent_id] || alert.agent_id}</div>
                  <div style={{ fontFamily: "var(--mono)", fontSize: 9, color: "var(--t3)", marginTop: 2 }}>
                    {timeAgo(alert.timestamp)}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

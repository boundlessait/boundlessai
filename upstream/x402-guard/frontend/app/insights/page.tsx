"use client";

import { useState, useEffect, useCallback } from "react";
import { RefreshCw } from "lucide-react";

interface Anomaly {
  type: string;
  severity: "low"|"medium"|"high"|"critical";
  description: string;
  amount?: number;
  domain?: string;
}

interface AgentAnalysis {
  agent_id: string;
  anomalies: Anomaly[];
  suggested_policy: {
    daily_limit: number; per_tx_limit: number;
    whitelist: string[]; blacklist: string[];
  };
  reasoning: string[];
  confidence_score: number;
}

interface DomainEntry { domain: string; score: number; }

const SEVERITY_COLOR: Record<string, string> = {
  low: "var(--t2)", medium: "var(--amber)",
  high: "var(--red)", critical: "var(--red)",
};
const SEVERITY_SYM: Record<string, string> = {
  low: "[~]", medium: "[?]", high: "[!]", critical: "[!!]",
};

// agentNames populated from /api/agents at load time

export default function InsightsPage() {
  const [analyses, setAnalyses]   = useState<AgentAnalysis[]>([]);
  const [domains, setDomains]     = useState<DomainEntry[]>([]);
  const [onchain, setOnchain]     = useState<Record<string, number> | null>(null);
  const [loading, setLoading]     = useState(true);
  const [agentIds, setAgentIds]   = useState<string[]>([]);
  const [agentNames, setAgentNames] = useState<Record<string, string>>({});
  const [selected, setSelected]   = useState<string>("");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      // Fetch agent list dynamically from API
      const agentsRes = await fetch("/api/agents").then(r => r.ok ? r.json() : []).catch(() => []);
      const ids: string[] = Array.isArray(agentsRes) ? agentsRes.map((a: any) => a.id) : [];
      const names: Record<string, string> = {};
      if (Array.isArray(agentsRes)) agentsRes.forEach((a: any) => { names[a.id] = a.name || a.id; });
      setAgentIds(ids);
      setAgentNames(names);
      if (ids.length && !selected) setSelected(ids[0]);

      // Fetch AI analysis for each agent
      const results = await Promise.all(
        ids.map((id: string) =>
          fetch(`/api/ai/analyze/${id}`, { method: "POST" })
            .then(r => r.ok ? r.json() : null).catch(() => null)
        )
      );
      setAnalyses(results.filter(Boolean) as AgentAnalysis[]);

      // Onchain stats
      const oc = await fetch("/api/onchain/stats")
        .then(r => r.ok ? r.json() : null).catch(() => null);
      if (oc) setOnchain(oc);
    } catch { /* no-op */ }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const current = analyses.find(a => a.agent_id === selected);
  const totalAnomalies = analyses.reduce((s, a) => s + a.anomalies.length, 0);
  const highSeverity   = analyses.reduce((s, a) => s + a.anomalies.filter(x => x.severity === "high" || x.severity === "critical").length, 0);

  return (
    <div style={{ position: "relative", zIndex: 1 }}>
      {/* Topbar */}
      <header style={{
        height: 44, background: "rgba(2,9,2,0.95)", borderBottom: "1px solid var(--border)",
        display: "flex", alignItems: "center", padding: "0 20px", gap: 12,
        position: "sticky", top: 0, zIndex: 40,
      }}>
        <span style={{ fontSize: 11, color: "var(--t2)" }}>
          root/<span style={{ color: "var(--t1)" }}>insights</span>
        </span>
        <div style={{ marginLeft: "auto" }}>
          <button onClick={load} className="btn" style={{ padding: "3px 8px", fontSize: 10 }}>
            <RefreshCw size={11} className={loading ? "animate-spin" : ""} />
          </button>
        </div>
      </header>

      <div style={{ padding: "16px 20px", display: "flex", flexDirection: "column", gap: 12 }}>

        {/* Stat strip */}
        <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 8 }}>
          {[
            { label: "agents analysed", val: analyses.length || agentIds.length, color: "var(--t1)" },
            { label: "total anomalies", val: totalAnomalies, color: totalAnomalies > 0 ? "var(--amber)" : "var(--t1)" },
            { label: "high severity",   val: highSeverity,   color: highSeverity  > 0 ? "var(--red)"   : "var(--t1)" },
            { label: "onchain txns",    val: onchain ? (onchain.approved ?? 0) + (onchain.soft_alerts ?? 0) + (onchain.blocked ?? 0) : "--", color: "var(--t1)" },
          ].map(({ label, val, color }) => (
            <div key={label} className="stat">
              <div className="stat-label">{label}</div>
              <div className="stat-value" style={{ color, fontSize: 20 }}>{val}</div>
            </div>
          ))}
        </div>

        {/* Agent selector + analysis */}
        <div style={{ display: "grid", gridTemplateColumns: "160px 1fr", gap: 12 }}>
          {/* Selector */}
          <div className="panel" style={{ height: "fit-content" }}>
            <div className="panel-head"><div className="panel-head-dot" />agents</div>
            {agentIds.map(id => {
              const a = analyses.find(x => x.agent_id === id);
              const hasHigh = a?.anomalies.some(x => x.severity === "high" || x.severity === "critical");
              return (
                <button key={id} onClick={() => setSelected(id)}
                  style={{
                    width: "100%", textAlign: "left", padding: "9px 14px",
                    display: "flex", alignItems: "center", gap: 8,
                    background: selected === id ? "rgba(255,255,255,.04)" : "transparent",
                    borderLeft: selected === id ? "2px solid var(--t2)" : "2px solid transparent",
                    borderBottom: "1px solid var(--border)",
                    cursor: "pointer", fontFamily: "var(--mono)",
                  }}>
                  <span style={{ fontSize: 13, fontWeight: 700, color: selected === id ? "var(--t1)" : "var(--t2)", width: 16 }}>
                    {(agentNames[id] || id).charAt(0).toUpperCase()}
                  </span>
                  <span style={{ fontSize: 10, color: selected === id ? "var(--t1)" : "var(--t3)", flex: 1 }}>
                    {agentNames[id] || id}
                  </span>
                  {hasHigh && <span style={{ fontSize: 9, color: "var(--red)" }}>[!]</span>}
                  {a && !hasHigh && a.anomalies.length > 0 && (
                    <span style={{ fontSize: 9, color: "var(--amber)" }}>[~]</span>
                  )}
                </button>
              );
            })}
          </div>

          {/* Analysis panel */}
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            {loading ? (
              <div className="panel" style={{ padding: 40, textAlign: "center", color: "var(--t3)", fontSize: 10 }}>
                analysing agents...
              </div>
            ) : current ? (
              <>
                {/* Anomalies */}
                <div className="panel">
                  <div className="panel-head">
                    <div className="panel-head-dot" />
                    anomalies — {agentNames[selected] || selected}
                    <span style={{ marginLeft: "auto", fontSize: 9, color: "var(--t3)" }}>
                      confidence {Math.round((current.confidence_score ?? 0) * 100)}%
                    </span>
                  </div>
                  {current.anomalies.length === 0 ? (
                    <div style={{ padding: "16px 14px", fontSize: 10, color: "var(--t3)" }}>
                      [+] no anomalies detected
                    </div>
                  ) : current.anomalies.map((a, i) => (
                    <div key={i} style={{
                      display: "flex", gap: 10, padding: "9px 14px",
                      borderBottom: "1px solid var(--border)",
                    }}>
                      <span style={{ fontSize: 10, color: SEVERITY_COLOR[a.severity], width: 24, flexShrink: 0, fontWeight: 500 }}>
                        {SEVERITY_SYM[a.severity]}
                      </span>
                      <div style={{ flex: 1 }}>
                        <div style={{ display: "flex", gap: 8, marginBottom: 3 }}>
                          <span style={{ fontSize: 9, padding: "1px 6px", borderRadius: 1,
                            background: `${SEVERITY_COLOR[a.severity]}18`,
                            border: `1px solid ${SEVERITY_COLOR[a.severity]}30`,
                            color: SEVERITY_COLOR[a.severity] }}>
                            {a.severity}
                          </span>
                          <span style={{ fontSize: 9, color: "var(--t3)", fontFamily: "var(--mono)" }}>
                            {a.type}
                          </span>
                          {a.amount && (
                            <span style={{ fontSize: 9, color: "var(--t2)", fontFamily: "var(--mono)" }}>
                              ${a.amount.toFixed(2)}
                            </span>
                          )}
                        </div>
                        <p style={{ fontSize: 9, color: "var(--t2)", lineHeight: 1.5 }}>{a.description}</p>
                      </div>
                    </div>
                  ))}
                </div>

                {/* Suggested policy */}
                <div className="panel">
                  <div className="panel-head">
                    <div className="panel-head-dot" />suggested policy
                  </div>
                  <div style={{ padding: "10px 14px", display: "flex", flexDirection: "column", gap: 6 }}>
                    {[
                      { label: "daily limit",  val: `$${current.suggested_policy?.daily_limit ?? "--"}` },
                      { label: "per tx limit", val: `$${current.suggested_policy?.per_tx_limit ?? "--"}` },
                      { label: "whitelist",    val: current.suggested_policy?.whitelist?.join(", ") || "none" },
                      { label: "blacklist",    val: current.suggested_policy?.blacklist?.join(", ") || "none" },
                    ].map(({ label, val }) => (
                      <div key={label} style={{ display: "flex", justifyContent: "space-between", fontSize: 10, padding: "3px 0", borderBottom: "1px solid var(--border)" }}>
                        <span style={{ color: "var(--t3)" }}>{label}</span>
                        <span style={{ color: "var(--t1)", fontFamily: "var(--mono)" }}>{val}</span>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Reasoning */}
                {current.reasoning?.length > 0 && (
                  <div className="panel">
                    <div className="panel-head"><div className="panel-head-dot" />reasoning</div>
                    <div style={{ padding: "10px 14px" }}>
                      {current.reasoning.map((r, i) => (
                        <div key={i} style={{ fontSize: 9, color: "var(--t2)", padding: "3px 0", display: "flex", gap: 8 }}>
                          <span style={{ color: "var(--t3)", flexShrink: 0 }}>{i + 1}.</span>
                          <span style={{ lineHeight: 1.6 }}>{r}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </>
            ) : (
              <div className="panel" style={{ padding: 40, textAlign: "center", color: "var(--t3)", fontSize: 10 }}>
                {">"} select agent to view analysis
              </div>
            )}
          </div>
        </div>

        {/* Onchain stats */}
        {onchain && (
          <div className="panel">
            <div className="panel-head">
              <div className="panel-head-dot" />onchain stats — GuardLog.sol
              <span style={{ marginLeft: "auto", fontSize: 9, color: "var(--t3)" }}>X Layer Testnet</span>
            </div>
            <div style={{ display: "flex", gap: 0 }}>
              {[
                { label: "approved",    val: onchain.approved ?? 0,    color: "var(--t2)"    },
                { label: "soft alerts", val: onchain.soft_alerts ?? 0, color: "var(--amber)" },
                { label: "blocked",     val: onchain.blocked ?? 0,     color: "var(--red)"   },
              ].map(({ label, val, color }) => (
                <div key={label} style={{ flex: 1, padding: "14px 16px", borderRight: "1px solid var(--border)" }}>
                  <div style={{ fontSize: 8, color: "var(--t3)", letterSpacing: 1, textTransform: "uppercase", marginBottom: 6 }}>{label}</div>
                  <div style={{ fontFamily: "var(--mono)", fontSize: 22, fontWeight: 700, color }}>{val}</div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

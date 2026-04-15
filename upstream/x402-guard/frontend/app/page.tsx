"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts";
import { RefreshCw } from "lucide-react";

import SpendingChart  from "@/components/SpendingChart";
import PnlChart       from "@/components/PnlChart";
import TradeFeed      from "@/components/TradeFeed";
import AgentCard      from "@/components/AgentCard";
import TopDomains     from "@/components/TopDomains";
import BlockReasons   from "@/components/BlockReasons";
import EmergencyPanel from "@/components/EmergencyPanel";
import {
  Agent, Transaction, DashboardStats,
  formatUSD,
} from "@/lib/api";

export default function Dashboard() {
  const [agents, setAgents]       = useState<Agent[]>([]);
  const [transactions, setTxs]    = useState<Transaction[]>([]);
  const [stats, setStats]         = useState<DashboardStats | null>(null);
  const [chartData, setChart]     = useState<Array<Record<string, number | string>>>([]);
  const [loading, setLoading]     = useState(false);
  const [alertLoad, setAlertLoad] = useState(false);
  const [chartRange, setRange]    = useState<"6h"|"24h"|"7d">("24h");
  const [ts, setTs]               = useState("");
  const [resetIn, setResetIn]     = useState("──");
  const [liveMode, setLive]             = useState(true);
  const [fleetBalance, setFleetBalance] = useState<{ usdc: number; okb: number } | null>(null);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);

  // Timestamp
  useEffect(() => {
    const tick = () => {
      const n = new Date();
      setTs(n.toLocaleTimeString("en-US", { hour12: false, timeZone: "UTC" }));
      // Use UTC midnight so reset countdown is always correct regardless of server timezone
      const nextMidnightUTC = new Date(Date.UTC(n.getUTCFullYear(), n.getUTCMonth(), n.getUTCDate() + 1));
      const d = nextMidnightUTC.getTime() - n.getTime();
      setResetIn(`${Math.floor(d/3600000)}h ${Math.floor((d%3600000)/60000)}m`);
    };
    tick(); const id = setInterval(tick, 1000); return () => clearInterval(id);
  }, []);

  const load = useCallback(async (showLoad = false) => {
    if (showLoad) setLoading(true);
    try {
      const [a, t, s, tl, fb] = await Promise.all([
        fetch("/api/agents").then(r => r.ok ? r.json() : null).catch(() => null),
        fetch("/api/transactions/alerts?limit=20").then(r => r.ok ? r.json() : null).catch(() => null),
        fetch("/api/dashboard/stats").then(r => r.ok ? r.json() : null).catch(() => null),
        fetch("/api/dashboard/timeline?hours=24").then(r => r.ok ? r.json() : null).catch(() => null),
        fetch("/api/wallet/balances").then(r => r.ok ? r.json() : null).catch(() => null),
      ]);
      if (a) setAgents(a);
      if (t) setTxs(t);
      if (s) setStats(s);
      if (tl) setChart(tl);
      if (Array.isArray(fb)) {
        const usdc = fb.reduce((s: number, w: any) => s + (w.usdc ?? 0), 0);
        const okb  = fb.reduce((s: number, w: any) => s + (w.okb  ?? 0), 0);
        setFleetBalance({ usdc, okb });
      }

    } catch (e) {
      console.error("Dashboard load error:", e);
    } finally { setLoading(false); }
  }, []);

  const refreshAlerts = useCallback(async () => {
    setAlertLoad(true);
    const t = await fetch("/api/transactions/alerts?limit=20").then(r => r.ok ? r.json() : null).catch(() => null);
    if (t) setTxs(t); setAlertLoad(false);
  }, []);

  useEffect(() => { load(false); }, [load]);
  useEffect(() => {
    if (liveMode) timer.current = setInterval(() => load(), 12000);  // 12s polling
    else if (timer.current) clearInterval(timer.current);
    return () => { if (timer.current) clearInterval(timer.current); };
  }, [liveMode, load]);

  const kill   = useCallback(async (id: string) => {
    await fetch(`/api/agents/${id}/kill`, { method: "POST" }).catch(() => null);
    setAgents(p => p.map(a => a.id === id ? { ...a, status: "blocked" as const } : a));
  }, []);
  const resume = useCallback(async (id: string) => {
    await fetch(`/api/agents/${id}/resume`, { method: "POST" }).catch(() => null);
    setAgents(p => p.map(a => a.id === id ? { ...a, status: "active" as const } : a));
  }, []);
  const pause  = useCallback(async (id: string) => {
    await fetch(`/api/agents/${id}/status`, {
      method: "PATCH", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status: "paused" }),
    }).catch(() => null);
    setAgents(p => p.map(a => a.id === id ? { ...a, status: "paused" as const } : a));
  }, []);
  const killAll   = useCallback(async () => {
    for (const a of agents.filter(a => a.status !== "blocked"))
      await fetch(`/api/agents/${a.id}/kill`, { method: "POST" }).catch(() => null);
    setAgents(p => p.map(a => ({ ...a, status: "blocked" as const })));
  }, [agents]);
  const resumeAll = useCallback(async () => {
    for (const a of agents.filter(a => a.status !== "active"))
      await fetch(`/api/agents/${a.id}/resume`, { method: "POST" }).catch(() => null);
    setAgents(p => p.map(a => ({ ...a, status: "active" as const })));
  }, [agents]);

  const display  = chartRange === "6h" ? chartData.slice(-6) : chartData;
  const miniDisplay = display.map((d) => ({
    ...d,
    total: Object.entries(d).filter(([k]) => k !== "time").reduce((s, [, v]) => s + (Number(v) || 0), 0),
  }));
  const monthly  = stats?.totalSpentMonth ?? 0;
  const fleetUSDC = fleetBalance?.usdc ?? 0;
  const fleetOKB  = fleetBalance?.okb  ?? 0;
  const netWorth  = fleetUSDC;
  const pnl       = stats?.txApprovedToday ?? 0;
  const denied   = stats?.txDeniedToday ?? 0;

  return (
    <div style={{ position: "relative", zIndex: 1 }}>
      {/* ── Topbar ── */}
      <header style={{
        height: 44, background: "rgba(2,9,2,0.95)", borderBottom: "1px solid var(--border)",
        display: "flex", alignItems: "center", padding: "0 20px", gap: 8,
        position: "sticky", top: 0, zIndex: 40,
      }}>
        <span style={{ fontSize: 11, color: "var(--t2)" }}>
          root/<span style={{ color: "var(--t1)" }}>dashboard</span>
        </span>
        <span style={{ fontFamily: "var(--mono)", fontSize: 10, color: "var(--t3)", marginLeft: 4 }}>{ts}</span>
        <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 8 }}>
          <button
            onClick={() => setLive(v => !v)}
            style={{
              display: "flex", alignItems: "center", gap: 5,
              fontSize: 10, color: "var(--t1)", letterSpacing: ".5px",
              padding: "3px 8px", border: "1px solid var(--border2)", borderRadius: 2,
              background: "rgba(255,255,255,.04)", fontFamily: "var(--mono)", cursor: "pointer",
            }}>
            <div className="dot-live" />{liveMode ? "LIVE" : "PAUSED"}
          </button>
          <button onClick={() => load()} className="btn" style={{ padding: "3px 8px", fontSize: 10 }}>
            <RefreshCw size={11} className={loading ? "animate-spin" : ""} />
          </button>
        </div>
      </header>

      <div style={{ padding: "16px 20px", display: "flex", flexDirection: "column", gap: 12 }}>

        {/* ── Portfolio Row ── */}
        <div>
          <div className="sec-header">wallet overview</div>
          <div className="dash-portfolio-row" style={{ animation: "termIn .3s ease .05s both" }}>

            {/* Balance */}
            <div className="panel">
              <div className="panel-head"><div className="panel-head-dot" />balance</div>
              <div style={{ padding: 14 }}>
                <div style={{ fontSize: 9, color: "var(--t3)", marginBottom: 3 }}>fleet wallet balance</div>
                <div className="cursor-val" style={{ fontSize: 28, fontWeight: 700, color: "var(--t1)", letterSpacing: -1, lineHeight: 1 }}>
                  {fleetBalance === null ? "loading..." : `$${fleetUSDC.toFixed(2)}`}
                </div>
                <div style={{ fontSize: 10, color: "var(--p-dim)", marginBottom: 12 }}>
                  {fleetBalance !== null ? `${fleetOKB.toFixed(4)} OKB` : ""} · X Layer testnet
                </div>
                <div style={{ height: 1, background: "var(--border)", margin: "8px 0" }} />
                {[
                  { label: "USDC (stablecoin)",   val: fleetBalance !== null ? `$${fleetUSDC.toFixed(2)}` : "—", color: "var(--t1)" },
                  { label: "OKB (gas)",            val: fleetBalance !== null ? `${fleetOKB.toFixed(4)} OKB` : "—", color: "var(--p-dim)" },
                  { label: "spent today",          val: stats ? formatUSD(stats.totalSpentToday) : "—", color: "var(--t1)" },
                  { label: "bots active",          val: agents.length > 0 ? `${agents.filter(a=>a.status==="active").length}/${agents.length}` : "—", color: "var(--p-dim)" },
                ].map(({ label, val, color }) => (
                  <div key={label} style={{ display: "flex", justifyContent: "space-between", padding: "4px 0" }}>
                    <span style={{ fontSize: 10, color: "var(--t3)" }}>{label}</span>
                    <span style={{ fontSize: 10, fontWeight: 500, color }}>{val}</span>
                  </div>
                ))}
              </div>
            </div>

            {/* Realized PnL mini chart */}
            <div className="panel">
              <div className="panel-head">
                <div className="panel-head-dot" />guard stats
                <div style={{ marginLeft: "auto", display: "flex", gap: 4 }}>
                  {["1d","7d","30d"].map((r, i) => (
                    <button key={r} style={{
                      fontFamily: "var(--mono)", fontSize: 9, padding: "2px 7px", cursor: "pointer", borderRadius: 1,
                      background: i===1 ? "rgba(212,255,0,.06)" : "none",
                      color:      i===1 ? "#d4ff00" : "var(--t3)",
                      border:     i===1 ? "1px solid rgba(212,255,0,.2)" : "1px solid var(--border)",
                    }}>{r}</button>
                  ))}
                </div>
              </div>
              <div style={{ padding: "12px 14px" }}>
                <div style={{ fontSize: 22, fontWeight: 700, color: "var(--t1)", letterSpacing: "-.5px", marginBottom: 2 }}>
                  {stats ? `${stats.txApprovedToday + denied + (stats.txFlaggedToday ?? 0)}` : "—"} tx
                </div>
                <div style={{ display: "flex", gap: 12, marginBottom: 10 }}>
                  {[
                    { label: "approved", val: stats?.txApprovedToday ?? 0, color: "var(--p-dim)" },
                    { label: "flagged",  val: stats?.txFlaggedToday  ?? 0, color: "var(--amber)" },
                    { label: "blocked",  val: denied,                      color: "var(--red)" },
                  ].map(({ label, val, color }) => (
                    <span key={label} style={{ fontSize: 9, color: "var(--t2)" }}>
                      {label} <span style={{ color }}>{val}</span>
                    </span>
                  ))}
                </div>
                <div style={{ height: 68 }}>
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={miniDisplay.slice(-12)} margin={{ top: 2, right: 2, left: -30, bottom: 0 }}>
                      <CartesianGrid strokeDasharray="2 2" stroke="rgba(255,255,255,.04)" />
                      <XAxis dataKey="time" tick={{ fill: "#555", fontSize: 9 }} axisLine={false} tickLine={false} interval="preserveStartEnd" />
                      <YAxis tick={false} axisLine={false} tickLine={false} />
                      <Line type="monotone" dataKey="total" stroke="rgba(255,255,255,0.6)" strokeWidth={1.5} dot={false} />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              </div>
            </div>

            {/* Performance */}
            <div className="panel">
              <div className="panel-head"><div className="panel-head-dot" />performance</div>
              <div style={{ padding: "10px 14px", display: "flex", flexDirection: "column" }}>
                {(() => {
                  const totalTx   = (stats?.txApprovedToday ?? 0) + denied + (stats?.txFlaggedToday ?? 0);
                  const approvalRate = totalTx > 0 ? Math.round(((stats?.txApprovedToday ?? 0) / totalTx) * 100) : 100;
                  const bestAgent = agents.length > 0
                    ? agents.reduce((b, a) => a.spentToday > b.spentToday ? a : b, agents[0])
                    : null;
                  const mostActive = agents.length > 0
                    ? agents.reduce((b, a) => a.txCount > b.txCount ? a : b, agents[0])
                    : null;
                  const riskLabel = approvalRate >= 80 ? "LOW" : approvalRate >= 60 ? "MED" : "HIGH";
                  const riskScore = Math.round(100 - approvalRate);
                  return [
                    { label: "best agent",       val: bestAgent?.name.split(" ")[0] ?? "—", meta: bestAgent ? `$${(bestAgent.spentToday/100).toFixed(0)} today` : "" },
                    { label: "most active",      val: mostActive?.name.split(" ")[0] ?? "—", meta: `${totalTx} tx today` },
                    { label: "approval rate",    val: `${approvalRate}%`, meta: "approved", color: approvalRate>=80?"var(--p-dim)":"var(--amber)" },
                    { label: "risk score",       val: `${riskLabel} ${riskScore}`, meta: "portfolio avg", color: riskLabel==="LOW"?"var(--p-dim)":"var(--red)" },
                    { label: "onchain txns",     val: `${totalTx}`, meta: "X Layer logged" },
                  ];
                })().map(({ label, val, meta, color }) => (
                  <div key={label} style={{
                    display: "flex", alignItems: "baseline", justifyContent: "space-between",
                    padding: "7px 0", borderBottom: "1px solid var(--border)",
                  }}>
                    <span style={{ fontSize: 9, color: "var(--t3)", letterSpacing: ".5px", flexShrink: 0 }}>{label}</span>
                    <span style={{ fontSize: 11, fontWeight: 500, color: color ?? "var(--t1)", textAlign: "right", display: "flex", alignItems: "baseline", gap: 5 }}>
                      {val}
                      <span style={{ fontSize: 9, color: "var(--t3)", fontWeight: 400 }}>{meta}</span>
                    </span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>

        {/* ── Stat Strip ── */}
        <div className="dash-stat-strip" style={{ animation: "termIn .3s ease .1s both" }}>
          {[
            { label: "agents",     val: stats?.totalAgents ?? agents.length,         sub: `${agents.filter(a=>a.status==="active").length} active now`, color: "var(--t1)"  },
            { label: "active",     val: agents.filter(a=>a.status==="active").length, sub: "running",      color: "var(--t1)"  },
            { label: "spent today",val: stats ? formatUSD(stats.totalSpentToday) : "$0", sub: "all agents", color: "var(--t1)" },
            { label: "monthly",    val: stats ? formatUSD(monthly) : "$0",            sub: "this month",   color: "var(--t1)"  },
            { label: "denied",     val: denied,                                       sub: "blocked today", color: denied > 0 ? "var(--red)" : "var(--t1)" },
            { label: "reset in",   val: resetIn,                                      sub: "daily budget", color: "var(--t1)"  },
          ].map(({ label, val, sub, color }) => (
            <div key={label} className="stat">
              <div className="stat-label">{label}</div>
              <div className="stat-value" style={{ color }}>{val}</div>
              <div className="stat-sub">{sub}</div>
            </div>
          ))}
        </div>

        {/* ── Mid Row ── */}
        <div className="dash-mid-row" style={{ animation: "termIn .3s ease .15s both" }}>
          {/* Left: Spending Over Time + Realized PnL */}
          <div className="dash-mid-left">
            <SpendingChart
              data={display}
              range={chartRange}
              onRangeChange={setRange}
              agentLabels={Object.fromEntries(agents.map(a => [a.name, a.name]))}
            />
            <PnlChart />
          </div>
          {/* Right: Live Trade Feed */}
          <TradeFeed />
        </div>

        {/* ── Agent Grid ── */}
        <div style={{ animation: "termIn .3s ease .2s both" }}>
          <div className="sec-header">agent fleet</div>
          {agents.length === 0 ? (
            <div className="dash-agent-grid">
              {Array.from({ length: 4 }, (_, i) => (
                <div key={i} style={{ background: "var(--bg1)", border: "1px solid var(--border)", borderRadius: "var(--r)", height: 220, padding: 12, display: "flex", alignItems: "center", justifyContent: "center" }}>
                  <span style={{ fontFamily: "var(--mono)", fontSize: 10, color: "var(--t3)" }}>loading...</span>
                </div>
              ))}
            </div>
          ) : (
            <div className="dash-agent-grid">
              {agents.map(a => (
                <AgentCard key={a.id} agent={a} onKill={kill} onResume={resume} onPause={pause} />
              ))}
            </div>
          )}
        </div>

        {/* ── Bottom Row ── */}
        <div className="dash-bottom-row" style={{ animation: "termIn .3s ease .25s both" }}>
          <TopDomains />
          <BlockReasons />
          <EmergencyPanel agents={agents} onKillAll={killAll} onResumeAll={resumeAll} />
        </div>

      </div>
    </div>
  );
}

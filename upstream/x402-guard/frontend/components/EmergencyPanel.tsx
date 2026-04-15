"use client";
import { useState, useRef } from "react";
import { Agent } from "@/lib/api";

interface Props { agents: Agent[]; onKillAll: () => void; onResumeAll: () => void; }

const DEMO_STEPS = [
  { delay: 0,    color: "var(--amber)", text: "ANOMALY DETECTED — agent-beta spending spike" },
  { delay: 1500, color: "var(--red)",   text: "GUARD BLOCKED: $26.00 exceeds per_tx limit $25" },
  { delay: 3000, color: "var(--amber)", text: "POLICY ENGINE: escalating to KILL SWITCH" },
  { delay: 4500, color: "var(--red)",   text: "KILL SWITCH ACTIVATED — agent-beta terminated" },
  { delay: 6000, color: "var(--t2)",    text: "AUDIT LOG: onchain record written to X Layer testnet" },
  { delay: 8000, color: "var(--t1)",    text: "SYSTEM SAFE — 3 agents running, 1 terminated" },
];

export default function EmergencyPanel({ agents, onKillAll, onResumeAll }: Props) {
  const active  = agents.filter(a => a.status === "active").length;
  const paused  = agents.filter(a => a.status === "paused").length;
  const blocked = agents.filter(a => a.status === "blocked").length;

  const [lastKill,   setLastKill]   = useState<string | null>(null);
  const [lastResume, setLastResume] = useState<string | null>(null);
  const [demoRunning, setDemoRunning] = useState(false);
  const [demoLogs, setDemoLogs] = useState<{ color: string; text: string }[]>([]);
  const logRef = useRef<HTMLDivElement>(null);
  const timers = useRef<ReturnType<typeof setTimeout>[]>([]);

  function timeAgo(iso: string) {
    const d = Math.floor((Date.now() - new Date(iso).getTime()) / 1000);
    if (d < 60) return `${d}s ago`;
    if (d < 3600) return `${Math.floor(d/60)}m ago`;
    return `${Math.floor(d/3600)}h ago`;
  }

  function runDemo() {
    if (demoRunning) return;
    setDemoRunning(true);
    setDemoLogs([]);
    timers.current.forEach(clearTimeout);
    timers.current = [];

    DEMO_STEPS.forEach(({ delay, color, text }, i) => {
      const t = setTimeout(() => {
        setDemoLogs(prev => {
          const next = [...prev, { color, text }];
          setTimeout(() => { if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight; }, 30);
          return next;
        });
        if (i === DEMO_STEPS.length - 1) {
          const clear = setTimeout(() => { setDemoLogs([]); setDemoRunning(false); }, 4000);
          timers.current.push(clear);
        }
      }, delay);
      timers.current.push(t);
    });
  }

  return (
    <div className="panel" style={{ display: "flex", flexDirection: "column" }}>
      <div className="panel-head">
        <div className="panel-head-dot" style={{ background: "var(--red)" }} />
        <span style={{ color: "var(--red)" }}>emergency</span>
      </div>
      <div style={{ padding: 14, display: "flex", flexDirection: "column", alignItems: "center", gap: 10, flex: 1 }}>
        {/* Status */}
        <div style={{ width: "100%", display: "flex", flexDirection: "column", gap: 4, marginBottom: 4 }}>
          {[
            { label: "active agents",  val: active,  color: "var(--t1)" },
            { label: "paused agents",  val: paused,  color: "var(--t1)" },
            { label: "blocked agents", val: blocked, color: "var(--red)" },
          ].map(({ label, val, color }) => (
            <div key={label} style={{ display: "flex", justifyContent: "space-between", fontSize: 9 }}>
              <span style={{ color: "var(--t3)" }}>{label}</span>
              <span style={{ color, fontWeight: 500 }}>{val}</span>
            </div>
          ))}
        </div>

        <div style={{ height: 1, background: "var(--border)", width: "100%", margin: "4px 0" }} />

        <div style={{ fontSize: 9, color: "var(--t3)", textAlign: "center", lineHeight: 1.7, letterSpacing: ".2px" }}>
          kills all active agents immediately.<br />
          pending txns cancelled.<br />
          manual resume required per agent.
        </div>

        <button
          onClick={() => { if (window.confirm("Kill ALL agents?")) { onKillAll(); setLastKill(new Date().toISOString()); } }}
          className="btn-kill-all">
          [ KILL ALL AGENTS ]
        </button>

        <button
          onClick={() => { if (window.confirm("Resume ALL agents?")) { onResumeAll(); setLastResume(new Date().toISOString()); } }}
          style={{
            width: "100%", padding: "8px",
            background: "none", border: "1px solid var(--border)",
            borderRadius: "var(--r)", color: "var(--t2)",
            fontFamily: "var(--mono)", fontSize: 11, fontWeight: 700,
            letterSpacing: 1, textTransform: "uppercase", cursor: "pointer",
            transition: "all .2s",
          }}
          onMouseEnter={e => { (e.currentTarget as HTMLButtonElement).style.borderColor = "var(--border2)"; (e.currentTarget as HTMLButtonElement).style.color = "var(--t1)"; }}
          onMouseLeave={e => { (e.currentTarget as HTMLButtonElement).style.borderColor = "var(--border)"; (e.currentTarget as HTMLButtonElement).style.color = "var(--t2)"; }}>
          [ RESUME ALL ]
        </button>

        {/* Demo Scenario Button */}
        <button
          onClick={runDemo}
          disabled={demoRunning}
          style={{
            width: "100%", padding: "8px",
            background: demoRunning ? "rgba(255,171,0,0.08)" : "none",
            border: `1px solid ${demoRunning ? "var(--amber)" : "var(--border)"}`,
            borderRadius: "var(--r)",
            color: demoRunning ? "var(--amber)" : "var(--t3)",
            fontFamily: "var(--mono)", fontSize: 11, fontWeight: 700,
            letterSpacing: 1, textTransform: "uppercase",
            cursor: demoRunning ? "not-allowed" : "pointer",
            transition: "all .2s",
          }}>
          {demoRunning ? "[ RUNNING... ]" : "[ RUN DEMO SCENARIO ]"}
        </button>

        {/* Demo Log Terminal */}
        {demoLogs.length > 0 && (
          <div
            ref={logRef}
            style={{
              width: "100%", maxHeight: 120, overflowY: "auto",
              background: "#020202", border: "1px solid var(--border)",
              borderRadius: "var(--r)", padding: "8px 10px",
              display: "flex", flexDirection: "column", gap: 4,
            }}>
            {demoLogs.map((log, i) => (
              <div key={i} style={{ fontSize: 8, fontFamily: "var(--mono)", color: log.color, lineHeight: 1.5 }}>
                <span style={{ color: "var(--t3)", marginRight: 6 }}>{">"}</span>{log.text}
              </div>
            ))}
          </div>
        )}

        <div style={{ fontSize: 9, color: "var(--t3)", textAlign: "center", letterSpacing: ".3px" }}>
          last kill: {lastKill ? timeAgo(lastKill) : "never"} · last resume: {lastResume ? timeAgo(lastResume) : "never"}
        </div>
      </div>
    </div>
  );
}

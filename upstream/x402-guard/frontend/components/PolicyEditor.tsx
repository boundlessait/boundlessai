"use client";

import { useState, useCallback, KeyboardEvent } from "react";
import { Save, Play, Shield, Zap, TrendingDown, Plus, X, CheckCircle, AlertTriangle, Loader } from "lucide-react";
import SliderInput from "./SliderInput";

export interface PolicyData {
  id?: string;
  agent_id: string;
  name?: string;
  daily_limit: number;
  hourly_limit: number;
  per_tx_limit: number;
  auto_approve_under: number;
  notifications_enabled?: boolean;
  active: boolean;
  whitelist: string[];
  blacklist: string[];
  soft_alert_threshold?: number;
}

const TEMPLATES = {
  Conservative: { daily_limit: 50,  hourly_limit: 20,  per_tx_limit: 5,   auto_approve_under: 0.1, soft_alert_threshold: 0.7 },
  Balanced:     { daily_limit: 150, hourly_limit: 60,  per_tx_limit: 25,  auto_approve_under: 0.5, soft_alert_threshold: 0.8 },
  Aggressive:   { daily_limit: 500, hourly_limit: 200, per_tx_limit: 100, auto_approve_under: 2,   soft_alert_threshold: 0.9 },
};
type TemplateKey = keyof typeof TEMPLATES;

interface SimResult {
  approved: number; soft_alerted: number; blocked: number;
  total_saved: number; false_positive_rate: number; recommendation: string;
  total_transactions_replayed?: number;
}

interface PolicyEditorProps {
  policy: PolicyData;
  onSave: (policy: PolicyData) => Promise<void>;
}

function DomainChips({ label, domains, color, onAdd, onRemove }: {
  label: string; domains: string[]; color: "green" | "red";
  onAdd: (d: string) => void; onRemove: (d: string) => void;
}) {
  const [input, setInput] = useState("");
  const handleKey = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter" && input.trim()) { e.preventDefault(); onAdd(input.trim()); setInput(""); }
  };
  const col = color === "green" ? { bg: "rgba(0,230,118,0.08)", border: "rgba(0,230,118,0.25)", text: "var(--p-dim)" }
                                : { bg: "var(--red-dim)",       border: "rgba(180,50,50,.3)",    text: "var(--red)" };
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
      <span style={{ fontSize: 9, color: "var(--t3)", textTransform: "uppercase", letterSpacing: 0.5 }}>{label}</span>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 4, minHeight: 24 }}>
        {domains.map((d) => (
          <span key={d} style={{ display: "inline-flex", alignItems: "center", gap: 4, fontSize: 9,
            padding: "2px 6px", borderRadius: 2, background: col.bg, border: `1px solid ${col.border}`, color: col.text,
            fontFamily: "var(--mono)" }}>
            {d}
            <button type="button" onClick={() => onRemove(d)} style={{ cursor: "pointer", color: col.text, background: "none", border: "none", padding: 0 }}>
              <X size={9} />
            </button>
          </span>
        ))}
        {domains.length === 0 && <span style={{ fontSize: 9, color: "var(--t3)" }}>none</span>}
      </div>
      <div style={{ display: "flex", gap: 6 }}>
        <input type="text" value={input} onChange={(e) => setInput(e.target.value)} onKeyDown={handleKey}
          placeholder="domain.com + Enter"
          style={{ flex: 1, padding: "4px 8px", borderRadius: 2, background: "var(--bg3)",
            border: "1px solid var(--border2)", color: "var(--t1)", fontFamily: "var(--mono)", fontSize: 10, outline: "none" }} />
        <button type="button" onClick={() => { if (input.trim()) { onAdd(input.trim()); setInput(""); } }}
          style={{ display: "flex", alignItems: "center", gap: 4, fontSize: 9, padding: "4px 8px", borderRadius: 2,
            background: col.bg, border: `1px solid ${col.border}`, color: col.text, cursor: "pointer", fontFamily: "var(--mono)" }}>
          <Plus size={10} />add
        </button>
      </div>
    </div>
  );
}

export default function PolicyEditor({ policy, onSave }: PolicyEditorProps) {
  const [form, setForm]           = useState<PolicyData>({ ...policy });
  const [saving, setSaving]       = useState(false);
  const [simulating, setSimulating] = useState(false);
  const [simResult, setSimResult] = useState<SimResult | null>(null);
  const [saveSuccess, setSaveSuccess] = useState(false);
  const [error, setError]         = useState<string | null>(null);

  const update = useCallback(<K extends keyof PolicyData>(key: K, value: PolicyData[K]) => {
    setForm((prev) => ({ ...prev, [key]: value }));
    setSaveSuccess(false); setError(null);
  }, []);

  const applyTemplate = (name: TemplateKey) => setForm((prev) => ({ ...prev, ...TEMPLATES[name] }));

  const handleSave = async () => {
    setSaving(true); setError(null);
    try {
      await onSave(form);
      setSaveSuccess(true);
      setTimeout(() => setSaveSuccess(false), 3000);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Save failed");
    } finally { setSaving(false); }
  };

  const handleSimulate = async () => {
    setSimulating(true); setSimResult(null); setError(null);
    try {
      const res = await fetch("/api/ai/simulate", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          agent_id: form.agent_id, days_back: 30,
          policy: {
            daily_limit: form.daily_limit, hourly_limit: form.hourly_limit,
            per_tx_limit: form.per_tx_limit, auto_approve_under: form.auto_approve_under,
            soft_alert_threshold: form.soft_alert_threshold ?? 0.8,
            whitelist: form.whitelist, blacklist: form.blacklist,
          },
        }),
      });
      if (!res.ok) throw new Error(`Simulation failed: ${res.status}`);
      setSimResult(await res.json());
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Simulation error");
    } finally { setSimulating(false); }
  };

  const S = {
    sec:   { background: "var(--bg2)", border: "1px solid var(--border)", borderRadius: "var(--r)", marginBottom: 8 } as React.CSSProperties,
    head:  { padding: "7px 14px", borderBottom: "1px solid var(--border)", fontSize: 9, color: "var(--t3)",
             letterSpacing: 1, textTransform: "uppercase" as const, display: "flex", alignItems: "center", gap: 6 } as React.CSSProperties,
    body:  { padding: "12px 14px", display: "flex", flexDirection: "column" as const, gap: 12 } as React.CSSProperties,
  };

  const templateIcons  = { Conservative: <Shield size={11} />, Balanced: <TrendingDown size={11} />, Aggressive: <Zap size={11} /> };
  const templateColors = {
    Conservative: { bg: "rgba(6,182,212,0.08)",   border: "rgba(6,182,212,0.25)",  text: "#06b6d4" },
    Balanced:     { bg: "rgba(168,85,247,0.08)",  border: "rgba(168,85,247,0.25)", text: "#a855f7" },
    Aggressive:   { bg: "rgba(201,64,64,0.08)",   border: "rgba(201,64,64,0.25)",  text: "var(--red)" },
  };

  return (
    <div style={{ display: "flex", flexDirection: "column" }}>

      {/* ── Agent name ── */}
      <div style={S.sec}>
        <div style={S.head}><div className="panel-head-dot" />agent name</div>
        <div style={S.body}>
          <input type="text" value={form.name ?? ""} onChange={(e) => update("name", e.target.value)}
            placeholder="e.g. Sniper Bot #1"
            style={{ padding: "6px 10px", borderRadius: "var(--r)", background: "var(--bg3)",
              border: "1px solid var(--border2)", color: "var(--t1)", fontFamily: "var(--mono)",
              fontSize: 11, outline: "none", width: "100%" }} />
          <span style={{ fontSize: 9, color: "var(--t3)" }}>updates everywhere — dashboard, charts, policy list</span>
        </div>
      </div>

      {/* ── Quick templates ── */}
      <div style={S.sec}>
        <div style={S.head}><div className="panel-head-dot" />quick templates</div>
        <div style={{ padding: "10px 14px", display: "flex", gap: 6, flexWrap: "wrap" as const }}>
          {(["Conservative", "Balanced", "Aggressive"] as TemplateKey[]).map((name) => {
            const c = templateColors[name];
            return (
              <button key={name} type="button" onClick={() => applyTemplate(name)}
                style={{ display: "flex", alignItems: "center", gap: 5, fontSize: 9, padding: "4px 10px",
                  borderRadius: "var(--r)", background: c.bg, border: `1px solid ${c.border}`,
                  color: c.text, fontFamily: "var(--mono)", cursor: "pointer" }}>
                {templateIcons[name]}{name.toLowerCase()}
              </button>
            );
          })}
        </div>
      </div>

      {/* ── Spending limits ── */}
      <div style={S.sec}>
        <div style={S.head}><div className="panel-head-dot" />spending limits</div>
        <div style={S.body}>
          <SliderInput label="Daily Limit"           value={form.daily_limit}        min={0} step={5}   unit="$" onChange={(v) => update("daily_limit", v)}                                color="purple" />
          <SliderInput label="Hourly Limit"          value={form.hourly_limit}       min={0} step={5}   unit="$" onChange={(v) => update("hourly_limit", v)}                               color="purple" />
          <SliderInput label="Per Transaction Limit" value={form.per_tx_limit}       min={0} step={1}   unit="$" onChange={(v) => update("per_tx_limit", v)}                               color="cyan"   />
          <SliderInput label="Auto Approve Under"    value={form.auto_approve_under} min={0} step={0.1} unit="$" onChange={(v) => update("auto_approve_under", parseFloat(v.toFixed(1)))} color="cyan"   />
        </div>
      </div>

      {/* ── Settings ── */}
      <div style={S.sec}>
        <div style={S.head}><div className="panel-head-dot" />settings</div>
        <div style={S.body}>
          {([
            { label: "Policy Active",         key: "active" as const,                val: form.active },
            { label: "Notifications Enabled", key: "notifications_enabled" as const, val: form.notifications_enabled ?? true },
          ] as const).map(({ label, key, val }) => (
            <div key={key} style={{ display: "flex", justifyContent: "space-between", alignItems: "center",
              padding: "4px 0", borderBottom: "1px solid var(--border)" }}>
              <span style={{ fontSize: 10, color: "var(--t2)" }}>{label}</span>
              <button type="button" onClick={() => update(key, !val as any)}
                style={{ width: 36, height: 18, borderRadius: 9, cursor: "pointer", position: "relative",
                  background: val ? "rgba(0,230,118,0.2)" : "var(--bg3)",
                  border: `1px solid ${val ? "rgba(0,230,118,0.4)" : "var(--border2)"}`, transition: "all .15s" }}>
                <div style={{ position: "absolute", top: 2, width: 12, height: 12, borderRadius: "50%",
                  background: val ? "var(--p-dim)" : "var(--t3)", left: val ? 20 : 2, transition: "all .15s" }} />
              </button>
            </div>
          ))}

          {/* Soft alert threshold */}
          <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
            <div style={{ display: "flex", justifyContent: "space-between" }}>
              <span style={{ fontSize: 9, color: "var(--t3)", textTransform: "uppercase", letterSpacing: 0.5 }}>Soft Alert Threshold</span>
              <span style={{ fontSize: 10, color: "var(--amber)", fontFamily: "var(--mono)" }}>
                {Math.round((form.soft_alert_threshold ?? 0.8) * 100)}%
              </span>
            </div>
            <input type="range" min={50} max={95} step={5}
              value={Math.round((form.soft_alert_threshold ?? 0.8) * 100)}
              onChange={(e) => update("soft_alert_threshold", parseInt(e.target.value) / 100)}
              style={{ width: "100%", accentColor: "var(--amber)" }} />
            <span style={{ fontSize: 9, color: "var(--t3)" }}>alert when spending hits this % of limit</span>
          </div>
        </div>
      </div>

      {/* ── Domain rules ── */}
      <div style={S.sec}>
        <div style={S.head}><div className="panel-head-dot" />domain rules</div>
        <div style={S.body}>
          <DomainChips label="Whitelist (bypasses limits)" domains={form.whitelist} color="green"
            onAdd={(d) => update("whitelist", [...form.whitelist, d])}
            onRemove={(d) => update("whitelist", form.whitelist.filter((x) => x !== d))} />
          <DomainChips label="Blacklist (always blocked)" domains={form.blacklist} color="red"
            onAdd={(d) => update("blacklist", [...form.blacklist, d])}
            onRemove={(d) => update("blacklist", form.blacklist.filter((x) => x !== d))} />
        </div>
      </div>

      {/* ── Simulation ── */}
      <div style={S.sec}>
        <div style={{ ...S.head, justifyContent: "space-between" }}>
          <span style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <div className="panel-head-dot" />policy simulation
          </span>
          <button type="button" onClick={handleSimulate} disabled={simulating}
            style={{ display: "flex", alignItems: "center", gap: 5, fontSize: 9, padding: "3px 10px",
              borderRadius: "var(--r)", background: "rgba(6,182,212,0.08)", border: "1px solid rgba(6,182,212,0.25)",
              color: "#06b6d4", fontFamily: "var(--mono)", cursor: simulating ? "wait" : "pointer", opacity: simulating ? 0.6 : 1 }}>
            {simulating ? <Loader size={10} className="animate-spin" /> : <Play size={10} />}
            {simulating ? "running..." : "[ run simulation ]"}
          </button>
        </div>

        {!simResult && !simulating && (
          <div style={{ padding: "10px 14px", fontSize: 9, color: "var(--t3)" }}>
            replay last 30 days of transactions against this policy config
          </div>
        )}

        {simResult && (
          <div style={S.body}>
            <div style={{ fontSize: 9, color: "var(--t3)", textAlign: "center" }}>
              replayed <span style={{ color: "var(--t1)", fontFamily: "var(--mono)" }}>
                {simResult.total_transactions_replayed ?? simResult.approved + simResult.soft_alerted + simResult.blocked}
              </span> transactions · last 30 days
            </div>

            {(simResult.total_transactions_replayed ?? 1) === 0 ? (
              <div style={{ fontSize: 9, color: "var(--t3)", textAlign: "center", padding: "8px 0" }}>
                [!] no transaction history for this agent
              </div>
            ) : (
              <>
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 6 }}>
                  {[
                    { label: "approved",   value: simResult.approved,     color: "var(--p-dim)" },
                    { label: "soft alert", value: simResult.soft_alerted, color: "var(--amber)" },
                    { label: "blocked",    value: simResult.blocked,       color: "var(--red)"   },
                  ].map(({ label, value, color }) => (
                    <div key={label} style={{ textAlign: "center", padding: "8px 4px", background: "var(--bg3)",
                      border: "1px solid var(--border)", borderRadius: "var(--r)" }}>
                      <div style={{ fontFamily: "var(--mono)", fontSize: 18, fontWeight: 700, color }}>{value}</div>
                      <div style={{ fontSize: 8, color: "var(--t3)", marginTop: 2 }}>{label}</div>
                    </div>
                  ))}
                </div>
                <div style={{ display: "flex", justifyContent: "space-between", fontSize: 9 }}>
                  <span style={{ color: "var(--t3)" }}>saved: <span style={{ color: "var(--p-dim)", fontFamily: "var(--mono)" }}>${simResult.total_saved.toFixed(2)}</span></span>
                  <span style={{ color: "var(--t3)" }}>false positive: <span style={{ color: simResult.false_positive_rate > 0.2 ? "var(--red)" : "var(--p-dim)", fontFamily: "var(--mono)" }}>{(simResult.false_positive_rate * 100).toFixed(1)}%</span></span>
                </div>
                <div style={{ fontSize: 9, color: "var(--t2)", padding: "8px 10px", background: "var(--bg3)",
                  border: "1px solid var(--border)", borderRadius: "var(--r)", lineHeight: 1.6 }}>
                  {simResult.recommendation}
                </div>
              </>
            )}
          </div>
        )}
      </div>

      {/* Error */}
      {error && (
        <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 9, padding: "6px 12px",
          background: "var(--red-dim)", border: "1px solid rgba(180,50,50,.3)", borderRadius: "var(--r)",
          color: "var(--red)", marginBottom: 8, fontFamily: "var(--mono)" }}>
          <AlertTriangle size={10} />[!] {error}
        </div>
      )}

      {/* ── Save button ── */}
      <button type="button" onClick={handleSave} disabled={saving}
        style={{
          width: "100%", display: "flex", alignItems: "center", justifyContent: "center", gap: 6,
          padding: "8px 0", borderRadius: "var(--r)", fontSize: 10, fontFamily: "var(--mono)",
          cursor: saving ? "wait" : "pointer",
          background: saveSuccess ? "rgba(0,230,118,0.1)"   : "rgba(255,255,255,0.04)",
          border:     saveSuccess ? "1px solid rgba(0,230,118,0.3)" : "1px solid var(--border2)",
          color:      saveSuccess ? "var(--p-dim)" : "var(--t1)",
          transition: "all .2s",
        }}>
        {saving ? <Loader size={12} className="animate-spin" /> : saveSuccess ? <CheckCircle size={12} /> : <Save size={12} />}
        {saving ? "saving..." : saveSuccess ? "[+] saved" : "[ save policy ]"}
      </button>
    </div>
  );
}

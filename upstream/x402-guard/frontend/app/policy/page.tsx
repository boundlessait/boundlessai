"use client";

import { useState, useEffect, useCallback } from "react";
import { RefreshCw } from "lucide-react";
import PolicyEditor, { PolicyData } from "@/components/PolicyEditor";

interface BackendPolicy {
  id: string; agent_id: string; name: string;
  daily_limit: number; hourly_limit: number; per_tx_limit: number;
  auto_approve_under: number; active: boolean;
  whitelist: string[]; blacklist: string[];
  soft_alert_threshold?: number;
}

const GREEK: Record<string, string> = {
  "agent-alpha": "α", "agent-beta": "β", "agent-gamma": "γ", "agent-delta": "δ",
};

function toEditor(p: BackendPolicy): PolicyData {
  return { ...p, soft_alert_threshold: p.soft_alert_threshold ?? 0.8, notifications_enabled: true };
}

export default function PolicyPage() {
  const [policies, setPolicies] = useState<BackendPolicy[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch("/api/policies");
      const data: BackendPolicy[] = await res.json();
      setPolicies(data);
    } catch { setPolicies([]); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    if (policies.length && !selectedId) setSelectedId(policies[0].id);
  }, [policies, selectedId]);

  const selected = policies.find(p => p.id === selectedId) ?? null;

  const handleSave = async (updated: PolicyData) => {
    setSaving(true); setMsg("");
    try {
      const body = {
        name: updated.name, daily_limit: updated.daily_limit,
        hourly_limit: updated.hourly_limit, per_tx_limit: updated.per_tx_limit,
        auto_approve_under: updated.auto_approve_under, active: updated.active,
        whitelist: updated.whitelist, blacklist: updated.blacklist,
        soft_alert_threshold: updated.soft_alert_threshold ?? 0.8,
      };
      const isNew = !updated.id || updated.id.startsWith("mock-");
      const res = await fetch(isNew ? "/api/policies" : `/api/policies/${updated.id}`, {
        method: isNew ? "POST" : "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(isNew ? { ...body, agent_id: updated.agent_id } : body),
      });
      if (res.ok) {
        const saved = await res.json();
        setPolicies(prev => {
          const exists = prev.some(p => p.id === saved.id);
          return exists ? prev.map(p => p.id === saved.id ? saved : p) : [...prev, saved];
        });
        setSelectedId(saved.id);
        setMsg("saved");
      } else { setMsg("error"); }
    } catch { setMsg("error"); }
    finally { setSaving(false); setTimeout(() => setMsg(""), 2000); }
  };

  return (
    <div style={{ position: "relative", zIndex: 1 }}>
      {/* Topbar */}
      <header style={{
        height: 44, background: "rgba(2,9,2,0.95)", borderBottom: "1px solid var(--border)",
        display: "flex", alignItems: "center", padding: "0 20px", gap: 12,
        position: "sticky", top: 0, zIndex: 40,
      }}>
        <span style={{ fontSize: 11, color: "var(--t2)" }}>
          root/<span style={{ color: "var(--t1)" }}>policy</span>
        </span>
        {msg && (
          <span style={{ fontSize: 10, color: msg === "saved" ? "var(--p-dim)" : "var(--red)", fontFamily: "var(--mono)" }}>
            {msg === "saved" ? "[+] saved" : "[!] error"}
          </span>
        )}
        <div style={{ marginLeft: "auto" }}>
          <button onClick={load} className="btn" style={{ padding: "3px 8px", fontSize: 10 }}>
            <RefreshCw size={11} className={loading ? "animate-spin" : ""} />
          </button>
        </div>
      </header>

      <div style={{ padding: "16px 20px", display: "grid", gridTemplateColumns: "180px 1fr", gap: 12 }}>

        {/* Agent list */}
        <div className="panel" style={{ height: "fit-content" }}>
          <div className="panel-head">
            <div className="panel-head-dot" />
            agents ({policies.length})
          </div>
          {loading ? (
            <div style={{ padding: 16, fontSize: 10, color: "var(--t3)" }}>loading...</div>
          ) : policies.map(p => {
            const active = p.id === selectedId;
            return (
              <button key={p.id} onClick={() => setSelectedId(p.id)}
                style={{
                  width: "100%", textAlign: "left",
                  padding: "10px 14px", display: "flex", alignItems: "center", gap: 8,
                  background: active ? "rgba(255,255,255,.04)" : "transparent",
                  borderLeft: active ? "2px solid var(--t2)" : "2px solid transparent",
                  borderBottom: "1px solid var(--border)",
                  cursor: "pointer", transition: "all .1s",
                  fontFamily: "var(--mono)",
                }}>
                <span style={{ fontSize: 14, fontWeight: 700, color: active ? "var(--t1)" : "var(--t2)", width: 16 }}>
                  {GREEK[p.agent_id] ?? "?"}
                </span>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: 10, color: active ? "var(--t1)" : "var(--t2)", fontWeight: 500 }}>
                    {p.name || p.agent_id}
                  </div>
                  <div style={{ fontSize: 9, color: "var(--t3)", marginTop: 1, fontFamily: "var(--mono)" }}>
                    {p.agent_id}
                  </div>
                  <div style={{ fontSize: 9, color: p.active ? "var(--p-dim)" : "var(--red)", marginTop: 1 }}>
                    {p.active ? "● active" : "○ inactive"}
                  </div>
                </div>
              </button>
            );
          })}
        </div>

        {/* Editor */}
        <div>
          {selected ? (
            <div className="panel">
              <div className="panel-head">
                <div className="panel-head-dot" />
                {selected.name || selected.agent_id}
                <span style={{ marginLeft: 4, fontSize: 9, color: "var(--t3)", fontFamily: "var(--mono)" }}>— {selected.agent_id}</span>
                {saving && <span style={{ marginLeft: "auto", fontSize: 9, color: "var(--t3)", fontFamily: "var(--mono)" }}>saving...</span>}
              </div>
              <div style={{ padding: 16 }}>
                <PolicyEditor key={selected.id} policy={toEditor(selected)} onSave={handleSave} />
              </div>
            </div>
          ) : (
            <div className="panel" style={{ padding: 40, textAlign: "center" }}>
              <div style={{ fontSize: 10, color: "var(--t3)" }}>
                {loading ? "loading policies..." : "> select an agent to edit policy"}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

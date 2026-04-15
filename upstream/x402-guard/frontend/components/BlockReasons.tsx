"use client";

import { useState, useEffect } from "react";

interface ReasonItem { reason: string; count: number; pct: number; amber?: boolean; }

export default function BlockReasons() {
  const [data, setData] = useState<ReasonItem[]>([]);

  useEffect(() => {
    const load = () => {
      fetch("/api/dashboard/blocks")
        .then(r => r.ok ? r.json() : null)
        .then(d => { if (Array.isArray(d)) setData(d); })
        .catch(() => null);
    };
    load();
    const id = setInterval(load, 10000);
    return () => clearInterval(id);
  }, []);

  const total = data.reduce((s, d) => s + d.count, 0);

  return (
    <div className="panel">
      <div className="panel-head">
        <div className="panel-head-dot" />block reasons
        <span style={{ marginLeft: "auto", fontSize: 9, color: "var(--t3)" }}>
          {total} total
        </span>
      </div>
      {data.map(item => (
        <div key={item.reason} style={{
          display: "flex", alignItems: "center", gap: 8,
          padding: "6px 14px", borderBottom: "1px solid var(--border)",
          opacity: item.count === 0 ? 0.3 : 1,
        }}>
          <span style={{ flex: 1, fontSize: 10, color: "var(--t2)" }}>{item.reason}</span>
          <div style={{ width: 50, height: 2, background: "var(--bg3)", flexShrink: 0 }}>
            <div style={{
              height: "100%", width: `${item.pct}%`,
              background: item.amber ? "var(--amber)" : "var(--red)",
              opacity: .65,
            }} />
          </div>
          <span style={{
            fontFamily: "var(--mono)", fontSize: 10, fontWeight: 700,
            minWidth: 20, textAlign: "right", flexShrink: 0,
            color: item.count === 0 ? "var(--t3)" : item.amber ? "var(--amber)" : "var(--red)",
          }}>{item.count}</span>
        </div>
      ))}
    </div>
  );
}

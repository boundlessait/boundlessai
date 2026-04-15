"use client";

import { useState, useEffect } from "react";
import { formatUSD } from "@/lib/api";

interface DomainItem { domain: string; amount: number; txs: number; }

export default function TopDomains() {
  const [data, setData] = useState<DomainItem[]>([]);

  useEffect(() => {
    const load = () => {
      fetch("/api/dashboard/domains")
        .then(r => r.ok ? r.json() : null)
        .then(d => { if (Array.isArray(d)) setData(d); })
        .catch(() => null);
    };
    load();
    const id = setInterval(load, 10000);
    return () => clearInterval(id);
  }, []);

  const max = Math.max(...data.map(d => d.amount), 1);

  return (
    <div className="panel">
      <div className="panel-head">
        <div className="panel-head-dot" />top domains
        <span style={{ marginLeft: "auto", fontSize: 9, color: "var(--t3)" }}>by spend</span>
      </div>
      {data.map((item, i) => (
        <div key={item.domain} style={{
          display: "flex", alignItems: "center", gap: 8,
          padding: "6px 14px", borderBottom: "1px solid var(--border)",
          transition: "background .1s",
        }}
          onMouseEnter={e => (e.currentTarget as HTMLDivElement).style.background = "var(--p-ghost)"}
          onMouseLeave={e => (e.currentTarget as HTMLDivElement).style.background = "transparent"}
        >
          <span style={{ fontSize: 9, color: "var(--t3)", width: 12, textAlign: "right" }}>{i+1}</span>
          <span style={{ flex: 1, fontSize: 10, color: "var(--t1)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", fontFamily: "var(--mono)" }}>
            {item.domain}
          </span>
          <span style={{ fontSize: 9, color: "var(--t3)", flexShrink: 0 }}>{item.txs}tx</span>
          <div style={{ width: 50, height: 2, background: "var(--bg3)", flexShrink: 0 }}>
            <div style={{ height: "100%", width: `${(item.amount / max) * 100}%`, background: "var(--t2)" }} />
          </div>
          <span style={{ fontFamily: "var(--mono)", fontSize: 10, fontWeight: 500, color: "var(--t1)", minWidth: 44, textAlign: "right", flexShrink: 0 }}>
            {formatUSD(item.amount)}
          </span>
        </div>
      ))}
    </div>
  );
}

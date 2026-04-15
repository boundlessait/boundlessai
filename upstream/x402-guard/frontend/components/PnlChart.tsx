"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import {
  Chart, LineController, LineElement, PointElement, BarController, BarElement,
  LinearScale, CategoryScale, Filler, Tooltip, Legend,
  type Plugin,
} from "chart.js";

Chart.register(LineController, LineElement, PointElement, BarController, BarElement, LinearScale, CategoryScale, Filler, Tooltip, Legend);

interface PnlPoint {
  time:        string;
  approved:    number;
  blocked:     number;
  cumApproved: number;
  cumBlocked:  number;
}

const crosshairPlugin: Plugin = {
  id: "pnl-crosshair",
  afterDraw(chart: any) {
    const { ctx, chartArea, tooltip } = chart;
    if (!tooltip?._active?.length) return;
    const x = tooltip._active[0].element.x;
    ctx.save();
    ctx.beginPath();
    ctx.moveTo(x, chartArea.top);
    ctx.lineTo(x, chartArea.bottom);
    ctx.strokeStyle = "rgba(255,255,255,0.08)";
    ctx.lineWidth = 1;
    ctx.setLineDash([3, 3]);
    ctx.stroke();
    ctx.restore();
  },
};

export default function PnlChart() {
  const canvasRef  = useRef<HTMLCanvasElement>(null);
  const chartRef   = useRef<Chart | null>(null);
  const [data, setData]       = useState<PnlPoint[]>([]);
  const [totalA, setTotalA]   = useState(0);
  const [totalB, setTotalB]   = useState(0);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try {
      const res = await fetch("/api/dashboard/pnl", {
        signal: AbortSignal.timeout(8000),
        cache: "no-store",
      });
      if (!res.ok) return;
      const d: PnlPoint[] = await res.json();
      if (!Array.isArray(d) || d.length === 0) return;
      const nonZero = d.filter(b => b.approved > 0 || b.blocked > 0);
      if (nonZero.length === 0) return;
      setData(d);
      setTotalA(d[d.length - 1]?.cumApproved ?? 0);
      setTotalB(d[d.length - 1]?.cumBlocked  ?? 0);
    } catch {}
    finally { setLoading(false); }
  }, []);

  useEffect(() => {
    load();
    const id = setInterval(load, 8000);
    return () => clearInterval(id);
  }, [load]);

  useEffect(() => {
    if (!canvasRef.current || data.length === 0) return;

    if (chartRef.current) { chartRef.current.destroy(); chartRef.current = null; }

    const labels = data.map(d => d.time);
    const approvedData = data.map(d => d.cumApproved);
    const blockedData  = data.map(d => d.cumBlocked);

    chartRef.current = new Chart(canvasRef.current, {
      type: "line",
      plugins: [crosshairPlugin],
      data: {
        labels,
        datasets: [
          {
            label: "Approved Spend",
            data: approvedData,
            borderColor: "rgba(212,255,0,0.7)",
            backgroundColor: "rgba(212,255,0,0.06)",
            borderWidth: 1.5,
            fill: true,
            tension: 0.3,
            pointRadius: 0,
            pointHoverRadius: 3,
          },
          {
            label: "Blocked",
            data: blockedData,
            borderColor: "rgba(180,50,50,0.7)",
            backgroundColor: "rgba(180,50,50,0.06)",
            borderWidth: 1.5,
            fill: true,
            tension: 0.3,
            pointRadius: 0,
            pointHoverRadius: 3,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: { duration: 400 },
        interaction: { mode: "index", intersect: false },
        plugins: {
          legend: { display: false },
          tooltip: {
            backgroundColor: "rgba(10,14,10,0.92)",
            borderColor: "rgba(255,255,255,0.08)",
            borderWidth: 1,
            titleColor: "#888",
            bodyColor: "#f2f2f2",
            titleFont: { family: "'JetBrains Mono', monospace", size: 10 },
            bodyFont:  { family: "'JetBrains Mono', monospace", size: 11 },
            callbacks: {
              label: (ctx: any) => ` ${ctx.dataset.label}: $${ctx.parsed.y.toFixed(2)}`,
            },
          },
        },
        scales: {
          x: {
            grid: { color: "rgba(255,255,255,0.03)" },
            ticks: { color: "#555", font: { size: 9, family: "'JetBrains Mono', monospace" }, maxTicksLimit: 8 },
          },
          y: {
            grid: { color: "rgba(255,255,255,0.03)" },
            ticks: {
              color: "#555", font: { size: 9, family: "'JetBrains Mono', monospace" },
              callback: (v: any) => `$${v}`,
            },
          },
        },
      },
    });

    return () => { chartRef.current?.destroy(); chartRef.current = null; };
  }, [data]);

  const hasData = totalA > 0 || totalB > 0;

  return (
    <div className="panel" style={{ display: "flex", flexDirection: "column" }}>
      <div className="panel-head">
        <div className="panel-head-dot" />guard activity
        <div style={{ marginLeft: "auto", display: "flex", gap: 12, alignItems: "center" }}>
          {hasData && (
            <>
              <span style={{ fontSize: 9, color: "rgba(212,255,0,0.7)" }}>
                ● approved ${totalA.toFixed(2)}
              </span>
              <span style={{ fontSize: 9, color: "rgba(180,80,80,0.9)" }}>
                ● blocked ${totalB.toFixed(2)}
              </span>
            </>
          )}
          <span style={{ fontSize: 9, color: "var(--t3)" }}>cumulative 24h</span>
        </div>
      </div>

      {loading ? (
        <div style={{ height: 140, display: "flex", alignItems: "center", justifyContent: "center" }}>
          <span style={{ fontSize: 10, color: "var(--t3)" }}>loading guard activity...</span>
        </div>
      ) : !hasData ? (
        <div style={{ height: 140, display: "flex", alignItems: "center", justifyContent: "center", flexDirection: "column", gap: 6 }}>
          <span style={{ fontSize: 10, color: "var(--t3)" }}>no transactions yet today</span>
          <span style={{ fontSize: 9, color: "#444" }}>guard checks will appear here in real-time</span>
        </div>
      ) : (
        <div style={{ padding: "8px 14px 12px", flex: 1 }}>
          <div className="chart-wrap" style={{ height: 130 }}>
            <canvas ref={canvasRef} style={{ display: "block" }} />
          </div>
        </div>
      )}
    </div>
  );
}

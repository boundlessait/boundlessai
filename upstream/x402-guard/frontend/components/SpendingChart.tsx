"use client";

import { useEffect, useRef, useMemo } from "react";
import {
  Chart,
  LineController,
  LineElement,
  PointElement,
  LinearScale,
  CategoryScale,
  Filler,
  Tooltip,
  Legend,
  type ChartData,
  type Plugin,
} from "chart.js";

Chart.register(LineController, LineElement, PointElement, LinearScale, CategoryScale, Filler, Tooltip, Legend);

// ── Dataset color slots (index 0-3) ───────────────────────────────────────────
const SLOT_CFG: Array<{ color: string; width: number; alpha: number; dash?: number[] }> = [
  { color: "#ffffff", width: 1.5, alpha: 0.85 },
  { color: "#888888", width: 1.5, alpha: 0.7  },
  { color: "#555555", width: 1.0, alpha: 0.7  },
  { color: "#333333", width: 1.0, alpha: 0.6, dash: [4, 3] },
];

// ── Crosshair plugin ──────────────────────────────────────────────────────────
const crosshairPlugin: Plugin = {
  id: "crosshair",
  afterDraw(chart) {
    const { ctx, chartArea, tooltip } = chart as any;
    if (!tooltip || !tooltip._active?.length) return;
    const x = tooltip._active[0].element.x;
    ctx.save();
    ctx.beginPath();
    ctx.moveTo(x, chartArea.top);
    ctx.lineTo(x, chartArea.bottom);
    ctx.strokeStyle = "rgba(255,255,255,0.12)";
    ctx.lineWidth = 1;
    ctx.setLineDash([3, 3]);
    ctx.stroke();
    ctx.restore();
  },
};

// ── Types ─────────────────────────────────────────────────────────────────────
type Row = Record<string, number | string>;

interface Props {
  data: Row[];
  range: "6h" | "24h" | "7d";
  onRangeChange: (r: "6h" | "24h" | "7d") => void;
  agentLabels?: Record<string, string>; // key=agentName, val=displayLabel (same now, kept for compat)
}

function hexAlpha(hex: string, opacity: number): string {
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  return `rgba(${r},${g},${b},${opacity})`;
}

export default function SpendingChart({ data, range, onRangeChange, agentLabels = {} }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const chartRef  = useRef<Chart | null>(null);

  const labels = data.map((d) => d.time as string);

  // Derive agent keys dynamically from data (exclude 'time')
  const agentKeys = useMemo(() => {
    if (data.length === 0) return [];
    return Object.keys(data[0]).filter(k => k !== "time");
  }, [data]);

  const chartData: ChartData<"line"> = useMemo(() => ({
    labels,
    datasets: agentKeys.map((key, i) => {
      const cfg = SLOT_CFG[i % SLOT_CFG.length];
      const values = data.map((d) => (d[key] as number) || 0);
      return {
        label: agentLabels[key] ?? key,
        data: values,
        borderColor: hexAlpha(cfg.color, cfg.alpha),
        borderWidth: cfg.width,
        borderDash: cfg.dash ?? [],
        tension: 0.5,
        fill: true,
        backgroundColor: hexAlpha(cfg.color, i === 0 ? 0.05 : 0.025),
        pointRadius: 0,
        pointHoverRadius: 4,
        pointHoverBackgroundColor: cfg.color,
        pointHoverBorderColor: "#080808",
        pointHoverBorderWidth: 2,
      };
    }),
  }), [data, agentKeys]);  // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    chartRef.current?.destroy();

    chartRef.current = new Chart(canvas, {
      type: "line",
      plugins: [crosshairPlugin],
      data: chartData,
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: { duration: 400, easing: "easeInOutQuart" },
        interaction: { mode: "index", intersect: false },
        plugins: {
          legend: { display: false },
          tooltip: {
            backgroundColor: "#141414",
            borderColor: "rgba(255,255,255,0.08)",
            borderWidth: 1,
            padding: 10,
            titleColor: "#444",
            titleFont: { family: "JetBrains Mono", size: 10 },
            bodyFont:  { family: "JetBrains Mono", size: 11 },
            bodyColor: "#fff",
            callbacks: {
              label(ctx) {
                const val = ctx.parsed?.y ?? 0;
                return `  ${ctx.dataset.label}  $${(val / 100).toFixed(2)}`;
              },
            },
          },
        },
        scales: {
          x: {
            grid: { display: false },
            border: { display: false },
            ticks: {
              color: "#444",
              font: { family: "JetBrains Mono", size: 10 },
              maxTicksLimit: 8,
            },
          },
          y: {
            grid: {
              color: "rgba(255,255,255,0.03)",
              drawBorder: false,
            } as any,
            border: { display: false },
            ticks: {
              color: "#444",
              font: { family: "JetBrains Mono", size: 10 },
              callback: (v: any) => v != null ? `$${(Number(v) / 100).toFixed(0)}` : "",
            },
          },
        },
      },
    });

    return () => { chartRef.current?.destroy(); chartRef.current = null; };
  }, [chartData]);

  return (
    <div className="panel" style={{ display: "flex", flexDirection: "column" }}>
      {/* Header */}
      <div className="panel-head">
        <div className="panel-head-dot" />
        spending over time
        <div style={{ marginLeft: "auto", display: "flex", gap: 4 }}>
          {(["6h", "24h", "7d"] as const).map((r) => (
            <button key={r} onClick={() => onRangeChange(r)} style={{
              fontFamily: "var(--mono)", fontSize: 9,
              padding: "2px 7px", cursor: "pointer", borderRadius: 1,
              background: range === r ? "rgba(212,255,0,.06)" : "none",
              color:      range === r ? "#d4ff00" : "var(--t3)",
              border:     range === r ? "1px solid rgba(212,255,0,.2)" : "1px solid var(--border)",
            }}>{r}</button>
          ))}
        </div>
      </div>

      {/* Canvas */}
      <div style={{ padding: "12px 16px 8px" }}>
        <div className="chart-wrap" style={{ height: 180 }}>
          <canvas ref={canvasRef} style={{ display: "block" }} />
        </div>

        {/* Legend — line style */}
        <div style={{ display: "flex", gap: 14, paddingTop: 8, flexWrap: "wrap" }}>
          {agentKeys.map((name, i) => {
            const cfg = SLOT_CFG[i % SLOT_CFG.length];
            return (
              <div key={name} style={{ display: "flex", alignItems: "center", gap: 5 }}>
                <div style={{
                  width: 14,
                  borderTop: cfg.dash
                    ? `2px dashed ${hexAlpha(cfg.color, cfg.alpha)}`
                    : `2px solid ${hexAlpha(cfg.color, cfg.alpha)}`,
                }} />
                <span style={{ fontSize: 10, color: "var(--t2)", fontFamily: "var(--mono)" }}>
                  {agentLabels[name] ?? name}
                </span>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

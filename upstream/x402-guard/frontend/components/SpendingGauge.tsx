"use client";

import { useMemo } from "react";
import { formatUSD } from "@/lib/api";

interface SpendingGaugeProps {
  spent: number;
  limit: number;
  size?: number;
  strokeWidth?: number;
  label?: string;
  showValues?: boolean;
}

export default function SpendingGauge({
  spent, limit, size = 120, strokeWidth = 10, label, showValues = true,
}: SpendingGaugeProps) {
  const pct = useMemo(() => (limit > 0 ? Math.min(100, (spent / limit) * 100) : 0), [spent, limit]);

  const radius       = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;
  const center       = size / 2;
  const arcDegrees   = 270;
  const arcLength    = (circumference * arcDegrees) / 360;
  const fillLength   = (arcLength * pct) / 100;
  const gapLength    = circumference - arcLength;

  const color = pct >= 90 ? "#F6465D" : pct >= 70 ? "#F0A500" : "#0168FF";

  return (
    <div className="flex flex-col items-center gap-1">
      <div className="relative" style={{ width: size, height: size }}>
        <svg width={size} height={size} style={{ transform: "rotate(135deg)" }}>
          {/* Track */}
          <circle cx={center} cy={center} r={radius} fill="none"
            stroke="#1E2733" strokeWidth={strokeWidth} strokeLinecap="round"
            strokeDasharray={`${arcLength} ${gapLength}`} />
          {/* Fill */}
          <circle cx={center} cy={center} r={radius} fill="none"
            stroke={color} strokeWidth={strokeWidth} strokeLinecap="round"
            strokeDasharray={`${fillLength} ${circumference - fillLength}`}
            style={{ transition: "stroke-dasharray 0.6s cubic-bezier(0.4,0,0.2,1), stroke 0.3s ease" }} />
        </svg>
        {/* Center */}
        <div className="absolute inset-0 flex flex-col items-center justify-center" style={{ paddingBottom: "8px" }}>
          <span className="font-bold tabular-nums" style={{ fontSize: size < 100 ? "0.95rem" : "1.2rem", color }}>
            {Math.round(pct)}%
          </span>
          {label && (
            <span style={{ fontSize: size < 100 ? "0.58rem" : "0.65rem", color: "#4A5568" }}>
              {label}
            </span>
          )}
        </div>
      </div>
      {showValues && (
        <p className="text-xs text-center" style={{ color: "#4A5568" }}>
          <span className="font-medium" style={{ color: "#8A9BB0" }}>{formatUSD(spent)}</span>
          {" / "}
          <span>{formatUSD(limit)}</span>
        </p>
      )}
    </div>
  );
}

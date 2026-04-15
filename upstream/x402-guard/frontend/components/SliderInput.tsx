"use client";

import { useId, useState, useEffect } from "react";

interface SliderInputProps {
  label: string;
  value: number;
  min: number;
  max?: number;
  step?: number;
  unit?: string;
  onChange: (value: number) => void;
  color?: "purple" | "cyan"; // kept for compat but remapped to theme colors
}

export default function SliderInput({
  label,
  value,
  min,
  max: maxProp,
  step = 1,
  unit = "",
  onChange,
  color = "purple",
}: SliderInputProps) {
  const id = useId();

  const sliderMax = maxProp !== undefined ? Math.max(maxProp, value) : Math.max(value * 2, 10);
  const pct = sliderMax > min ? Math.min(100, ((value - min) / (sliderMax - min)) * 100) : 0;

  // remap to dashboard theme: purple→t1 (white), cyan→amber
  const accent = color === "cyan" ? "var(--amber)" : "var(--t1)";
  const accentRgb = color === "cyan" ? "255,171,0" : "255,255,255";
  const trackFill = color === "cyan"
    ? "linear-gradient(90deg, rgba(180,120,0,0.7), var(--amber))"
    : "linear-gradient(90deg, rgba(120,120,120,0.5), var(--t2))";

  const [inputVal, setInputVal] = useState(String(value));
  useEffect(() => { setInputVal(String(value)); }, [value]);

  const commitInput = () => {
    const n = parseFloat(inputVal);
    if (!isNaN(n) && n >= min) onChange(n);
    else setInputVal(String(value));
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8 }}>
        <label htmlFor={id} style={{ fontSize: 9, color: "var(--t3)", textTransform: "uppercase", letterSpacing: 0.5, flexShrink: 0 }}>
          {label}
        </label>

        {/* Editable value badge */}
        <div style={{
          display: "flex", alignItems: "center", gap: 2,
          background: "var(--bg3)", border: "1px solid var(--border2)",
          borderRadius: "var(--r)", padding: "2px 7px",
        }}>
          {unit === "$" && <span style={{ color: accent, fontSize: 11, fontWeight: 700 }}>$</span>}
          <input
            type="number"
            value={inputVal}
            min={min}
            step={step}
            onChange={(e) => setInputVal(e.target.value)}
            onBlur={commitInput}
            onKeyDown={(e) => e.key === "Enter" && commitInput()}
            style={{
              width: Math.max(36, inputVal.length * 8 + 8),
              background: "transparent", border: "none", outline: "none",
              color: accent, fontSize: 11, fontWeight: 700,
              fontFamily: "var(--mono)", textAlign: "right",
            }}
          />
          {unit !== "$" && unit && <span style={{ color: accent, fontSize: 11, fontWeight: 700 }}>{unit}</span>}
        </div>
      </div>

      {/* Slider track */}
      <div style={{ position: "relative", display: "flex", alignItems: "center", height: 20 }}>
        <div style={{ position: "absolute", width: "100%", height: 2, background: "var(--border2)", borderRadius: 1 }} />
        <div style={{ position: "absolute", height: 2, borderRadius: 1, width: `${pct}%`, background: trackFill, transition: "width .1s" }} />
        <input
          id={id}
          type="range"
          min={min}
          max={sliderMax}
          step={step}
          value={Math.min(value, sliderMax)}
          onChange={(e) => onChange(Number(e.target.value))}
          style={{ position: "absolute", width: "100%", appearance: "none", background: "transparent", cursor: "pointer",
            ["--acc" as string]: accent, ["--acc-rgb" as string]: accentRgb }}
        />
      </div>

      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 8, color: "var(--t3)" }}>
        <span>{unit === "$" ? `$${min}` : `${min}${unit}`}</span>
        <span>type to set any value</span>
      </div>

      <style>{`
        #${CSS.escape(id)} { height: 20px; outline: none; }
        #${CSS.escape(id)}::-webkit-slider-thumb {
          -webkit-appearance: none; appearance: none;
          width: 14px; height: 14px; border-radius: 50%;
          background: var(--acc); border: 2px solid var(--bg);
          box-shadow: 0 0 0 2px rgba(var(--acc-rgb),.3);
          cursor: pointer; transition: box-shadow .15s;
        }
        #${CSS.escape(id)}::-webkit-slider-thumb:hover {
          box-shadow: 0 0 0 4px rgba(var(--acc-rgb),.2);
        }
        #${CSS.escape(id)}::-moz-range-thumb {
          width: 14px; height: 14px; border-radius: 50%;
          background: var(--acc); border: 2px solid var(--bg);
          box-shadow: 0 0 0 2px rgba(var(--acc-rgb),.3); cursor: pointer;
        }
        #${CSS.escape(id)}::-moz-range-track { background: transparent; }
        input[type=number]::-webkit-inner-spin-button,
        input[type=number]::-webkit-outer-spin-button { -webkit-appearance: none; }
      `}</style>
    </div>
  );
}

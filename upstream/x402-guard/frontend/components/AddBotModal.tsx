"use client";

import { useState } from "react";
import { X } from "lucide-react";

const BOT_TYPES = [
  { id: "sniper",     label: "Sniper Bot",     desc: "Fast token sniping on launch" },
  { id: "arbitrage",  label: "Arbitrage Bot",   desc: "Cross-DEX price difference" },
  { id: "prediction", label: "Prediction Bot",  desc: "AI market prediction + trading" },
  { id: "sentiment",  label: "Sentiment Bot",   desc: "Social/news sentiment trading" },
  { id: "custom",     label: "Custom Bot",      desc: "Define your own limits" },
];

interface Props {
  onClose: () => void;
  onAdd: (bot: {
    name: string; agent_id: string; bot_type: string;
    wallet_address: string; description: string;
    daily_limit: number; hourly_limit: number; per_tx_limit: number;
  }) => Promise<void>;
}

export default function AddBotModal({ onClose, onAdd }: Props) {
  const [step, setStep]       = useState<1|2>(1);
  const [botType, setBotType] = useState("");
  const [name, setName]       = useState("");
  const [agentId, setAgentId] = useState("");
  const [wallet, setWallet]   = useState("");
  const [dailyLimit, setDaily]  = useState(200);
  const [hourlyLimit, setHourly] = useState(80);
  const [perTxLimit, setPerTx]  = useState(20);
  const [saving, setSaving]   = useState(false);
  const [err, setErr]         = useState("");

  const selectedType = BOT_TYPES.find(b => b.id === botType);

  // Pre-fill limits based on bot type
  const selectType = (id: string) => {
    setBotType(id);
    const presets: Record<string, [number, number, number]> = {
      sniper:     [500, 200, 50],
      arbitrage:  [1000, 400, 100],
      prediction: [200, 80, 20],
      sentiment:  [100, 40, 10],
      custom:     [200, 80, 20],
    };
    const [d, h, p] = presets[id] ?? [200, 80, 20];
    setDaily(d); setHourly(h); setPerTx(p);
  };

  const handleSubmit = async () => {
    if (!name.trim() || !agentId.trim()) { setErr("Name and Bot ID are required"); return; }
    if (agentId.includes(" "))           { setErr("Bot ID cannot have spaces"); return; }
    setSaving(true); setErr("");
    try {
      await onAdd({
        name: name.trim(),
        agent_id: agentId.trim().toLowerCase(),
        bot_type: botType || "custom",
        wallet_address: wallet.trim(),
        description: selectedType?.desc ?? "",
        daily_limit: dailyLimit,
        hourly_limit: hourlyLimit,
        per_tx_limit: perTxLimit,
      });
      onClose();
    } catch (e: any) {
      setErr(e.message ?? "Failed to add bot");
    } finally { setSaving(false); }
  };

  const panel: React.CSSProperties = {
    background: "var(--bg1)", border: "1px solid var(--border2)",
    borderRadius: "var(--r)", padding: 24, width: 480, maxWidth: "95vw",
  };

  return (
    <div style={{
      position: "fixed", inset: 0, zIndex: 200,
      background: "rgba(0,0,0,0.75)", backdropFilter: "blur(4px)",
      display: "flex", alignItems: "center", justifyContent: "center",
    }} onClick={e => { if (e.target === e.currentTarget) onClose(); }}>
      <div style={panel}>
        {/* Header */}
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 20 }}>
          <div>
            <div style={{ fontFamily: "var(--mono)", fontSize: 13, fontWeight: 700, color: "var(--t1)" }}>
              [ add new bot ]
            </div>
            <div style={{ fontFamily: "var(--sans)", fontSize: 10, color: "var(--t3)", marginTop: 2 }}>
              step {step} of 2
            </div>
          </div>
          <button onClick={onClose} className="btn" style={{ padding: "4px 6px" }}>
            <X size={14} />
          </button>
        </div>

        {step === 1 && (
          <>
            <div style={{ fontFamily: "var(--sans)", fontSize: 10, color: "var(--t3)", marginBottom: 10, letterSpacing: "0.08em", textTransform: "uppercase" }}>
              Select bot type
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              {BOT_TYPES.map(bt => (
                <button key={bt.id} onClick={() => selectType(bt.id)}
                  style={{
                    display: "flex", alignItems: "center", gap: 12,
                    padding: "10px 14px", borderRadius: "var(--r)", cursor: "pointer",
                    background: botType === bt.id ? "rgba(255,255,255,.06)" : "var(--bg2)",
                    border: `1px solid ${botType === bt.id ? "var(--border2)" : "var(--border)"}`,
                    borderLeft: botType === bt.id ? "3px solid var(--t2)" : "3px solid transparent",
                    textAlign: "left",
                  }}>
                  <div>
                    <div style={{ fontFamily: "var(--mono)", fontSize: 11, fontWeight: 700, color: botType === bt.id ? "var(--t1)" : "var(--t2)" }}>
                      {bt.label}
                    </div>
                    <div style={{ fontFamily: "var(--sans)", fontSize: 10, color: "var(--t3)", marginTop: 2 }}>
                      {bt.desc}
                    </div>
                  </div>
                  {botType === bt.id && (
                    <span style={{ marginLeft: "auto", fontFamily: "var(--mono)", fontSize: 10, color: "var(--t2)" }}>
                      selected
                    </span>
                  )}
                </button>
              ))}
            </div>
            <button
              onClick={() => botType && setStep(2)}
              className="btn" disabled={!botType}
              style={{ marginTop: 16, width: "100%", padding: "10px", fontSize: 11,
                opacity: botType ? 1 : 0.4,
                background: botType ? "rgba(255,255,255,.08)" : "transparent",
                borderColor: botType ? "var(--border2)" : "var(--border)",
                color: botType ? "var(--t1)" : "var(--t3)",
              }}>
              next →
            </button>
          </>
        )}

        {step === 2 && (
          <>
            {/* Bot name & ID */}
            <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
              <div>
                <label style={{ fontFamily: "var(--sans)", fontSize: 10, color: "var(--t3)", letterSpacing: "0.08em", textTransform: "uppercase" }}>
                  Bot Name
                </label>
                <input value={name} onChange={e => setName(e.target.value)}
                  placeholder="e.g. Sniper Bot #1"
                  style={{
                    display: "block", width: "100%", marginTop: 6,
                    background: "var(--bg3)", border: "1px solid var(--border)",
                    borderRadius: "var(--r)", padding: "8px 12px",
                    fontFamily: "var(--mono)", fontSize: 12, color: "var(--t1)",
                    outline: "none",
                  }} />
              </div>

              <div>
                <label style={{ fontFamily: "var(--sans)", fontSize: 10, color: "var(--t3)", letterSpacing: "0.08em", textTransform: "uppercase" }}>
                  Bot ID <span style={{ color: "var(--t3)", fontSize: 9 }}>(used in API calls)</span>
                </label>
                <input value={agentId} onChange={e => setAgentId(e.target.value.toLowerCase().replace(/\s/g, "-"))}
                  placeholder="e.g. sniper-bot-1"
                  style={{
                    display: "block", width: "100%", marginTop: 6,
                    background: "var(--bg3)", border: "1px solid var(--border)",
                    borderRadius: "var(--r)", padding: "8px 12px",
                    fontFamily: "var(--mono)", fontSize: 12, color: "var(--t1)",
                    outline: "none",
                  }} />
              </div>

              <div>
                <label style={{ fontFamily: "var(--sans)", fontSize: 10, color: "var(--t3)", letterSpacing: "0.08em", textTransform: "uppercase" }}>
                  Bot Wallet Address <span style={{ color: "var(--t3)", fontSize: 9 }}>(optional — for balance display)</span>
                </label>
                <input value={wallet} onChange={e => setWallet(e.target.value)}
                  placeholder="0x..."
                  style={{
                    display: "block", width: "100%", marginTop: 6,
                    background: "var(--bg3)", border: "1px solid var(--border)",
                    borderRadius: "var(--r)", padding: "8px 12px",
                    fontFamily: "var(--mono)", fontSize: 11, color: "var(--t1)",
                    outline: "none",
                  }} />
              </div>

              {/* Spending limits */}
              <div style={{ borderTop: "1px solid var(--border)", paddingTop: 12 }}>
                <div style={{ fontFamily: "var(--sans)", fontSize: 10, color: "var(--t3)", letterSpacing: "0.08em", textTransform: "uppercase", marginBottom: 10 }}>
                  Spending Limits (USD)
                </div>
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 8 }}>
                  {[
                    { label: "Daily",   value: dailyLimit,  set: setDaily,  hint: "/day" },
                    { label: "Hourly",  value: hourlyLimit, set: setHourly, hint: "/hr"  },
                    { label: "Per Tx",  value: perTxLimit,  set: setPerTx,  hint: "/tx"  },
                  ].map(({ label, value, set, hint }) => (
                    <div key={label}>
                      <label style={{ fontFamily: "var(--sans)", fontSize: 9, color: "var(--t3)" }}>
                        {label}
                      </label>
                      <div style={{ display: "flex", alignItems: "center", gap: 4, marginTop: 4 }}>
                        <span style={{ fontFamily: "var(--mono)", fontSize: 10, color: "var(--t3)" }}>$</span>
                        <input type="number" value={value}
                          onChange={e => set(Number(e.target.value))}
                          style={{
                            flex: 1, background: "var(--bg3)", border: "1px solid var(--border)",
                            borderRadius: "var(--r)", padding: "6px 8px",
                            fontFamily: "var(--mono)", fontSize: 11, color: "var(--t1)",
                            outline: "none", width: "100%",
                          }} />
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {err && (
                <div style={{ fontFamily: "var(--sans)", fontSize: 10, color: "var(--red)", background: "var(--red-dim)", padding: "8px 12px", borderRadius: "var(--r)" }}>
                  [!] {err}
                </div>
              )}

              <div style={{ display: "flex", gap: 8, marginTop: 4 }}>
                <button onClick={() => setStep(1)} className="btn" style={{ flex: 1, padding: "10px", fontSize: 11 }}>
                  ← back
                </button>
                <button onClick={handleSubmit} disabled={saving}
                  className="btn"
                  style={{ flex: 2, padding: "10px", fontSize: 11,
                    background: saving ? "transparent" : "rgba(255,255,255,.1)",
                    borderColor: "var(--border2)", color: "var(--t1)",
                  }}>
                  {saving ? "adding..." : "[ add bot ]"}
                </button>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

// ── Decision Journal ──

import { DECISION_TYPE_MAP, DECISION_COLORS, DECISION_REASONS, FALLBACK_DECISIONS } from '../config.js';

function decodeDecisionType(hex) {
  return DECISION_TYPE_MAP[hex] || '未知 (' + hex.slice(0, 10) + '...)';
}

export async function loadDecisions(count, rpcAssembler) {
  const el = document.getElementById('journal-timeline');
  if (count === 0) {
    el.innerHTML = '<div class="text-center py-8 text-gray-600 text-xs">暂无决策记录</div>';
    return;
  }
  let html = '';
  let rpcFailed = false;
  const start = Math.max(1, count - 9);
  // Probe: try the first RPC call; if it fails, skip straight to fallback
  try {
    await Promise.race([
      rpcAssembler.getDecision(count),
      new Promise((_, rej) => setTimeout(() => rej(new Error('timeout')), 3000)),
    ]);
  } catch (e) { rpcFailed = true; }
  if (!rpcFailed) {
    for (let i = count; i >= start; i--) {
      try {
        const d = await Promise.race([
          rpcAssembler.getDecision(i),
          new Promise((_, rej) => setTimeout(() => rej(new Error('timeout')), 3000)),
        ]);
        const dt = new Date(Number(d.timestamp) * 1000);
        const typeHex = d.decisionType;
        const typeName = decodeDecisionType(typeHex);
        const typeColor = DECISION_COLORS[typeName] || 'text-gray-400';
        const reasoning = DECISION_REASONS[typeName] || '链上决策记录';
        html += renderDecisionEntry(Number(d.strategyId), dt, typeName, typeColor, reasoning, d.reasoningHash);
      } catch (e) { break; }
    }
  }
  // If RPC failed or loaded nothing, use fallback
  if (html === '') {
    html += '<div class="mb-3"><span class="data-src sim" style="font-size:10px">缓存数据 — RPC 不可达时显示最近链上快照</span></div>';
    FALLBACK_DECISIONS.forEach(d => {
      const dt = new Date(d.timestamp * 1000);
      const typeName = decodeDecisionType(d.decisionType);
      const typeColor = DECISION_COLORS[typeName] || 'text-gray-400';
      const reasoning = DECISION_REASONS[typeName] || '链上决策记录';
      html += renderDecisionEntry(d.strategyId, dt, typeName, typeColor, reasoning, d.reasoningHash);
    });
  }
  el.innerHTML = html || '<div class="text-center py-8 text-gray-600 text-xs">无法加载决策记录</div>';
}

function renderDecisionEntry(strategyId, dt, typeName, typeColor, reasoning, reasoningHash) {
  return `<div class="flex gap-4">
    <div class="timeline-dot" style="${typeColor.includes('cyan') ? 'border-color:#22d3ee' : typeColor.includes('green') ? 'border-color:#4ade80' : typeColor.includes('yellow') ? 'border-color:#facc15' : typeColor.includes('purple') ? 'border-color:#a855f7' : typeColor.includes('pink') ? 'border-color:#ec4899' : ''}"></div>
    <div class="flex-1 pb-4 border-b border-gray-800/30">
      <div class="flex justify-between items-start mb-1">
        <span class="text-xs text-[var(--neon)]">策略 #${strategyId}</span>
        <span class="text-xs text-gray-500">${dt.toLocaleString()}</span>
      </div>
      <p class="text-xs"><span class="${typeColor} font-bold">${typeName}</span></p>
      <p class="text-xs text-gray-400 mt-1">${reasoning}</p>
      <p class="text-xs text-gray-600 mt-1">验证哈希: <span class="font-mono text-gray-700">${reasoningHash.slice(0, 18)}...</span></p>
    </div>
  </div>`;
}

export function init() {
  // Journal is loaded by dashboard refresh cycle
}

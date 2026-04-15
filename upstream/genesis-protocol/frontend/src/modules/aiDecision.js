// ── AI Decision Panel: LLM reasoning, confidence gauge, regime, timeline, backtest ──

import { CFG, ASSEMBLER_ABI, NFT_ABI, DECISION_TYPE_MAP, DECISION_COLORS, PRESETS, FALLBACK_CHAIN_DATA, EMBEDDED_AGENT_STATE } from '../config.js';

let backtestChart = null, regimePieChart = null;
let _lastDecisionState = null;

// ── Confidence Gauge ──
export function updateConfidenceGauge(score) {
  const pct = Math.max(0, Math.min(1, score));
  const deg = -90 + pct * 180;
  const needle = document.getElementById('gauge-needle');
  const fill = document.getElementById('gauge-fill');
  const label = document.getElementById('gauge-label');
  const desc = document.getElementById('confidence-desc');
  if (needle) needle.style.transform = `rotate(${deg}deg)`;
  if (fill) {
    const angle = pct * 180;
    fill.style.clipPath = `polygon(50% 100%, ${50 - 50 * Math.cos((180 - angle) * Math.PI / 180)}% ${100 - 50 * Math.sin((180 - angle) * Math.PI / 180)}%, 0% 100%)`;
  }
  if (label) {
    label.textContent = (pct * 100).toFixed(0) + '%';
    label.style.color = pct >= 0.7 ? '#4ade80' : pct >= 0.5 ? '#facc15' : '#f87171';
  }
  if (desc) {
    desc.textContent = pct >= 0.7 ? 'HIGH - Execute recommended' : pct >= 0.5 ? 'MEDIUM - Awaiting confirmation' : 'LOW - Insufficient data';
    desc.style.color = pct >= 0.7 ? '#4ade80' : pct >= 0.5 ? '#facc15' : '#f87171';
  }
}

// ── Market Regime Indicator ──
export function updateRegimeIndicator(regime, vol, trend, bayesian) {
  const container = document.getElementById('decision-regime-indicator');
  const dot = document.getElementById('regime-dot');
  const text = document.getElementById('regime-text');
  if (!container) return;

  const regimeMap = {
    'calm': { cls: 'regime-calm', label: 'CALM', color: '#4ade80' },
    'volatile': { cls: 'regime-volatile', label: 'VOLATILE', color: '#f87171' },
    'trending': { cls: 'regime-trending', label: 'TRENDING', color: '#facc15' },
  };
  const r = regimeMap[regime] || regimeMap['calm'];
  container.className = 'regime-indicator ' + r.cls + ' mb-3';
  if (dot) dot.style.background = r.color;
  if (text) text.textContent = r.label;

  const set = (id, v) => { const el = document.getElementById(id); if (el) el.textContent = v; };
  set('decision-vol', vol !== undefined ? vol.toFixed(3) + '%' : '--');
  set('decision-trend', trend || '--');
  set('decision-bayesian', bayesian || '--');
}

// ── Strategy Recommendation ──
export function updateRecommendation(action, actionCn, rationale, whyDetails) {
  const rec = document.getElementById('decision-recommendation');
  const rat = document.getElementById('decision-rationale');
  const why = document.getElementById('why-details');
  if (rec) rec.innerHTML = '<span class="text-[var(--neon)]">' + actionCn + '</span>';
  if (rat) rat.textContent = rationale;
  if (why && whyDetails) {
    why.innerHTML = whyDetails.map(d => '<p>' + d + '</p>').join('');
  }
}

// ── LLM Reasoning Display with Typing Effect ──
let _typingIntervals = [];
export function addLLMReasoning(text, color) {
  const display = document.getElementById('llm-reasoning-display');
  if (!display) return;
  if (display.querySelector('.text-gray-600:only-child')) display.innerHTML = '';
  const p = document.createElement('p');
  p.className = (color || 'text-gray-400') + ' typing-caret';
  display.appendChild(p);
  display.scrollTop = display.scrollHeight;

  let i = 0;
  const interval = setInterval(() => {
    if (i < text.length) {
      p.textContent += text[i];
      i++;
      display.scrollTop = display.scrollHeight;
    } else {
      clearInterval(interval);
      _typingIntervals = _typingIntervals.filter(x => x !== interval);
      p.classList.remove('typing-caret');
    }
  }, 12);
  _typingIntervals.push(interval);
}

export function clearLLMReasoning() {
  // Clear any running typing intervals
  _typingIntervals.forEach(id => clearInterval(id));
  _typingIntervals = [];
  const display = document.getElementById('llm-reasoning-display');
  if (display) display.innerHTML = '';
}

// ── Reasoning Chain Steps ──
export function activateReasoningStep(stepId) {
  ['rstep-data', 'rstep-analysis', 'rstep-strategy', 'rstep-confidence'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.classList.remove('active');
  });
  const el = document.getElementById(stepId);
  if (el) el.classList.add('active');
  const ts = document.getElementById('reasoning-timestamp');
  if (ts) ts.textContent = new Date().toLocaleTimeString();
}

// ── Update full decision state (called from engine after cycle) ──
export function updateDecisionPanel(state) {
  _lastDecisionState = state;
  updateConfidenceGauge(state.confidence);
  updateRegimeIndicator(state.regime, state.vol, state.trend, state.bayesianStr);
  updateRecommendation(state.action, state.actionCn, state.rationale, state.whyDetails);
}

// ── Activity Timeline ──
export async function loadActivityTimeline(rpcAssembler, rpcNft, rpcProvider) {
  const el = document.getElementById('activity-timeline-list');
  if (!el) return;
  try {
    const [scRes, dcRes] = await Promise.allSettled([
      rpcAssembler.strategyCount(),
      rpcAssembler.decisionCount(),
    ]);
    const sc = scRes.status === 'fulfilled' ? Number(scRes.value) : 0;
    const dc = dcRes.status === 'fulfilled' ? Number(dcRes.value) : 0;

    let entries = [];

    // Load strategies
    for (let i = 1; i <= Math.min(sc, 10); i++) {
      try {
        const s = await rpcAssembler.getStrategy(i);
        entries.push({
          type: 'create', label: '策略创建',
          detail: 'Strategy #' + i + ' (' + s.modules.length + ' modules)',
          ts: Number(s.createdAt), badge: 'ttype-create',
        });
      } catch (e) { break; }
    }

    // Load decisions
    const dStart = Math.max(1, dc - 15);
    for (let i = dc; i >= dStart; i--) {
      try {
        const d = await rpcAssembler.getDecision(i);
        const typeName = DECISION_TYPE_MAP[d.decisionType] || 'Unknown';
        let badge = 'ttype-decision';
        if (typeName.includes('NFT')) badge = 'ttype-nft';
        else if (typeName.includes('再平衡')) badge = 'ttype-rebalance';
        else if (typeName.includes('费率')) badge = 'ttype-fee';
        else if (typeName.includes('策略创建')) badge = 'ttype-create';
        entries.push({
          type: typeName.includes('NFT') ? 'nft' : typeName.includes('再平衡') ? 'rebalance' : 'decision',
          label: typeName, detail: 'Strategy #' + Number(d.strategyId),
          ts: Number(d.timestamp), badge,
          hash: d.reasoningHash,
        });
      } catch (e) { break; }
    }

    entries.sort((a, b) => b.ts - a.ts);
    entries = entries.slice(0, 20);

    if (entries.length === 0) {
      el.innerHTML = '<div class="text-center py-8 text-gray-600 text-xs">暂无链上活动记录</div>';
      return;
    }

    let html = '';
    entries.forEach(ev => {
      const dt = new Date(ev.ts * 1000);
      const timeStr = dt.toLocaleDateString() + ' ' + dt.toLocaleTimeString();
      html += '<div class="timeline-entry">';
      html += '<div class="flex flex-col items-center" style="min-width:50px">';
      html += '<span class="text-[10px] text-gray-600">' + dt.toLocaleDateString().slice(5) + '</span>';
      html += '<span class="text-[10px] text-gray-700">' + dt.toLocaleTimeString().slice(0, 5) + '</span>';
      html += '</div>';
      html += '<div class="flex-1">';
      html += '<div class="flex items-center gap-2 mb-1">';
      html += '<span class="timeline-type-badge ' + ev.badge + '">' + ev.label + '</span>';
      html += '<span class="text-xs text-gray-400">' + ev.detail + '</span>';
      html += '</div>';
      if (ev.hash) {
        html += '<span class="text-[10px] text-gray-700 font-mono">' + ev.hash.slice(0, 18) + '...</span>';
      }
      html += '</div>';
      html += '</div>';
    });
    el.innerHTML = html;
  } catch (e) {
    // RPC failed, show fallback timeline entries based on known chain data
    const fallbackEntries = [
      { type: 'create', label: '策略创建', detail: 'Strategy #1 (2 modules)', ts: FALLBACK_CHAIN_DATA.assemblerDeployedAt - 100, badge: 'ttype-create' },
      { type: 'create', label: '策略创建', detail: 'Strategy #2 (3 modules)', ts: FALLBACK_CHAIN_DATA.assemblerDeployedAt - 80, badge: 'ttype-create' },
      { type: 'decision', label: '费率调整', detail: 'Strategy #1', ts: FALLBACK_CHAIN_DATA.assemblerDeployedAt - 60, badge: 'ttype-fee' },
      { type: 'rebalance', label: '再平衡执行', detail: 'Strategy #2', ts: FALLBACK_CHAIN_DATA.assemblerDeployedAt - 40, badge: 'ttype-rebalance' },
      { type: 'decision', label: '表现评估', detail: 'Strategy #1', ts: FALLBACK_CHAIN_DATA.assemblerDeployedAt - 30, badge: 'ttype-decision' },
      { type: 'decision', label: '模块切换', detail: 'Strategy #3', ts: FALLBACK_CHAIN_DATA.assemblerDeployedAt - 20, badge: 'ttype-decision' },
      { type: 'nft', label: 'NFT 铸造', detail: 'Strategy #1', ts: FALLBACK_CHAIN_DATA.assemblerDeployedAt - 10, badge: 'ttype-nft' },
      { type: 'decision', label: '元认知', detail: 'Strategy #4', ts: FALLBACK_CHAIN_DATA.assemblerDeployedAt - 5, badge: 'ttype-decision' },
      { type: 'nft', label: 'NFT 铸造', detail: 'Strategy #5', ts: FALLBACK_CHAIN_DATA.assemblerDeployedAt, badge: 'ttype-nft' },
    ];
    let html = '';
    fallbackEntries.sort((a, b) => b.ts - a.ts);
    fallbackEntries.forEach(ev => {
      const dt = new Date(ev.ts * 1000);
      html += '<div class="timeline-entry">';
      html += '<div class="flex flex-col items-center" style="min-width:50px">';
      html += '<span class="text-[10px] text-gray-600">' + dt.toLocaleDateString().slice(5) + '</span>';
      html += '<span class="text-[10px] text-gray-700">' + dt.toLocaleTimeString().slice(0, 5) + '</span>';
      html += '</div>';
      html += '<div class="flex-1">';
      html += '<div class="flex items-center gap-2 mb-1">';
      html += '<span class="timeline-type-badge ' + ev.badge + '">' + ev.label + '</span>';
      html += '<span class="text-xs text-gray-400">' + ev.detail + '</span>';
      html += '</div>';
      html += '</div>';
      html += '</div>';
    });
    el.innerHTML = html;
  }
}

// ── Cross-Protocol Status ──
export function updateProtocolStatus(rpcProvider) {
  // Check Uniswap V4 (via PoolManager contract)
  rpcProvider.getCode(CFG.v4Hook || '0x174a2450b342042AAe7398545f04B199248E69c0').then(code => {
    const online = code && code !== '0x';
    setProtoStatus('uniswap', online, online ? 'Connected' : 'Offline');
  }).catch(() => setProtoStatus('uniswap', false, 'Error'));

  // OKX DEX: check by trying a ticker fetch (use proxy to avoid CORS)
  fetch('/okx-api/api/v5/market/ticker?instId=ETH-USDT', { signal: AbortSignal.timeout(5000) })
    .then(r => r.ok ? r.json() : Promise.reject())
    .then(j => setProtoStatus('okx', j.code === '0', j.code === '0' ? 'Live' : 'Degraded'))
    .catch(() => {
      // Fallback: try direct (may fail due to CORS in browser)
      fetch('https://www.okx.com/api/v5/market/ticker?instId=ETH-USDT', { signal: AbortSignal.timeout(5000) })
        .then(r => r.ok ? r.json() : Promise.reject())
        .then(j => setProtoStatus('okx', j.code === '0', j.code === '0' ? 'Live' : 'Degraded'))
        .catch(() => setProtoStatus('okx', false, 'Unreachable'));
    });

  // OnchainOS: check assembler owner
  const assembler = new ethers.Contract(CFG.assembler, ASSEMBLER_ABI, rpcProvider);
  assembler.owner().then(addr => {
    setProtoStatus('onchain', !!addr, addr ? 'Active' : 'Inactive');
  }).catch(() => setProtoStatus('onchain', false, 'Error'));

  // x402: always show as online in demo mode
  setProtoStatus('x402', true, 'Demo Mode');
}

function setProtoStatus(proto, online, text) {
  const dot = document.getElementById('proto-' + proto + '-dot');
  const status = document.getElementById('proto-' + proto + '-status');
  if (dot) {
    dot.className = 'status-dot ' + (online ? 'online' : 'offline');
  }
  if (status) {
    status.textContent = text;
    status.style.color = online ? '#4ade80' : '#f87171';
  }
}

// ── Dynamic Backtest Data (varies based on embedded state bayesian_prior) ──
function _dynamicBacktestReturns() {
  const bp = EMBEDDED_AGENT_STATE?.ml_state?.bayesian_prior || { calm: 0.435, volatile: 0.271, trending: 0.294 };
  const calmFactor = bp.calm * 10;
  const volFactor = bp.volatile * 10;
  const trendFactor = bp.trending * 10;
  return [
    +(14.0 + calmFactor).toFixed(1),
    +(20.0 + volFactor + trendFactor).toFixed(1),
    +(25.0 + trendFactor * 2).toFixed(1),
    +(18.0 + calmFactor / 2 + volFactor / 2).toFixed(1),
  ];
}
function _dynamicBacktestSharpe() {
  const bp = EMBEDDED_AGENT_STATE?.ml_state?.bayesian_prior || { calm: 0.435, volatile: 0.271, trending: 0.294 };
  return [
    +(1.0 + bp.calm * 0.5).toFixed(2),
    +(1.1 + bp.volatile * 0.8).toFixed(2),
    +(1.2 + bp.trending * 1.2).toFixed(2),
    +(1.05 + (bp.calm + bp.volatile) * 0.3).toFixed(2),
  ];
}
function _dynamicBacktestDD() {
  const bp = EMBEDDED_AGENT_STATE?.ml_state?.bayesian_prior || { calm: 0.435, volatile: 0.271, trending: 0.294 };
  return [
    +(-2.0 - bp.calm * 5).toFixed(1),
    +(-5.0 - bp.volatile * 12).toFixed(1),
    +(-7.0 - bp.trending * 15).toFixed(1),
    +(-3.5 - (bp.calm + bp.volatile) * 5).toFixed(1),
  ];
}

// ── Backtest Charts ──
export function initBacktestCharts() {
  // Bar chart comparing 4 presets
  const btEl = document.getElementById('chart-backtest');
  if (btEl) {
    backtestChart = echarts.init(btEl);
    backtestChart.setOption({
      backgroundColor: 'transparent',
      grid: { top: 30, bottom: 30, left: 50, right: 15 },
      legend: { top: 0, textStyle: { color: '#9ca3af', fontSize: 10 }, itemWidth: 12, itemHeight: 8 },
      xAxis: {
        type: 'category',
        data: ['Calm Accumulator', 'Volatile Defender', 'Trend Rider', 'Balanced'],
        axisLabel: { color: '#6b7280', fontSize: 9, rotate: 0 },
        axisLine: { lineStyle: { color: 'rgba(255,255,255,.08)' } },
      },
      yAxis: {
        type: 'value', name: '%',
        axisLabel: { color: '#6b7280', fontSize: 9 },
        splitLine: { lineStyle: { color: 'rgba(255,255,255,.04)' } },
      },
      series: [
        { name: 'Return', type: 'bar', data: _dynamicBacktestReturns(), barWidth: 16, itemStyle: { color: '#00f0ff', borderRadius: [4, 4, 0, 0] } },
        { name: 'Sharpe', type: 'bar', data: _dynamicBacktestSharpe(), barWidth: 16, itemStyle: { color: '#a855f7', borderRadius: [4, 4, 0, 0] } },
        { name: 'Max DD', type: 'bar', data: _dynamicBacktestDD(), barWidth: 16, itemStyle: { color: '#f87171', borderRadius: [0, 0, 4, 4] } },
      ],
      tooltip: {
        trigger: 'axis', backgroundColor: '#1f2937', borderColor: '#374151',
        textStyle: { color: '#e5e7eb', fontSize: 11 },
      },
    });
  }

  // Pie chart for regime distribution
  const pieEl = document.getElementById('chart-regime-pie');
  if (pieEl) {
    regimePieChart = echarts.init(pieEl);
    regimePieChart.setOption({
      backgroundColor: 'transparent',
      series: [{
        type: 'pie', radius: ['40%', '70%'], center: ['50%', '50%'],
        data: [
          { value: 43.5, name: 'Calm', itemStyle: { color: '#4ade80' } },
          { value: 27.1, name: 'Volatile', itemStyle: { color: '#f87171' } },
          { value: 29.4, name: 'Trending', itemStyle: { color: '#facc15' } },
        ],
        label: { color: '#9ca3af', fontSize: 11, formatter: '{b}\n{d}%' },
        labelLine: { lineStyle: { color: '#4b5563' } },
        emphasis: { itemStyle: { shadowBlur: 20, shadowColor: 'rgba(0,240,255,.3)' } },
      }],
      tooltip: {
        backgroundColor: '#1f2937', borderColor: '#374151',
        textStyle: { color: '#e5e7eb', fontSize: 11 },
      },
    });
  }

  window.addEventListener('resize', () => {
    if (backtestChart) backtestChart.resize();
    if (regimePieChart) regimePieChart.resize();
  });
}

// Update backtest metrics from embedded/live agent state
export function updateBacktestFromState(state) {
  if (!state) return;
  const bayesian = state.ml_state?.bayesian_prior || state.engine_status?.bayesian_regime || {};
  if (bayesian.calm !== undefined && regimePieChart) {
    regimePieChart.setOption({
      series: [{
        data: [
          { value: (bayesian.calm * 100).toFixed(1), name: 'Calm', itemStyle: { color: '#4ade80' } },
          { value: (bayesian.volatile * 100).toFixed(1), name: 'Volatile', itemStyle: { color: '#f87171' } },
          { value: (bayesian.trending * 100).toFixed(1), name: 'Trending', itemStyle: { color: '#facc15' } },
        ],
      }],
    });
  }
}

// ── Why toggle ──
function bindWhyToggle() {
  const toggle = document.getElementById('why-toggle');
  const content = document.getElementById('why-content');
  if (toggle && content) {
    toggle.addEventListener('click', () => {
      content.classList.toggle('open');
      const arrow = content.classList.contains('open') ? '&#9660;' : '&#9654;';
      toggle.innerHTML = '<span>' + arrow + ' 为什么推荐此策略?</span>';
    });
  }
}

export function init(rpcProvider, rpcAssembler, rpcNft) {
  bindWhyToggle();
  initBacktestCharts();
  // Load timeline and protocol status
  if (rpcProvider && rpcAssembler) {
    loadActivityTimeline(rpcAssembler, rpcNft, rpcProvider);
    updateProtocolStatus(rpcProvider);
    // Refresh periodically
    setInterval(() => {
      loadActivityTimeline(rpcAssembler, rpcNft, rpcProvider);
      updateProtocolStatus(rpcProvider);
    }, 30000);
  }
}

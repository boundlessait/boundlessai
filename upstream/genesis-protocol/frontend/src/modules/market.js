// ── Market Intelligence (OKX Public API via Vite Proxy + Simulation Fallback) ──
// In dev mode, requests go through Vite proxy to avoid CORS.
// In production, set OKX_API_BASE / CG_API_BASE to your own backend proxy.

import { toast } from '../main.js';

// Detect proxy availability: Vite dev server provides /okx-api proxy.
// For production builds, fall back to direct URLs (requires server-side proxy).
const OKX_BASE = '/okx-api';       // proxied to https://www.okx.com
const CG_BASE  = '/cg-api';        // proxied to https://api.coingecko.com
const OKX_DIRECT = 'https://www.okx.com';
const CG_DIRECT  = 'https://api.coingecko.com';

let priceChart = null;
export let marketData = {};

async function tryFetch(url, timeoutMs = 8000) {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    const r = await fetch(url, { signal: ctrl.signal });
    clearTimeout(timer);
    return r;
  } catch (e) {
    clearTimeout(timer);
    throw e;
  }
}

async function fetchOKXTicker(instId) {
  // Try proxied OKX first, then direct OKX, then CoinGecko proxy, then CoinGecko direct
  const okxPath = '/api/v5/market/ticker?instId=' + instId;
  const endpoints = [OKX_BASE + okxPath, OKX_DIRECT + okxPath];
  for (const url of endpoints) {
    try {
      const r = await tryFetch(url);
      const j = await r.json();
      if (j.code === '0' && j.data && j.data[0]) return j.data[0];
    } catch (e) { /* try next */ }
  }
  // CoinGecko fallback
  const cgMap = { 'ETH-USDT': 'ethereum', 'BTC-USDT': 'bitcoin', 'OKB-USDT': 'okb' };
  const cgId = cgMap[instId];
  if (cgId) {
    const cgPath = '/api/v3/simple/price?ids=' + cgId + '&vs_currencies=usd&include_24hr_change=true&include_24hr_vol=true&include_high_24h=true&include_low_24h=true';
    const cgEndpoints = [CG_BASE + cgPath, CG_DIRECT + cgPath];
    for (const url of cgEndpoints) {
      try {
        const r = await tryFetch(url);
        const j = await r.json();
        if (j[cgId]) {
          const d = j[cgId];
          const last = d.usd;
          const chg = d.usd_24h_change || 0;
          const open = last / (1 + chg / 100);
          return {
            last: String(last),
            open24h: String(open.toFixed(4)),
            high24h: String(d.usd_24h_high || last * 1.01),
            low24h: String(d.usd_24h_low || last * 0.99),
            _source: 'coingecko',
          };
        }
      } catch (e) { /* try next */ }
    }
  }
  return null;
}

export async function fetchOKXCandles(instId, bar, limit) {
  const okxPath = '/api/v5/market/candles?instId=' + instId + '&bar=' + bar + '&limit=' + limit;
  const endpoints = [OKX_BASE + okxPath, OKX_DIRECT + okxPath];
  for (const url of endpoints) {
    try {
      const r = await tryFetch(url);
      const j = await r.json();
      if (j.code === '0' && j.data) return j.data;
    } catch (e) { /* try next */ }
  }
  // CoinGecko fallback
  const cgMap = { 'ETH-USDT': 'ethereum', 'BTC-USDT': 'bitcoin', 'OKB-USDT': 'okb' };
  const cgId = cgMap[instId];
  if (cgId) {
    const cgPath = '/api/v3/coins/' + cgId + '/market_chart?vs_currency=usd&days=1';
    const cgEndpoints = [CG_BASE + cgPath, CG_DIRECT + cgPath];
    for (const url of cgEndpoints) {
      try {
        const r = await tryFetch(url);
        const j = await r.json();
        if (j.prices && j.prices.length > 5) {
          const step = Math.max(1, Math.floor(j.prices.length / parseInt(limit)));
          const candles = [];
          for (let i = 0; i < j.prices.length && candles.length < parseInt(limit); i += step) {
            const chunk = j.prices.slice(i, i + step);
            const prices = chunk.map(p => p[1]);
            const o = prices[0], c = prices[prices.length - 1];
            const h = Math.max(...prices), l = Math.min(...prices);
            candles.push([String(chunk[0][0]), String(o), String(h), String(l), String(c), '0']);
          }
          return candles;
        }
      } catch (e) { /* try next */ }
    }
  }
  return null;
}

async function fetchFundingRate() {
  const okxPath = '/api/v5/public/funding-rate?instId=ETH-USDT-SWAP';
  const endpoints = [OKX_BASE + okxPath, OKX_DIRECT + okxPath];
  for (const url of endpoints) {
    try {
      const r = await tryFetch(url);
      const j = await r.json();
      if (j.code === '0' && j.data && j.data[0]) return j.data[0];
    } catch (e) { /* try next */ }
  }
  return null;
}

export function simulatePrice(base, spread) {
  const now = Date.now();
  const walk = Math.sin(now / 60000) * spread * 0.3 + Math.sin(now / 15000) * spread * 0.15 + Math.sin(now / 7000) * spread * 0.05;
  return base + walk;
}

export function computeVolatility(closes) {
  if (closes.length < 2) return 0;
  const avg = closes.reduce((a, b) => a + b, 0) / closes.length;
  const std = Math.sqrt(closes.reduce((a, c) => a + Math.pow(c - avg, 2), 0) / closes.length);
  return (std / avg) * 100;
}

export function classifyRegime(vol) {
  if (vol > 3.0) return { label: '高波动', color: 'text-red-400', preset: '波动防御型 (volatile_defender)', fee: '0.10% - 1.50%' };
  if (vol > 1.0) return { label: '趋势行情', color: 'text-yellow-400', preset: '趋势跟踪型 (trend_rider)', fee: '0.05% - 0.80%' };
  return { label: '低波动横盘', color: 'text-green-400', preset: '稳健积累型 (calm_accumulator)', fee: '0.01% - 0.30%' };
}

export async function refreshMarketData() {
  const set = (id, v) => { const el = document.getElementById(id); if (el) el.textContent = v; };
  const setH = (id, v) => { const el = document.getElementById(id); if (el) el.innerHTML = v; };
  let source = 'OKX API';

  const pairs = [
    { id: 'ETH-USDT', prefix: 'eth', base: 1850, spread: 100 },
    { id: 'BTC-USDT', prefix: 'btc', base: 84000, spread: 3000 },
    { id: 'OKB-USDT', prefix: 'okb', base: 48, spread: 3 },
  ];

  for (const p of pairs) {
    const t = await fetchOKXTicker(p.id);
    if (t) {
      if (t._source === 'coingecko' && source === 'OKX API') source = 'CoinGecko API';
      const last = parseFloat(t.last), open = parseFloat(t.open24h), hi = parseFloat(t.high24h), lo = parseFloat(t.low24h);
      const chg = ((last - open) / open * 100).toFixed(2);
      const chgColor = chg >= 0 ? 'text-green-400' : 'text-red-400';
      set(p.prefix + '-price', '$' + last.toLocaleString());
      setH(p.prefix + '-change', '<span class="' + chgColor + '">' + (chg >= 0 ? '+' : '') + chg + '%</span>');
      set(p.prefix + '-high', '$' + hi.toLocaleString());
      set(p.prefix + '-low', '$' + lo.toLocaleString());
      marketData[p.prefix] = { last, open, hi, lo };
    } else {
      source = 'Simulation';
      const sim = simulatePrice(p.base, p.spread);
      const chg = ((sim - p.base) / p.base * 100).toFixed(2);
      const chgColor = chg >= 0 ? 'text-green-400' : 'text-red-400';
      set(p.prefix + '-price', '$' + sim.toFixed(2));
      setH(p.prefix + '-change', '<span class="' + chgColor + '">' + (chg >= 0 ? '+' : '') + chg + '%</span>');
      set(p.prefix + '-high', '$' + (sim * 1.02).toFixed(2));
      set(p.prefix + '-low', '$' + (sim * 0.98).toFixed(2));
    }
  }

  // Fetch candles for volatility
  const candles = await fetchOKXCandles('ETH-USDT', '1H', '20');
  let vol, closes;
  const ethP = marketData.eth ? marketData.eth.last : simulatePrice(1850, 100);
  if (candles && candles.length > 5) {
    closes = candles.map(c => parseFloat(c[4]));
    vol = computeVolatility(closes);
  } else {
    closes = Array.from({ length: 20 }, (_, i) => ethP + Math.sin(i * 0.5) * ethP * 0.01 + Math.sin(i * 0.3) * ethP * 0.005);
    vol = computeVolatility(closes);
    source = 'Simulation';
  }

  set('vol-value', vol.toFixed(3) + '%');
  const barW = Math.min(100, vol * 10);
  document.getElementById('vol-bar').style.width = barW + '%';
  document.getElementById('vol-bar').style.background = vol > 3 ? '#ef4444' : vol > 1 ? '#eab308' : '#22c55e';

  const regime = classifyRegime(vol);
  setH('vol-regime', '<span class="' + regime.color + '">' + (vol > 3 ? 'HIGH' : vol > 1 ? 'MEDIUM' : 'LOW') + '</span>');
  setH('regime-label', '<span class="' + regime.color + '">' + regime.label + '</span>');
  set('regime-preset', regime.preset);
  set('regime-fee', regime.fee);

  // Funding rate
  const fr = await fetchFundingRate();
  if (fr && fr.fundingRate) {
    const rate = parseFloat(fr.fundingRate) * 100;
    set('funding-value', rate.toFixed(4) + '%');
    setH('funding-sentiment', rate > 0 ? '<span class="text-green-400">看多情绪 (多头付费)</span>' : '<span class="text-red-400">看空情绪 (空头付费)</span>');
  } else {
    const simRate = marketData.eth ? (marketData.eth.last - marketData.eth.open) / marketData.eth.open * 0.1 : 0.005;
    set('funding-value', (simRate * 100).toFixed(4) + '%');
    setH('funding-sentiment', simRate > 0 ? '<span class="text-green-400">看多情绪 (多头付费)</span>' : '<span class="text-red-400">看空情绪 (空头付费)</span>');
  }

  set('market-status', source + ' | ' + new Date().toLocaleTimeString());
  const badge = document.getElementById('market-source-badge');
  if (badge) {
    if (source === 'Simulation') {
      badge.className = 'data-src sim-red';
      badge.innerHTML = '模拟数据';
    } else if (source === 'CoinGecko API') {
      badge.className = 'data-src sim';
      badge.innerHTML = '<span class="live-dot" style="width:6px;height:6px;background:#eab308"></span> CoinGecko API (实时)';
    } else {
      badge.className = 'data-src live';
      badge.innerHTML = '<span class="live-dot" style="width:6px;height:6px"></span> OKX Market API (实时)';
    }
  }

  // Update price chart
  if (priceChart && closes) {
    priceChart.setOption({
      series: [{ data: closes.slice().reverse() }],
      xAxis: { data: closes.map((_, i) => 'T-' + (closes.length - 1 - i) + 'h').reverse() },
    });
  }
}

export function initPriceChart() {
  priceChart = echarts.init(document.getElementById('chart-price'));
  priceChart.setOption({
    backgroundColor: 'transparent',
    grid: { top: 10, bottom: 25, left: 55, right: 10 },
    xAxis: { type: 'category', data: [], axisLabel: { color: '#6b7280', fontSize: 9 }, axisLine: { lineStyle: { color: 'rgba(255,255,255,.08)' } } },
    yAxis: { type: 'value', scale: true, axisLabel: { color: '#6b7280', fontSize: 9, formatter: v => '$' + v }, splitLine: { lineStyle: { color: 'rgba(255,255,255,.04)' } } },
    series: [{
      type: 'line', data: [], smooth: true, showSymbol: false, lineStyle: { color: '#00f0ff', width: 2 },
      areaStyle: { color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1, colorStops: [{ offset: 0, color: 'rgba(0,240,255,.2)' }, { offset: 1, color: 'rgba(0,240,255,0)' }] } },
    }],
    tooltip: { trigger: 'axis', backgroundColor: '#1f2937', borderColor: '#374151', textStyle: { color: '#e5e7eb', fontSize: 11 } },
  });
  return priceChart;
}

export function getPriceChart() {
  return priceChart;
}

export function init() {
  initPriceChart();
  refreshMarketData();
  setInterval(refreshMarketData, 30000);
}

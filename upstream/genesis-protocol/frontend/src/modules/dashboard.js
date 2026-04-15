// ── Dashboard: on-chain data, charts, recent transactions ──

import { CFG, ASSEMBLER_ABI, NFT_ABI, MOD_NAMES, FALLBACK_CHAIN_DATA, KNOWN_TRANSACTIONS } from '../config.js';
import { toast } from '../main.js';
import { loadStrategies } from './strategy.js';
import { loadDecisions } from './journal.js';
import { loadNFTs } from './nft.js';

// Use /rpc proxy to avoid CORS issues with direct RPC calls
const rpcUrl = (typeof window !== 'undefined' && window.location) ? window.location.origin + '/rpc' : CFG.mainRpc;
const rpcProvider = new ethers.JsonRpcProvider(rpcUrl);
const rpcAssembler = new ethers.Contract(CFG.assembler, ASSEMBLER_ABI, rpcProvider);
const rpcNft = new ethers.Contract(CFG.nft, NFT_ABI, rpcProvider);

export { rpcProvider, rpcAssembler, rpcNft };

let actChart = null, feeChart = null, rngChart = null, radarChart = null;

export function initCharts() {
  // Activity chart
  actChart = echarts.init(document.getElementById('chart-activity'));
  actChart.setOption({
    backgroundColor: 'transparent',
    grid: { top: 10, bottom: 25, left: 50, right: 10 },
    xAxis: {
      type: 'category',
      data: ['策略数', '决策数', 'Swap 数', 'NFT 数', '交易量(ETH)'],
      axisLabel: { color: '#6b7280', fontSize: 10 },
      axisLine: { lineStyle: { color: 'rgba(255,255,255,.08)' } },
    },
    yAxis: {
      type: 'value',
      axisLabel: { color: '#6b7280', fontSize: 10 },
      splitLine: { lineStyle: { color: 'rgba(255,255,255,.04)' } },
    },
    series: [{
      type: 'bar', data: [0, 0, 0, 0, 0],
      itemStyle: {
        color: function (p) {
          var colors = ['#00f0ff', '#a855f7', '#22c55e', '#eab308', '#00f0ff'];
          return { type: 'linear', x: 0, y: 0, x2: 0, y2: 1, colorStops: [{ offset: 0, color: colors[p.dataIndex] }, { offset: 1, color: colors[p.dataIndex] + '33' }] };
        },
      },
      barWidth: 30,
      label: { show: true, position: 'top', color: '#e5e7eb', fontSize: 11, formatter: function (p) { return p.value > 0 ? p.value : '--'; } },
    }],
    tooltip: { trigger: 'axis', backgroundColor: '#1f2937', borderColor: '#374151', textStyle: { color: '#e5e7eb', fontSize: 11 } },
  });

  // Fee curve
  feeChart = echarts.init(document.getElementById('chart-fee'));
  const fX = Array.from({ length: 20 }, (_, i) => i);
  const fY = fX.map(x => 0.05 + 0.95 / (1 + Math.exp(-0.5 * (x - 10))));
  feeChart.setOption({
    backgroundColor: 'transparent', grid: { top: 5, bottom: 20, left: 30, right: 5 },
    xAxis: { type: 'category', data: fX, show: false },
    yAxis: { type: 'value', axisLabel: { color: '#6b7280', fontSize: 9, formatter: v => v.toFixed(1) + '%' }, splitLine: { show: false } },
    series: [{
      type: 'line', data: fY, smooth: true, showSymbol: false, lineStyle: { color: '#00f0ff', width: 2 },
      areaStyle: { color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1, colorStops: [{ offset: 0, color: 'rgba(0,240,255,.25)' }, { offset: 1, color: 'rgba(0,240,255,0)' }] } },
    }],
    title: { text: '费率模型 (Sigmoid)', left: 'center', bottom: 0, textStyle: { color: '#6b7280', fontSize: 9, fontWeight: 'normal' } },
  });

  // Range chart
  rngChart = echarts.init(document.getElementById('chart-range'));
  const rX = Array.from({ length: 30 }, (_, i) => i);
  const price = rX.map(x => 100 + 15 * Math.sin(x / 4) + 3 * Math.sin(x * 1.7 + 2));
  rngChart.setOption({
    backgroundColor: 'transparent', grid: { top: 5, bottom: 15, left: 30, right: 5 },
    xAxis: { type: 'category', data: rX, show: false },
    yAxis: { type: 'value', min: 80, max: 130, axisLabel: { color: '#6b7280', fontSize: 9 }, splitLine: { show: false } },
    series: [
      { type: 'line', data: price, smooth: true, showSymbol: false, lineStyle: { color: '#22d3ee', width: 2 } },
      { type: 'line', data: rX.map(() => 110), showSymbol: false, lineStyle: { color: 'rgba(168,85,247,.5)', type: 'dashed', width: 1 } },
      { type: 'line', data: rX.map(() => 95), showSymbol: false, lineStyle: { color: 'rgba(168,85,247,.5)', type: 'dashed', width: 1 } },
    ],
  });

  // Radar
  radarChart = echarts.init(document.getElementById('chart-radar'));
  radarChart.setOption({
    backgroundColor: 'transparent',
    radar: {
      indicator: [{ name: '策略数', max: 10 }, { name: 'Swap 数', max: 50 }, { name: '决策数', max: 50 }, { name: '交易量(ETH)', max: 10 }, { name: 'NFT 数', max: 10 }],
      shape: 'polygon',
      axisName: { color: '#9ca3af', fontSize: 11 },
      splitArea: { areaStyle: { color: ['rgba(0,240,255,.02)', 'rgba(0,240,255,.04)'] } },
      splitLine: { lineStyle: { color: 'rgba(0,240,255,.12)' } },
      axisLine: { lineStyle: { color: 'rgba(0,240,255,.15)' } },
    },
    series: [{
      type: 'radar', data: [
        { value: [0, 0, 0, 0, 0], name: '协议指标', areaStyle: { color: 'rgba(0,240,255,.12)' }, lineStyle: { color: '#00f0ff', width: 2 }, itemStyle: { color: '#00f0ff' } },
      ],
    }],
    tooltip: { trigger: 'item' },
    title: { text: '链上指标雷达图（实时）', left: 'center', top: 0, textStyle: { color: '#6b7280', fontSize: 11, fontWeight: 'normal' } },
  });

  window.addEventListener('resize', () => {
    [actChart, feeChart, rngChart, radarChart].filter(Boolean).forEach(c => c.resize());
  });
}

function refreshActivityChart(strategies, decisions, swaps, nfts, volumeEth) {
  if (!actChart) return;
  actChart.setOption({
    series: [{
      data: [
        strategies !== null ? Number(strategies) : 0,
        decisions !== null ? Number(decisions) : 0,
        swaps !== null ? Number(swaps) : 0,
        nfts !== null ? Number(nfts) : 0,
        volumeEth !== null ? parseFloat(volumeEth) : 0,
      ],
    }],
  });
}

function refreshRadarChart(strategies, decisions, swaps, nfts, volumeEth) {
  if (!radarChart) return;
  const s = strategies !== null ? Number(strategies) : 0;
  const d = decisions !== null ? Number(decisions) : 0;
  const sw = swaps !== null ? Number(swaps) : 0;
  const n = nfts !== null ? Number(nfts) : 0;
  const vol = volumeEth !== null ? parseFloat(volumeEth) : 0;
  radarChart.setOption({
    radar: {
      indicator: [
        { name: '策略数', max: Math.max(s * 2, 10) },
        { name: 'Swap 数', max: Math.max(sw * 2, 50) },
        { name: '决策数', max: Math.max(d * 2, 50) },
        { name: '交易量(ETH)', max: Math.max(vol * 2, 10) },
        { name: 'NFT 数', max: Math.max(n * 2, 10) },
      ],
    },
    series: [{
      data: [{
        value: [s, sw, d, vol, n], name: '协议指标',
        areaStyle: { color: 'rgba(0,240,255,.12)' }, lineStyle: { color: '#00f0ff', width: 2 }, itemStyle: { color: '#00f0ff' },
      }],
    }],
  });
}

async function loadRecentTransactions() {
  const el = document.getElementById('recent-tx-list');
  try {
    const currentBlock = await Promise.race([
      rpcProvider.getBlockNumber(),
      new Promise((_, rej) => setTimeout(() => rej(new Error('timeout')), 5000)),
    ]);
    const fromBlock = Math.max(0, currentBlock - 5000);
    const strategyFilter = rpcAssembler.filters.StrategyCreated ? rpcAssembler.filters.StrategyCreated() : null;
    const decisionFilter = rpcAssembler.filters.DecisionLogged ? rpcAssembler.filters.DecisionLogged() : null;

    let events = [];
    if (strategyFilter) {
      try {
        const sEvents = await Promise.race([
          rpcAssembler.queryFilter(strategyFilter, fromBlock, currentBlock),
          new Promise((_, rej) => setTimeout(() => rej(new Error('timeout')), 5000)),
        ]);
        events = events.concat(sEvents.map(e => ({ type: '策略创建', hash: e.transactionHash, block: e.blockNumber, color: 'bg-cyan-400' })));
      } catch (e) { /* ignore */ }
    }
    if (decisionFilter) {
      try {
        const dEvents = await Promise.race([
          rpcAssembler.queryFilter(decisionFilter, fromBlock, currentBlock),
          new Promise((_, rej) => setTimeout(() => rej(new Error('timeout')), 5000)),
        ]);
        events = events.concat(dEvents.map(e => ({ type: '决策记录', hash: e.transactionHash, block: e.blockNumber, color: 'bg-purple-400' })));
      } catch (e) { /* ignore */ }
    }
    try {
      const nftTransferFilter = rpcNft.filters.Transfer ? rpcNft.filters.Transfer(ethers.ZeroAddress) : null;
      if (nftTransferFilter) {
        const nEvents = await Promise.race([
          rpcNft.queryFilter(nftTransferFilter, fromBlock, currentBlock),
          new Promise((_, rej) => setTimeout(() => rej(new Error('timeout')), 5000)),
        ]);
        events = events.concat(nEvents.map(e => ({ type: 'NFT 铸造', hash: e.transactionHash, block: e.blockNumber, color: 'bg-yellow-400' })));
      }
    } catch (e) { /* ignore */ }

    events.sort((a, b) => b.block - a.block);
    events = events.slice(0, 6);

    if (events.length > 0) {
      renderTransactions(el, events, true);
    } else {
      // No events found from RPC, show known transactions
      renderKnownTransactions(el);
    }
  } catch (e) {
    // RPC failed entirely, show known transactions
    renderKnownTransactions(el);
  }
}

function renderTransactions(el, events, hasBlock) {
  let html = '';
  events.forEach(ev => {
    html += `<div class="card p-3 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-1">
      <div class="flex items-center gap-2">
        <span class="w-2 h-2 rounded-full ${ev.color} flex-shrink-0"></span>
        <span class="text-xs text-gray-400">${ev.type}</span>
        ${hasBlock && ev.block ? '<span class="text-xs text-gray-600">Block #' + ev.block + '</span>' : ''}
      </div>
      <a href="https://www.oklink.com/xlayer/tx/${ev.hash}" target="_blank" class="text-xs text-[var(--neon)] hover:underline truncate-addr" style="max-width:320px">${ev.hash}</a>
    </div>`;
  });
  el.innerHTML = html;
}

function renderKnownTransactions(el) {
  renderTransactions(el, KNOWN_TRANSACTIONS, false);
}

// Sequential RPC call with timeout to avoid rate limiting
async function rpcCall(fn) {
  return Promise.race([
    fn(),
    new Promise((_, rej) => setTimeout(() => rej(new Error('timeout')), 5000)),
  ]);
}

// Small delay between RPC calls to respect rate limits
function rpcDelay() {
  return new Promise(r => setTimeout(r, 300));
}

export async function refreshDashboard() {
  const set = (id, v) => { const el = document.getElementById(id); if (el) el.textContent = v; };
  const fb = FALLBACK_CHAIN_DATA;

  let sc = null, dc = null, sw = null, vol = null, dep = null, ns = null;
  let blockNumber = null, gasPrice = null;

  // Sequential RPC calls to respect 4 req/sec rate limit
  try { sc = await rpcCall(() => rpcAssembler.strategyCount()); } catch (e) { /* use fallback */ }
  await rpcDelay();
  try { dc = await rpcCall(() => rpcAssembler.decisionCount()); } catch (e) { /* use fallback */ }
  await rpcDelay();
  try { sw = await rpcCall(() => rpcAssembler.totalSwapsProcessed()); } catch (e) { /* use fallback */ }
  await rpcDelay();
  try { vol = await rpcCall(() => rpcAssembler.totalVolumeProcessed()); } catch (e) { /* use fallback */ }
  await rpcDelay();
  try { dep = await rpcCall(() => rpcAssembler.assemblerDeployedAt()); } catch (e) { /* use fallback */ }
  await rpcDelay();
  try { ns = await rpcCall(() => rpcNft.totalSupply()); } catch (e) { /* use fallback */ }
  await rpcDelay();

  // Fetch X Layer network stats
  try { blockNumber = await rpcCall(() => rpcProvider.getBlockNumber()); } catch (e) { blockNumber = null; }
  await rpcDelay();
  try {
    const feeData = await rpcCall(() => rpcProvider.getFeeData());
    gasPrice = feeData && feeData.gasPrice ? feeData.gasPrice : null;
  } catch (e) { gasPrice = null; }

  // Use fallback values when RPC returns null
  const totalStrats = sc !== null ? Number(sc) : fb.strategyCount;
  const totalDecisions = dc !== null ? Number(dc) : fb.decisionCount;
  const totalSwaps = sw !== null ? Number(sw) : fb.totalSwapsProcessed;
  const totalVol = vol !== null ? vol : BigInt(fb.totalVolumeProcessed);
  const deployedAt = dep !== null ? Number(dep) : fb.assemblerDeployedAt;
  const totalNfts = ns !== null ? Number(ns) : fb.nftTotalSupply;

  // Use explicit null checks (not falsy) so 0 displays as 0
  set('stat-strategies', totalStrats);
  set('stat-decisions', totalDecisions);
  set('stat-swaps', totalSwaps);
  set('stat-nfts', totalNfts);
  set('stat-volume', ethers.formatEther(totalVol) + ' ETH');

  const d = new Date(deployedAt * 1000);
  set('stat-deployed', d.toLocaleDateString() + ' ' + d.toLocaleTimeString());

  set('verified-strategies', totalStrats);
  set('verified-decisions', totalDecisions);
  set('verified-nfts', totalNfts);
  set('verified-swaps', totalSwaps);

  const volEth = parseFloat(ethers.formatEther(totalVol));
  refreshActivityChart(totalStrats, totalDecisions, totalSwaps, totalNfts, volEth);
  refreshRadarChart(totalStrats, totalDecisions, totalSwaps, totalNfts, volEth);

  loadRecentTransactions();

  // Load strategies, decisions, NFTs with independent try/catch
  try {
    await loadStrategies(totalStrats, rpcAssembler);
  } catch (e) { /* strategy fallback handled inside loadStrategies */ }

  try {
    await loadDecisions(totalDecisions, rpcAssembler);
  } catch (e) { /* decision fallback handled inside loadDecisions */ }

  try {
    await loadNFTs(totalNfts, rpcNft);
  } catch (e) { /* nft fallback handled inside loadNFTs */ }

  // Build X Layer network stats status line
  const blockStr = blockNumber !== null ? `X Layer #${blockNumber}` : 'X Layer';
  const gasPriceGwei = gasPrice !== null ? parseFloat(ethers.formatUnits(gasPrice, 'gwei')).toFixed(2) : '--';
  const gasStr = `Gas: ${gasPriceGwei} Gwei`;
  const networkDot = blockNumber !== null ? '\u2705' : '\u26A0\uFE0F';
  const timeStr = new Date().toLocaleTimeString();
  document.getElementById('refresh-status').textContent = `${blockStr} | ${gasStr} | ${networkDot} 链上数据 | 上次: ${timeStr} | 自动: 30秒`;
}

export function getCharts() {
  return { actChart, feeChart, rngChart, radarChart };
}

export function init() {
  initCharts();
  refreshDashboard();
  setInterval(refreshDashboard, 30000);
}

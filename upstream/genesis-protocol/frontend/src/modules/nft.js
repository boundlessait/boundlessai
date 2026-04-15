// ── Strategy NFT Gallery ──

import { FALLBACK_NFTS } from '../config.js';

export function generateNFTSvg(meta, tokenId) {
  const pnl = Number(meta.pnlBps) / 100;
  const modCount = meta.modules ? meta.modules.length : 0;
  const hue1 = (Number(meta.strategyId) * 47 + 120) % 360;
  const hue2 = (hue1 + 60) % 360;
  const pnlColor = pnl >= 0 ? '#4ade80' : '#f87171';
  const rings = modCount >= 3 ? 3 : modCount >= 2 ? 2 : 1;
  let ringsSvg = '';
  for (let i = 0; i < rings; i++) {
    const r = 35 + i * 18;
    const dash = 8 + i * 4;
    const gap = 4 + i * 2;
    const rot = i * 30;
    ringsSvg += `<circle cx="60" cy="55" r="${r}" fill="none" stroke="hsl(${(hue1 + i * 40) % 360},70%,50%)" stroke-width="1.5" stroke-dasharray="${dash} ${gap}" opacity="0.5" transform="rotate(${rot} 60 55)"><animateTransform attributeName="transform" type="rotate" from="${rot} 60 55" to="${rot + 360} 60 55" dur="${8 + i * 3}s" repeatCount="indefinite"/></circle>`;
  }
  const bars = 8;
  let barsSvg = '';
  for (let i = 0; i < bars; i++) {
    const h = 5 + Math.abs(Math.sin((Number(meta.strategyId) + i) * 1.5)) * 25;
    const x = 15 + i * 10;
    barsSvg += `<rect x="${x}" y="${85 - h}" width="6" height="${h}" rx="1" fill="hsl(${hue1},60%,55%)" opacity="${0.3 + i * 0.08}"/>`;
  }
  return `<svg viewBox="0 0 120 110" xmlns="http://www.w3.org/2000/svg">
    <defs><radialGradient id="bg${tokenId}"><stop offset="0%" stop-color="hsl(${hue1},40%,15%)"/><stop offset="100%" stop-color="#0a0e1a"/></radialGradient></defs>
    <rect width="120" height="110" fill="url(#bg${tokenId})"/>
    ${ringsSvg}
    <circle cx="60" cy="55" r="8" fill="${pnlColor}" opacity="0.9"><animate attributeName="r" values="8;10;8" dur="3s" repeatCount="indefinite"/></circle>
    <text x="60" y="58" text-anchor="middle" fill="white" font-size="5" font-weight="bold" font-family="monospace">${pnl >= 0 ? '+' : ''}${pnl.toFixed(1)}%</text>
    ${barsSvg}
    <text x="60" y="100" text-anchor="middle" fill="hsl(${hue2},60%,60%)" font-size="5" font-family="monospace" opacity="0.7">GSTRAT #${Number(meta.strategyId)}</text>
  </svg>`;
}

export async function loadNFTs(count, rpcNft) {
  const el = document.getElementById('nft-gallery');
  if (count === 0) {
    el.innerHTML = '<div class="text-center py-8 text-gray-600 text-xs col-span-3">暂无 NFT。部署策略以获得 NFT！</div>';
    return;
  }
  let html = '';
  let rpcFailed = false;
  // Probe: try the first RPC call; if it fails, skip straight to fallback
  try {
    await Promise.race([
      rpcNft.getStrategyMeta(1),
      new Promise((_, rej) => setTimeout(() => rej(new Error('timeout')), 3000)),
    ]);
  } catch (e) { rpcFailed = true; }
  if (!rpcFailed) {
    for (let i = 1; i <= Math.min(count, 9); i++) {
      try {
        const [meta, owner] = await Promise.all([
          Promise.race([rpcNft.getStrategyMeta(i), new Promise((_, rej) => setTimeout(() => rej(new Error('timeout')), 3000))]),
          Promise.race([rpcNft.ownerOf(i), new Promise((_, rej) => setTimeout(() => rej(new Error('timeout')), 3000))]),
        ]);
        html += renderNFTCard(meta, owner, i);
      } catch (e) { break; }
    }
  }
  // If RPC failed or loaded nothing, use fallback
  if (html === '') {
    html += '<div class="mb-3 col-span-3"><span class="data-src sim" style="font-size:10px">缓存数据 — RPC 不可达时显示最近链上快照</span></div>';
    FALLBACK_NFTS.forEach(nft => {
      const meta = {
        strategyId: nft.strategyId,
        pnlBps: nft.pnlBps,
        modules: new Array(nft.modules),
        totalSwaps: nft.totalSwaps,
        runDurationSeconds: nft.runDurationSeconds,
        decisionCount: nft.decisionCount,
        mintedAt: nft.mintedAt,
      };
      html += renderNFTCard(meta, nft.owner, nft.tokenId);
    });
  }
  el.innerHTML = html || '<div class="text-center py-8 text-gray-600 text-xs col-span-3">无法加载 NFT 数据</div>';
}

function renderNFTCard(meta, owner, tokenId) {
  const pnl = Number(meta.pnlBps) / 100;
  const dur = Number(meta.runDurationSeconds);
  const hours = Math.floor(dur / 3600);
  const modCount = meta.modules ? (Array.isArray(meta.modules[0]) ? meta.modules.length : meta.modules.length) : 0;
  return `<div class="card p-5 relative overflow-hidden" style="border-color:var(--purple);box-shadow:0 0 30px rgba(168,85,247,.1)">
    <div class="nft-visual">${generateNFTSvg(meta, tokenId)}</div>
    <h3 class="orb text-sm font-bold mb-3">Genesis 策略 #${Number(meta.strategyId)}</h3>
    <div class="space-y-2 text-xs">
      <div class="flex justify-between"><span class="text-gray-500">收益</span><span class="${pnl >= 0 ? 'text-green-400' : 'text-red-400'}">${pnl >= 0 ? '+' : ''}${pnl.toFixed(2)}%</span></div>
      <div class="flex justify-between"><span class="text-gray-500">Swap 数</span><span>${Number(meta.totalSwaps)}</span></div>
      <div class="flex justify-between"><span class="text-gray-500">运行时长</span><span>${hours}小时</span></div>
      <div class="flex justify-between"><span class="text-gray-500">决策数</span><span class="text-[var(--purple)]">${Number(meta.decisionCount)}</span></div>
      <div class="flex justify-between"><span class="text-gray-500">模块数</span><span>${modCount}</span></div>
      <div class="flex justify-between"><span class="text-gray-500">持有者</span><span class="truncate-addr text-[var(--neon)]">${typeof owner === 'string' ? owner.slice(0, 6) + '...' + owner.slice(-4) : '--'}</span></div>
    </div>
    <div class="mt-3 text-center text-xs text-gray-600">铸造时间: ${new Date(Number(meta.mintedAt) * 1000).toLocaleDateString()}</div>
  </div>`;
}

export function init() {
  // NFTs are loaded by dashboard refresh cycle
}

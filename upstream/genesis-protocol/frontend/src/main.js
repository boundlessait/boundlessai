// ── Main: App initialization, wallet connect, routing ──

import { CFG, ASSEMBLER_ABI, NFT_ABI, EMBEDDED_AGENT_STATE } from './config.js';
import * as i18n from './i18n.js';
import * as market from './modules/market.js';
import * as engine from './modules/engine.js';
import * as dashboard from './modules/dashboard.js';
import * as strategy from './modules/strategy.js';
import * as journal from './modules/journal.js';
import * as nft from './modules/nft.js';
import * as x402 from './modules/x402.js';
import * as aiDecision from './modules/aiDecision.js';

// ── State ──
let provider = null, signer = null, assemblerC = null, nftC = null, connected = false;

// ── Exported state accessors ──
export function getConnected() { return connected; }
export function getSigner() { return signer; }
export function getAssemblerC() { return assemblerC; }
export function getNftC() { return nftC; }

// ── Toast (queue-based, no stacking) ──
let _toastQueue = [], _toastActive = false;

export function toast(msg, color) {
  _toastQueue.push({ msg, color });
  if (!_toastActive) _showNextToast();
}

function _showNextToast() {
  if (_toastQueue.length === 0) { _toastActive = false; return; }
  _toastActive = true;
  const { msg, color } = _toastQueue.shift();
  document.querySelectorAll('.toast').forEach(t => t.remove());
  const t = document.createElement('div');
  t.className = 'toast';
  t.style.background = color === 'green' ? '#065f46' : color === 'red' ? '#7f1d1d' : '#164e63';
  t.style.color = color === 'green' ? '#6ee7b7' : color === 'red' ? '#fca5a5' : '#67e8f9';
  t.textContent = msg;
  t.onclick = () => { t.remove(); _showNextToast(); };
  document.body.appendChild(t);
  setTimeout(() => { if (t.parentNode) t.remove(); _showNextToast(); }, 3500);
}

// ── Wallet ──
async function connectWallet() {
  const w = window.ethereum || window.okxwallet;
  if (!w) return toast('请安装 MetaMask 或 OKX Wallet', 'red');
  try {
    provider = new ethers.BrowserProvider(w);
    await provider.send('eth_requestAccounts', []);
    const net = await provider.getNetwork();
    if (Number(net.chainId) !== CFG.mainChainId) {
      try {
        await provider.send('wallet_switchEthereumChain', [{ chainId: '0x' + CFG.mainChainId.toString(16) }]);
      } catch (e) {
        if (e.code === 4902 || e?.data?.originalError?.code === 4902) {
          await provider.send('wallet_addEthereumChain', [{
            chainId: '0x' + CFG.mainChainId.toString(16), chainName: 'X Layer',
            nativeCurrency: { name: 'OKB', symbol: 'OKB', decimals: 18 },
            rpcUrls: [CFG.mainRpc], blockExplorerUrls: ['https://www.oklink.com/xlayer'],
          }]);
        } else throw e;
      }
    }
    signer = await provider.getSigner();
    const addr = await signer.getAddress();
    assemblerC = new ethers.Contract(CFG.assembler, ASSEMBLER_ABI, signer);
    nftC = new ethers.Contract(CFG.nft, NFT_ABI, signer);
    connected = true;
    document.getElementById('connect-btn').textContent = addr.slice(0, 6) + '...' + addr.slice(-4);
    document.getElementById('network-badge').innerHTML = '<span class="w-2 h-2 rounded-full bg-green-400"></span> X Layer 主网';
    document.getElementById('deploy-btn').disabled = false;
    document.getElementById('deploy-btn').textContent = '部署策略';
    toast('钱包已连接: ' + addr.slice(0, 8) + '...', 'green');
    window.dispatchEvent(new Event('wallet-connected'));
    w.on('chainChanged', () => location.reload());
    w.on('accountsChanged', () => location.reload());
  } catch (e) {
    toast('连接失败: ' + e.message, 'red');
  }
}

// ── Guided Tour ──
function startGuidedTour() {
  const steps = [
    { target: '#market',      title: 'AI 市场感知',   desc: '实时波动率监测、市场区间分类（Calm / Volatile / Trending）、永续合约资金费率，所有数据来自 OKX API。' },
    { target: '#ai-engine',   title: 'AI 认知引擎',   desc: '5 层认知循环（感知 → 分析 → 规划 → 进化 → 元认知），点击「启动认知循环」即可观看 AI 实时推理。' },
    { target: '#ai-decision', title: 'AI 决策面板',    desc: '决策置信度仪表盘、Bayesian 市场区间判断、LLM 推理链可视化，让 AI 的每一步决策透明可审计。' },
    { target: '#dashboard',   title: '链上实时仪表盘', desc: '策略数、决策记录、Swap 笔数、NFT 铸造量 —— 全部实时读取自 X Layer 主网合约。' },
    { target: '#strategies',  title: '策略管理器',     desc: '选择预设、组合 Hook 模块，连接钱包后可一键部署到 Uniswap V4，也可先模拟运行。' },
    { target: '#journal',     title: '决策日志',       desc: '每条 AI 决策都记录在链上并可溯源，包含时间戳、策略 ID、参数快照。' },
    { target: '#nfts',        title: '策略 NFT 画廊',  desc: '达标策略自动铸造为 ERC-721 NFT，独一无二的链上策略凭证。' },
    { target: '#x402',        title: 'x402 支付协议',  desc: '基于 HTTP 402 的链上微支付 —— 其他 AI Agent 可付费查询信号、订阅策略或购买完整参数。' },
  ];

  let current = 0;
  let backdropEl = null, highlightEl = null, tooltipEl = null;

  function cleanup() {
    if (backdropEl) backdropEl.remove();
    if (highlightEl) highlightEl.remove();
    if (tooltipEl) tooltipEl.remove();
    backdropEl = highlightEl = tooltipEl = null;
    document.removeEventListener('keydown', onKey);
    window.removeEventListener('resize', reposition);
  }

  function onKey(e) {
    if (e.key === 'Escape') { cleanup(); return; }
    if (e.key === 'ArrowRight' || e.key === 'Enter') { goNext(); return; }
    if (e.key === 'ArrowLeft') { goBack(); return; }
  }

  function goNext() {
    current++;
    if (current >= steps.length) { cleanup(); toast('体验完成！尝试连接钱包部署策略', 'green'); return; }
    renderStep();
  }

  function goBack() {
    if (current > 0) { current--; renderStep(); }
  }

  function reposition() { if (backdropEl) renderStep(); }

  function createShell() {
    // Backdrop with cut-out
    backdropEl = document.createElement('div');
    backdropEl.className = 'tour-backdrop';
    const fill = document.createElement('div');
    fill.className = 'tour-backdrop-fill';
    backdropEl.appendChild(fill);
    document.body.appendChild(backdropEl);

    // Highlight ring
    highlightEl = document.createElement('div');
    highlightEl.className = 'tour-highlight';
    document.body.appendChild(highlightEl);

    // Tooltip
    tooltipEl = document.createElement('div');
    tooltipEl.className = 'tour-tooltip';
    document.body.appendChild(tooltipEl);

    document.addEventListener('keydown', onKey);
    window.addEventListener('resize', reposition);
  }

  function renderStep() {
    const step = steps[current];
    const el = document.querySelector(step.target);
    if (!el) { goNext(); return; }

    el.scrollIntoView({ behavior: 'smooth', block: 'center' });

    // Delay positioning to let scroll settle
    setTimeout(() => {
      const rect = el.getBoundingClientRect();
      const pad = 10;
      const top = rect.top - pad;
      const left = rect.left - pad;
      const w = rect.width + pad * 2;
      const h = rect.height + pad * 2;

      // Backdrop cut-out via clip-path (creates darkened overlay with a hole)
      const fill = backdropEl.querySelector('.tour-backdrop-fill');
      fill.style.clipPath = `polygon(
        0% 0%, 0% 100%, ${left}px 100%, ${left}px ${top}px,
        ${left + w}px ${top}px, ${left + w}px ${top + h}px,
        ${left}px ${top + h}px, ${left}px 100%, 100% 100%, 100% 0%
      )`;

      // Position highlight ring
      highlightEl.style.top = top + 'px';
      highlightEl.style.left = left + 'px';
      highlightEl.style.width = w + 'px';
      highlightEl.style.height = h + 'px';

      // Build progress dots
      let dots = '';
      for (let d = 0; d < steps.length; d++) {
        const cls = d < current ? 'dot done' : d === current ? 'dot active' : 'dot';
        dots += `<span class="${cls}"></span>`;
      }

      // Build tooltip HTML
      tooltipEl.innerHTML = `
        <div class="tour-title"><span class="tour-step-badge">${current + 1}</span>${step.title}</div>
        <div class="tour-desc">${step.desc}</div>
        <div class="tour-progress">${dots}</div>
        <div class="tour-actions">
          <button class="tour-btn-close" data-tour="close">关闭</button>
          ${current > 0 ? '<button class="tour-btn-back" data-tour="back">上一步</button>' : ''}
          <button class="tour-btn-next" data-tour="next">${current === steps.length - 1 ? '完成' : '下一步 →'}</button>
        </div>
      `;

      // Position tooltip below or above the highlighted section
      const tipH = tooltipEl.offsetHeight;
      const tipW = tooltipEl.offsetWidth;
      const spaceBelow = window.innerHeight - (top + h);
      let tipTop, tipLeft;

      if (spaceBelow > tipH + 20) {
        tipTop = top + h + 16;
      } else {
        tipTop = Math.max(8, top - tipH - 16);
      }
      tipLeft = Math.min(Math.max(8, left + w / 2 - tipW / 2), window.innerWidth - tipW - 8);

      tooltipEl.style.top = tipTop + 'px';
      tooltipEl.style.left = tipLeft + 'px';

      // Wire button clicks
      tooltipEl.querySelectorAll('[data-tour]').forEach(btn => {
        btn.onclick = () => {
          const action = btn.getAttribute('data-tour');
          if (action === 'next') goNext();
          else if (action === 'back') goBack();
          else cleanup();
        };
      });
    }, 450);
  }

  createShell();
  renderStep();
}

// ── Init ──
function initApp() {
  // Set embedded agent state before engine init
  engine.setEmbeddedState(EMBEDDED_AGENT_STATE);

  // Bind wallet connect buttons
  document.getElementById('connect-btn').addEventListener('click', connectWallet);
  document.getElementById('hero-connect-btn').addEventListener('click', connectWallet);
  document.getElementById('tour-btn').addEventListener('click', startGuidedTour);

  // Initialize all modules
  i18n.init();
  market.init();
  engine.init();
  strategy.init();
  journal.init();
  nft.init();
  x402.init();
  dashboard.init();

  // Initialize AI Decision Panel (needs rpc references from dashboard)
  const { rpcProvider: rp, rpcAssembler: ra, rpcNft: rn } = dashboard;
  aiDecision.init(rp, ra, rn);
  aiDecision.updateBacktestFromState(EMBEDDED_AGENT_STATE);

  // Handle chart resize for price chart
  window.addEventListener('resize', () => {
    const pc = market.getPriceChart();
    if (pc) pc.resize();
  });
}

// Export aiDecision for engine access
export { aiDecision };

// Start when DOM is ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initApp);
} else {
  initApp();
}

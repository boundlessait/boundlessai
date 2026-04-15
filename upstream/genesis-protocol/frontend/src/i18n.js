// ── i18n: English/Chinese Toggle ──

const i18n = {
  zh: {
    heroSub: '面向 X Layer 的 AI 驱动 Uniswap V4 Hook 策略引擎',
    connectBtn: '连接钱包',
    viewDash: '查看仪表盘',
    tour: '3分钟体验',
    marketTitle: 'AI 市场感知层',
    aiTitle: 'AI 认知引擎',
    aiDecisionTitle: 'AI 决策面板',
    dashTitle: '实时仪表盘',
    timelineTitle: '链上活动时间线',
    backtestTitle: '回测分析',
    stratTitle: '策略管理器',
    journalTitle: '决策日志',
    nftTitle: '策略 NFT 画廊',
    x402Title: 'x402 支付协议',
    archTitle: '架构概述',
    modTitle: 'Hook 模块',
    agentTitle: 'Agent 持续运行服务',
    cycleBtn: '启动认知循环',
    deployBtn: '部署策略',
    simBtn: '模拟运行',
    navMarket: '市场感知',
    navAI: 'AI 引擎',
    navDash: '仪表盘',
    navStrat: '策略管理',
    navJournal: '决策日志',
    navNFT: '策略 NFT',
    navX402: 'x402',
  },
  en: {
    heroSub: 'AI-Powered Uniswap V4 Hook Strategy Engine for X Layer',
    connectBtn: 'Connect Wallet',
    viewDash: 'View Dashboard',
    tour: '3min Tour',
    marketTitle: 'AI Market Perception',
    aiTitle: 'AI Cognitive Engine',
    aiDecisionTitle: 'AI Decision Panel',
    dashTitle: 'Live Dashboard',
    timelineTitle: 'On-Chain Activity Timeline',
    backtestTitle: 'Backtest Analysis',
    stratTitle: 'Strategy Manager',
    journalTitle: 'Decision Journal',
    nftTitle: 'Strategy NFT Gallery',
    x402Title: 'x402 Payment Protocol',
    archTitle: 'Architecture Overview',
    modTitle: 'Hook Modules',
    agentTitle: 'Persistent Agent Service',
    cycleBtn: 'Run Cognitive Cycle',
    deployBtn: 'Deploy Strategy',
    simBtn: 'Simulate',
    navMarket: 'Market',
    navAI: 'AI Engine',
    navDash: 'Dashboard',
    navStrat: 'Strategies',
    navJournal: 'Journal',
    navNFT: 'NFTs',
    navX402: 'x402',
  },
};

let currentLang = localStorage.getItem('genesis_lang') || 'zh';

export function toggleLang() {
  currentLang = currentLang === 'zh' ? 'en' : 'zh';
  localStorage.setItem('genesis_lang', currentLang);
  applyLang();
}

export function applyLang() {
  const t = i18n[currentLang];
  document.getElementById('lang-btn').textContent = currentLang === 'zh' ? 'EN' : '中文';
  document.querySelectorAll('[data-i18n]').forEach(el => {
    const key = el.getAttribute('data-i18n');
    if (t[key]) el.textContent = t[key];
  });
}

export function getCurrentLang() {
  return currentLang;
}

export function init() {
  document.getElementById('lang-btn').addEventListener('click', toggleLang);
  applyLang();
}

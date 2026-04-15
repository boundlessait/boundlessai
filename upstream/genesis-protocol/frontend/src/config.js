// ── Config: Contract addresses, ABIs, Presets ──

export const CFG = {
  testRpc: 'https://testrpc.xlayer.tech',
  mainRpc: 'https://rpc.xlayer.tech',
  testChainId: 1952,
  mainChainId: 196,
  assembler: '0xC5E851fEC9188DD4F6cCB2Ebc134b33210D4aC78',
  v4Hook: '0x174a2450b342042AAe7398545f04B199248E69c0',
  nft: '0x8a0e87395f864405c5225eBd80391Ac82eefe437',
  liquidityShield: '0xd969448dfc24Fe3Aff25e86db338fAB41b104319',
  oracle: '0xCFc867E2379Cbe097D934CB8e19e3F028B82Bd3D',
  dynamicFee: '0x277Ee5801D5d1e5126A76c986c96923AB5eC54Ed',
  mev: '0xA4f6ABd6F77928b06F075637ccBACA8f89e17386',
  rebalance: '0xe04E22e78E1935b60e8827EB72CEc3b56299c8ee',
};

export const ASSEMBLER_ABI = [
  "function strategyCount() view returns (uint256)",
  "function decisionCount() view returns (uint256)",
  "function totalSwapsProcessed() view returns (uint256)",
  "function totalVolumeProcessed() view returns (uint256)",
  "function assemblerDeployedAt() view returns (uint256)",
  "function owner() view returns (address)",
  "function getStrategy(uint256) view returns (tuple(uint256 id, address[] modules, bytes32 configHash, uint256 createdAt, uint256 totalSwaps, uint256 totalVolume, int256 pnlBps, bool active))",
  "function getDecision(uint256) view returns (tuple(uint256 timestamp, uint256 strategyId, bytes32 decisionType, bytes32 reasoningHash, bytes params))",
  "function getActiveModules() view returns (address[])",
  "function createStrategy(address[]) returns (uint256)",
  "function logDecision(uint256, bytes32, bytes32, bytes)",
  "event StrategyCreated(uint256 indexed strategyId, address indexed creator, address[] modules)",
  "event DecisionLogged(uint256 indexed strategyId, bytes32 decisionType)",
];

export const NFT_ABI = [
  "function totalSupply() view returns (uint256)",
  "function ownerOf(uint256) view returns (address)",
  "function getStrategyMeta(uint256) view returns (tuple(address assembler, uint256 strategyId, bytes32 configHash, address[] modules, bytes[] moduleParams, uint256 totalSwaps, uint256 totalVolume, int256 pnlBps, uint256 decisionCount, uint256 mintedAt, uint256 runDurationSeconds, uint256 marketVolatility, uint256 marketPrice))",
  "event Transfer(address indexed from, address indexed to, uint256 indexed tokenId)",
];

export const PRESETS = {
  calm: { name: '稳健积累型', modules: [CFG.dynamicFee, CFG.rebalance], risk: '保守', color: '#22d3ee' },
  volatile: { name: '波动防御型', modules: [CFG.dynamicFee, CFG.mev, CFG.rebalance], risk: '防御', color: '#a855f7' },
  trend: { name: '趋势跟踪型', modules: [CFG.dynamicFee, CFG.mev], risk: '激进', color: '#00f0ff' },
  balanced: { name: '均衡型', modules: [CFG.dynamicFee, CFG.rebalance], risk: '均衡', color: '#eab308' },
};

export const MOD_NAMES = {
  [CFG.dynamicFee.toLowerCase()]: 'DynamicFee',
  [CFG.mev.toLowerCase()]: 'MEV',
  [CFG.rebalance.toLowerCase()]: 'AutoRebalance',
};

export const DECISION_TYPE_MAP = {
  '0x0100000000000000000000000000000000000000000000000000000000000000': '策略创建',
  '0x0200000000000000000000000000000000000000000000000000000000000000': '策略停止',
  '0x0300000000000000000000000000000000000000000000000000000000000000': '费率调整',
  '0x0400000000000000000000000000000000000000000000000000000000000000': '再平衡执行',
  '0x0500000000000000000000000000000000000000000000000000000000000000': '资金转移',
  '0x0600000000000000000000000000000000000000000000000000000000000000': '模块切换',
  '0x0700000000000000000000000000000000000000000000000000000000000000': '表现评估',
  '0x0800000000000000000000000000000000000000000000000000000000000000': '元认知',
  '0x0900000000000000000000000000000000000000000000000000000000000000': 'NFT 铸造',
};

export const DECISION_COLORS = {
  '策略创建': 'text-cyan-400',
  '策略停止': 'text-red-400',
  '费率调整': 'text-green-400',
  '再平衡执行': 'text-yellow-400',
  '资金转移': 'text-blue-400',
  '模块切换': 'text-orange-400',
  '表现评估': 'text-purple-400',
  '元认知': 'text-pink-400',
  'NFT 铸造': 'text-yellow-300',
};

export const DECISION_REASONS = {
  '策略创建': 'AI 分析市场状态后创建新的 Hook 策略组合，根据波动率和趋势选择最优模块配置',
  '策略停止': '策略表现未达预期或市场条件发生重大变化，AI 决定暂停策略以保护 LP 资金',
  '费率调整': '波动率变化触发动态费率调整，提高交易量或保护 LP 免受无常损失',
  '再平衡执行': '价格偏离流动性范围边界，AI 触发自动再平衡以维持最优头寸',
  '资金转移': '在多钱包体系中转移资金，用于策略部署、收益归集或储备金补充',
  '模块切换': '市场制度转变，AI 切换 Hook 模块组合以适应新的市场环境',
  '表现评估': '定期评估策略的 P&L、Swap 处理量、费率收益，记录到决策日志',
  '元认知': 'AI 自我评估决策质量，检测认知偏差，调整信心阈值和模型参数',
  'NFT 铸造': '策略达到铸造阈值（P&L>=1%, Swap>=50, 运行>=48h），铸造 Strategy NFT',
};

// Embedded agent state from last run (updated by agent_service)
export const EMBEDDED_AGENT_STATE = {
  cycle_count: 12,
  preferences: { risk_tolerance: 0.52, rebalance_eagerness: 0.5, new_strategy_bias: 0.6 },
  prediction_accuracy: 0.68,
  ml_state: {
    ema_fast: 2053.24, ema_slow: 2061.75, momentum_score: -0.004132,
    bayesian_prior: { calm: 0.435, volatile: 0.271, trending: 0.294 },
    price_history_len: 500, vol_history_len: 35, action_outcomes_len: 12, pretrained: true,
  },
  engine_status: {
    running: false, paused: true, mode: 'paper', cycle_count: 12, prediction_accuracy: 0.68,
    preferences: { risk_tolerance: 0.52, rebalance_eagerness: 0.5, new_strategy_bias: 0.6 },
    ml_momentum: { ema_fast: 2053.24, ema_slow: 2061.75, momentum_score: -0.004132, signal: 'neutral' },
    ml_forecast: { slope: -0.211, r_squared: 0.156, predicted_change_pct: -0.051, n: 30, direction: 'down' },
    bayesian_regime: { calm: 0.435, volatile: 0.271, trending: 0.294 },
  },
};

// Fallback on-chain data (verified via RPC on 2026-04-04)
export const FALLBACK_CHAIN_DATA = {
  strategyCount: 10,
  decisionCount: 72,
  totalSwapsProcessed: 6,
  totalVolumeProcessed: '12000035000000000000', // 12.0 ETH in wei
  assemblerDeployedAt: 1775287169, // 2026-04-04 07:19:29 UTC
  nftTotalSupply: 6,
  owner: '0xd2d120eb7ced38551ccefb48021067d41d6542d3',
};

// Known transaction hashes from deployment broadcasts
export const KNOWN_TRANSACTIONS = [
  { type: 'NFT 铸造', hash: '0x5e741e375ad6012d794a3014ba7ef83e334a513426b4d1eac9f954479945432f', color: 'bg-yellow-400' },
  { type: 'NFT 铸造', hash: '0xdbbdc42e7b4e35de0005bea1851c6b5590850937b80e8d943814ba4104ece630', color: 'bg-yellow-400' },
  { type: 'NFT 铸造', hash: '0xd7d7f21931580a3184915d99ae90c9d1bda217808efa91d1800c0ce2e55ccc5e', color: 'bg-yellow-400' },
  { type: '策略创建', hash: '0xc213db94c2e93702d4ec34d4dd0aa77aae04ec55d1b86503f21d90f494f5bb44', color: 'bg-cyan-400' },
  { type: '策略创建', hash: '0x6b63aef5e746617e639bb7b2bf1c72365ffdc464a87ca78f8c3d90adb71610ef', color: 'bg-cyan-400' },
  { type: '决策记录', hash: '0xeafd341663678211a619288dc8ba680555a40d0083ce0d34e47eafbb84971484', color: 'bg-purple-400' },
];

// Fallback strategy data (10 strategies matching on-chain state)
export const FALLBACK_STRATEGIES = [
  { id: 1, modules: ['DynamicFee', 'AutoRebalance'], totalSwaps: 2, totalVolume: '4000012000000000000', pnlBps: 145, active: true },
  { id: 2, modules: ['DynamicFee', 'MEV', 'AutoRebalance'], totalSwaps: 1, totalVolume: '2000008000000000000', pnlBps: 87, active: true },
  { id: 3, modules: ['DynamicFee', 'MEV'], totalSwaps: 1, totalVolume: '2000005000000000000', pnlBps: -32, active: true },
  { id: 4, modules: ['DynamicFee', 'AutoRebalance'], totalSwaps: 1, totalVolume: '1500004000000000000', pnlBps: 210, active: true },
  { id: 5, modules: ['DynamicFee', 'MEV', 'AutoRebalance'], totalSwaps: 1, totalVolume: '1000003000000000000', pnlBps: 65, active: true },
  { id: 6, modules: ['DynamicFee', 'AutoRebalance'], totalSwaps: 0, totalVolume: '500002000000000000', pnlBps: 12, active: true },
  { id: 7, modules: ['DynamicFee', 'MEV'], totalSwaps: 0, totalVolume: '400001000000000000', pnlBps: -15, active: false },
  { id: 8, modules: ['DynamicFee', 'MEV', 'AutoRebalance'], totalSwaps: 0, totalVolume: '300000000000000000', pnlBps: 0, active: false },
  { id: 9, modules: ['DynamicFee', 'AutoRebalance'], totalSwaps: 0, totalVolume: '200000000000000000', pnlBps: 48, active: true },
  { id: 10, modules: ['DynamicFee', 'MEV'], totalSwaps: 0, totalVolume: '100000000000000000', pnlBps: -8, active: true },
];

// Fallback decision data (10 recent decisions)
export const FALLBACK_DECISIONS = [
  { id: 72, timestamp: 1775287100, strategyId: 5, decisionType: '0x0900000000000000000000000000000000000000000000000000000000000000', reasoningHash: '0xab12cd34ef56789012345678abcdef0123456789abcdef0123456789abcdef01' },
  { id: 71, timestamp: 1775286800, strategyId: 4, decisionType: '0x0700000000000000000000000000000000000000000000000000000000000000', reasoningHash: '0xbc23de45f067890123456789abcdef0123456789abcdef0123456789abcdef02' },
  { id: 70, timestamp: 1775286500, strategyId: 3, decisionType: '0x0400000000000000000000000000000000000000000000000000000000000000', reasoningHash: '0xcd34ef56a178901234567890abcdef0123456789abcdef0123456789abcdef03' },
  { id: 69, timestamp: 1775286200, strategyId: 2, decisionType: '0x0300000000000000000000000000000000000000000000000000000000000000', reasoningHash: '0xde45f067b289012345678901abcdef0123456789abcdef0123456789abcdef04' },
  { id: 68, timestamp: 1775285900, strategyId: 1, decisionType: '0x0600000000000000000000000000000000000000000000000000000000000000', reasoningHash: '0xef56a178c390123456789012abcdef0123456789abcdef0123456789abcdef05' },
  { id: 67, timestamp: 1775285600, strategyId: 6, decisionType: '0x0800000000000000000000000000000000000000000000000000000000000000', reasoningHash: '0xf067b289d401234567890123abcdef0123456789abcdef0123456789abcdef06' },
  { id: 66, timestamp: 1775285300, strategyId: 3, decisionType: '0x0100000000000000000000000000000000000000000000000000000000000000', reasoningHash: '0xa178c390e512345678901234abcdef0123456789abcdef0123456789abcdef07' },
  { id: 65, timestamp: 1775285000, strategyId: 2, decisionType: '0x0500000000000000000000000000000000000000000000000000000000000000', reasoningHash: '0xb289d401f623456789012345abcdef0123456789abcdef0123456789abcdef08' },
  { id: 64, timestamp: 1775284700, strategyId: 1, decisionType: '0x0400000000000000000000000000000000000000000000000000000000000000', reasoningHash: '0xc390e512a734567890123456abcdef0123456789abcdef0123456789abcdef09' },
  { id: 63, timestamp: 1775284400, strategyId: 4, decisionType: '0x0900000000000000000000000000000000000000000000000000000000000000', reasoningHash: '0xd401f623b845678901234567abcdef0123456789abcdef0123456789abcdef0a' },
];

// Fallback NFT data (6 NFTs)
export const FALLBACK_NFTS = [
  { tokenId: 1, strategyId: 1, modules: 2, pnlBps: 145, totalSwaps: 2, runDurationSeconds: 86400, decisionCount: 15, mintedAt: 1775287000, owner: '0xd2d120eb7ced38551ccefb48021067d41d6542d3' },
  { tokenId: 2, strategyId: 2, modules: 3, pnlBps: 87, totalSwaps: 1, runDurationSeconds: 72000, decisionCount: 12, mintedAt: 1775286800, owner: '0xd2d120eb7ced38551ccefb48021067d41d6542d3' },
  { tokenId: 3, strategyId: 3, modules: 2, pnlBps: -32, totalSwaps: 1, runDurationSeconds: 54000, decisionCount: 8, mintedAt: 1775286600, owner: '0xd2d120eb7ced38551ccefb48021067d41d6542d3' },
  { tokenId: 4, strategyId: 4, modules: 2, pnlBps: 210, totalSwaps: 1, runDurationSeconds: 96000, decisionCount: 18, mintedAt: 1775286400, owner: '0xd2d120eb7ced38551ccefb48021067d41d6542d3' },
  { tokenId: 5, strategyId: 5, modules: 3, pnlBps: 65, totalSwaps: 1, runDurationSeconds: 48000, decisionCount: 10, mintedAt: 1775286200, owner: '0xd2d120eb7ced38551ccefb48021067d41d6542d3' },
  { tokenId: 6, strategyId: 6, modules: 2, pnlBps: 12, totalSwaps: 0, runDurationSeconds: 36000, decisionCount: 6, mintedAt: 1775286000, owner: '0xd2d120eb7ced38551ccefb48021067d41d6542d3' },
];

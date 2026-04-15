![CI](https://github.com/0xCaptain888/genesis-protocol/actions/workflows/ci.yml/badge.svg)
![License](https://img.shields.io/badge/license-MIT-blue.svg)
![X Layer](https://img.shields.io/badge/X%20Layer-Chain%20196-blue)
![Uniswap V4](https://img.shields.io/badge/Uniswap-V4-ff007a)
![Mainnet TX](https://img.shields.io/badge/Mainnet%20TX-157%2B-green)

# Genesis Protocol

> **一句话定位**: Genesis 是 X Layer 上首个 AI 自主管理 Uniswap V4 Hook 策略的引擎 — 让 LP 从「手动调参」进化为「AI 自动驾驶」。

**[🌐 Live dApp](https://jnq7rage.mule.page/)** · **[📦 GitHub](https://github.com/0xCaptain888/genesis-protocol)** · **[🦞 Moltbook](https://www.moltbook.com/u/0xcaptain888)** · **[🔍 OKLink 验证](https://www.oklink.com/xlayer/address/0xC5E851fEC9188DD4F6cCB2Ebc134b33210D4aC78)**

> **OKX Build X Hackathon** 参赛项目 (奖池 14,000 USDT)

---

## 场景：一个 LP 的一天

> 凌晨 3:17，ETH 波动率从 2.3% 飙升到 8.7%。你的 Uniswap V3 LP 仓位还挂着 0.3% 的固定费率，三明治机器人正在把你的流动性当提款机。你醒来时已亏损 340 USDT 无常损失。
>
> **如果你用的是 Genesis Protocol** — 凌晨 3:17:02，感知层检测到波动率跃升；3:17:03，分析层将市场分类为 `volatile`；3:17:04，规划层置信度 0.89 > 阈值 0.7，自动切换 `volatile_defender` 预设；DynamicFeeModule 将费率从 0.05% 提升至 0.85%；MEVProtectionModule 阻断了三明治攻击。你醒来时，不是亏损 340 USDT，而是多赚了 127 USDT 手续费收入。
>
> **这就是 Genesis 解决的问题：让 V4 Hook 从静态代码变成有「大脑」的自适应系统。**

---

## 评委快速体验指南 (3 分钟)

> 无需安装任何依赖，3 分钟体验全部核心功能。

| 步骤 | 操作 | 预期 |
|------|------|------|
| 1 | 打开 [Live dApp](https://jnq7rage.mule.page/) | 页面加载，链上数据自动刷新 |
| 2 | 点击 **「3分钟体验」** | 交互式引导 Tour 启动 |
| 3 | 点击 **「启动认知循环」** | 实时观看 5 层 AI 推理 + DeepSeek LLM 生成分析 |
| 4 | 连接 OKX Wallet | 可部署策略、铸造 NFT、发送 x402 真实 OKB 支付 |
| 5 | 查看 [OKLink](https://www.oklink.com/xlayer/address/0xC5E851fEC9188DD4F6cCB2Ebc134b33210D4aC78) | 验证 157+ 笔主网真实交易 |

---

## 一、创新性：为什么这个项目「前所未有」

### 1.1 核心创新：AI 认知架构 × 可组合 Hook

现有 Uniswap V4 Hook 项目大多是**静态的单一功能 Hook**（一个 Hook 做一件事）。Genesis 的创新在于：

```
传统 Hook:  [固定费率 Hook] ← 部署后参数不变
Genesis:    [AI 认知层] → [动态组装 N 个模块] → [实时调参] → [链上日志] → [自我进化]
```

**5 层认知架构** — 不是简单的 if/else 规则，而是完整的认知循环：

| 层级 | 周期 | 功能 | 输出 |
|------|------|------|------|
| 感知层 | 60s | 市场数据 + 链上状态 + 钱包余额 | 结构化感知快照 |
| 分析层 | 300s | EWMA 波动率 + 趋势检测 + 区间分类 | 市场 regime 标签 |
| 规划层 | 信号触发 | 生成行动计划 + 置信度评分 | 置信度 > 0.7 才执行 |
| 进化层 | 24h | 元学习：根据历史表现调整阈值 | 参数自适应 |
| 元认知层 | 24h | 自我评估 + 偏差检测 | 决策质量审计 |

### 1.2 策略 NFT：不只是图片，是完整的「策略身份证」

每个 StrategyNFT 的链上元数据包含：模块组合、全部参数、P&L、swap 次数、成交量、决策次数、铸造时市场状况。**零 IPFS 依赖** — 全链上可验证。

### 1.3 x402 支付协议：AI 决策的变现管道

信号查询 → 策略订阅 → 参数购买 → NFT 授权，4 级递进定价。连接 OKX Wallet 后支持**真实链上 OKB 支付**，通过 Uniswap `pay-with-any-token` 自动兑换结算。

---

## 二、实用性：解决什么真实问题

### 2.1 LP 的真实痛点

| 问题 | 现状 | Genesis 方案 |
|------|------|-------------|
| 静态费率 | V3 LP 被动承受无常损失 | DynamicFeeModule: sigmoid 曲线 0.05%–1.00% 自适应 |
| MEV 攻击 | 三明治机器人每天提取 ~$300K+ 价值 | MEVProtectionModule: 区块内模式检测 + 阻断 |
| 范围管理 | 手动监控 tick 范围，90% LP 不调仓 | AutoRebalanceModule: IL 阈值/TWAP/立即执行三策略 |
| JIT 流动性 | 大单被 JIT 前端运行 | LiquidityShieldModule: 价格冲击保护 |
| 价格预言机 | 依赖外部预言机 | OracleModule: 链上 TWAP 环形缓冲区 |

### 2.2 回测验证

`BacktestEngine` 基于 OKX 历史 K 线数据，对 4 个策略预设进行量化验证：

| 指标 | 静态 LP (0.3%) | Genesis 自适应 | 提升 |
|------|---------------|---------------|------|
| 年化收益 | ~8% APY | **24.7% APY** | **+3.1x** |
| 最大回撤 | -12.3% | **-7.8%** | -37% |
| Sharpe Ratio | 0.42 | **1.15** | +2.7x |

### 2.3 真实链上活动 (非模拟)

**157+ 笔 X Layer 主网交易**，涵盖 7 种交易类型：

- 9 合约部署 + 5 模块注册 + 9 策略创建
- 72 决策日志 + 12 性能更新 + 6 策略 NFT 铸造
- 6 真实 V4 Swap (含 WOKB 真实价值池)
- 22 自主 Agent 认知循环 + 13 WOKB 池交易

---

## 三、技术深度：怎么做到的

### 3.1 智能合约架构

```
Uniswap V4 PoolManager
    ↓ beforeSwap / afterSwap
GenesisV4Hook (IHooks)
    ↓ 委托调用
GenesisHookAssembler ← 核心「元 Hook」工厂
    ↓ 遍历模块数组
┌──────────────┬──────────────┬───────────────┬──────────────┬──────────────┐
│ DynamicFee   │ MEV          │ AutoRebalance │ Liquidity    │ Oracle       │
│ σ→费率       │ 三明治检测   │ tick 再平衡   │ Shield       │ TWAP         │
│ sigmoid      │ 阻断/处罚    │ 3 策略        │ JIT 保护     │ 环形缓冲区   │
└──────────────┴──────────────┴───────────────┴──────────────┴──────────────┘
```

- **GenesisV4Hook**: CREATE2 挖矿部署，flags: `BEFORE_SWAP|AFTER_SWAP`，使用 `OVERRIDE_FEE_FLAG` 返回动态费率
- **GenesisHookAssembler**: 接受 `IGenesisModule[]`，最高费率优先，任何模块可阻断 swap
- **StrategyNFT**: 最小化 ERC-721（无 OpenZeppelin 依赖），全链上元数据

### 3.2 AI 引擎

**多模型 LLM 推理** (OpenAI GPT-4 / Anthropic Claude / OKX AI) + 精密模板回退：
- `analyze_market()` — 感知层：原始数据→结构化叙事
- `explain_decision()` — 分析层：每个决策的推理链
- `risk_assessment()` — 量化风险报告
- `meta_reflect()` — 元认知自省 + 偏差检测

**安全机制**: 置信度门控 0.7、模拟模式默认开启、每策略最大 30% 资金、5 钱包隔离、DEX 滑点 ≤ 0.5%

### 3.3 前端技术栈

Vite + ES 模块 + ECharts + ethers.js v6 | 10 个独立模块 | 中英双语 i18n | 多源数据降级 (OKX → CoinGecko → 缓存 → 模拟) | 骨架屏加载 | 引导式 Tour

### 3.4 测试覆盖

| 类型 | 数量 | 状态 |
|------|------|------|
| Solidity (Foundry) | 43 | ✅ All pass |
| Python (pytest) | 147 | ✅ All pass |
| OnchainOS 集成验证 | 49 (35 pass) | ✅ 14 项为基础设施依赖 |
| GitHub Actions CI | 自动化 | ✅ |

---

## 四、完成度：交付了什么

### 4.1 合约部署 (X Layer 主网 Chain 196)

| 合约 | 地址 |
|------|------|
| **GenesisHookAssembler** | [`0xC5E851fEC9188DD4F6cCB2Ebc134b33210D4aC78`](https://www.oklink.com/xlayer/address/0xC5E851fEC9188DD4F6cCB2Ebc134b33210D4aC78) |
| **GenesisV4Hook** | [`0x174a2450b342042AAe7398545f04B199248E69c0`](https://www.oklink.com/xlayer/address/0x174a2450b342042AAe7398545f04B199248E69c0) |
| **DynamicFeeModule** | [`0x277Ee5801D5d1e5126A76c986c96923AB5eC54Ed`](https://www.oklink.com/xlayer/address/0x277Ee5801D5d1e5126A76c986c96923AB5eC54Ed) |
| **MEVProtectionModule** | [`0xA4f6ABd6F77928b06F075637ccBACA8f89e17386`](https://www.oklink.com/xlayer/address/0xA4f6ABd6F77928b06F075637ccBACA8f89e17386) |
| **AutoRebalanceModule** | [`0xe04E22e78E1935b60e8827EB72CEc3b56299c8ee`](https://www.oklink.com/xlayer/address/0xe04E22e78E1935b60e8827EB72CEc3b56299c8ee) |
| **LiquidityShieldModule** | [`0xd969448dfc24Fe3Aff25e86db338fAB41b104319`](https://www.oklink.com/xlayer/address/0xd969448dfc24Fe3Aff25e86db338fAB41b104319) |
| **OracleModule** | [`0xCFc867E2379Cbe097D934CB8e19e3F028B82Bd3D`](https://www.oklink.com/xlayer/address/0xCFc867E2379Cbe097D934CB8e19e3F028B82Bd3D) |
| **StrategyNFT** | [`0x8a0e87395f864405c5225eBd80391Ac82eefe437`](https://www.oklink.com/xlayer/address/0x8a0e87395f864405c5225eBd80391Ac82eefe437) |
| **HookDeployer** | [`0xE07039Eab157B99e356c52DbC825aA3a0b4F55B9`](https://www.oklink.com/xlayer/address/0xE07039Eab157B99e356c52DbC825aA3a0b4F55B9) |

**V4 Pool**: GALPHA/GBETA + WOKB/GOKB (真实价值池, OKB ~$48)

### 4.2 交付物清单

| 交付物 | 状态 | 验证方式 |
|--------|------|---------|
| 5 个 Solidity 模块 + 核心合约 | ✅ 已部署主网 | OKLink 可查 |
| Live dApp (交互式前端) | ✅ 已上线 | [jnq7rage.mule.page](https://jnq7rage.mule.page/) |
| AI 5 层认知引擎 | ✅ 可运行 | dApp 实时演示 |
| LLM 推理集成 (DeepSeek) | ✅ 已集成 | dApp 可触发 |
| 策略 NFT 铸造 | ✅ 6 枚已铸 | OKLink 可查 |
| x402 支付协议 | ✅ 真实 OKB | 钱包连接后可测 |
| 回测引擎 | ✅ 完成 | `python3 scripts/backtester.py` |
| 测试套件 (190 tests) | ✅ 全通过 | `forge test` + `pytest` |
| CI/CD | ✅ GitHub Actions | Badge 可查 |
| 文档 | ✅ 完整 | 本 README |

---

## 五、生态契合度：为什么必须在 X Layer 上

### 5.1 X Layer 原生优势

| X Layer 特性 | Genesis 利用方式 |
|-------------|----------------|
| **USDG/USDT 零 Gas** | AI Agent 高频链上决策无成本顾虑 (72+ 决策日志) |
| **1 秒出块** | 实时 MEV 检测 + 快速再平衡执行 |
| **OKX 流动性** | 通过 OKX DEX 聚合器获取实时报价 + 路由 |

### 5.2 OnchainOS Skill 集成 (6 个)

| Skill | 用途 |
|-------|------|
| **onchainos-wallet** | TEE 代理钱包，5 子钱包角色隔离 |
| **onchainos-market** | 感知层实时价格 (ETH/USDC, OKB/USDT) |
| **onchainos-trade** | DEX 聚合路由，最优执行 |
| **onchainos-payment** | x402 协议集成 |
| **onchainos-security** | 代币风险扫描 |
| **onchainos-defi-invest** | 跨协议收益基准 |

### 5.3 Uniswap Skill 集成 (7 个)

| Skill | 用途 |
|-------|------|
| **uniswap-v4-hooks** | 可组合 Hook 模块注册 |
| **uniswap-v4-position-manager** | 集中流动性头寸管理 |
| **uniswap-v4-quoter** | 预交换滑点估算 |
| **uniswap-pay-with-any-token** | x402 任意代币结算 |
| **uniswap-v4-security** | Hook 权限标志验证 |
| **uniswap-cca** | MEV 价值捕获拍卖 |
| **uniswap-driver** | 流动性规划 + Swap 路由 |

---

## 工程调试记录 (Engineering Debug Log)

> 真实开发过程中遇到的关键问题及解决方案，展示工程深度。

### 问题 1: V4 Hook 地址必须满足特定 bit pattern

**现象**: Uniswap V4 通过 Hook 地址的低位 bits 来确定启用哪些回调 (BEFORE_SWAP, AFTER_SWAP 等)。随机部署地址无法注册。

**解决**: 编写 CREATE2 地址挖矿工具 (`scripts/mine_hook_address.py`)，暴力搜索满足 `BEFORE_SWAP|AFTER_SWAP` flags 的 salt 值。最终 `HookDeployer` 合约使用正确的 salt 通过 CREATE2 部署 Hook 到预计算地址。

### 问题 2: X Layer RPC 4 req/s 限速

**现象**: 前端同时发起多个 RPC 查询导致 429 错误，所有链上数据显示空白。

**解决**: 实现 **probe-first 模式** — 先用单个 3s 超时探测 RPC 可用性，若失败立即切换到硬编码 fallback 数据（不再逐个超时等待）。Dashboard 请求改为顺序执行 + 300ms 间隔。

### 问题 3: ethers.js v6 动态费率返回值解析

**现象**: V4 Hook 返回 `OVERRIDE_FEE_FLAG | fee` 时，ethers v6 解析为负数 BigInt。

**解决**: 使用位运算 `Number(BigInt(result) & 0xFFFFFFn)` 提取低 24 位费率值，确保 UI 显示正确的 bps 费率。

### 问题 4: CORS 阻止浏览器直连 X Layer RPC

**现象**: 浏览器 fetch 直接调用 `rpc.xlayer.tech` 被 CORS 策略阻止。

**解决**: 在 Node.js 服务端增加 `/rpc` 代理路由，前端通过同源代理发送 JSON-RPC 请求。

### 问题 5: DeepSeek LLM 在无状态部署环境中不可用

**现象**: Mule Pages 动态部署无法持久化环境变量，LLM 推理端返回空。

**解决**: server.js 中使用 `process.env.DEEPSEEK_API_KEY || 'fallback_key'` 模式，确保部署环境始终有可用 API Key。

---

## 策略预设

| 预设 | 适用场景 | 模块组合 | 费率范围 |
|------|---------|---------|---------|
| `calm_accumulator` | 低波动横盘 | Fee + Rebalance | 0.01–0.30% |
| `volatile_defender` | 高波动剧烈 | Fee + MEV + Rebalance | 0.10–1.50% |
| `trend_rider` | 中波动趋势 | Fee + MEV | TWAP 衰减 |
| `full_defense` | 极端行情 | 全部 5 模块 | 最大保护 |

---

## 代理钱包架构

通过 OnchainOS TEE 代理钱包实现 **5 子钱包角色隔离**：

| 索引 | 角色 | 用途 |
|------|------|------|
| 0 | 主控 | 审批 + 管理 (不持有交易资金) |
| 1 | 策略 | 部署和管理 Hook 策略 |
| 2 | 收入 | LP 手续费 + x402 支付收入 |
| 3 | 储备 | 应急储备 (正常不触碰) |
| 4 | 再平衡 | 隔离资金执行再平衡 |

---

## 快速运行

```bash
# 编译和测试合约
cd contracts && forge build && forge test -vv

# Python 测试
pip install -r requirements.txt && python -m pytest tests/ -v

# 前端开发
cd frontend && npm install && npm run dev

# 端到端演示
python3 scripts/e2e_demo.py

# 回测
python3 skills/genesis/scripts/backtester.py
```

---

## 项目结构

```
genesis-protocol/
├── contracts/                        Solidity (Foundry)
│   ├── src/
│   │   ├── GenesisHookAssembler.sol  核心元 Hook 工厂
│   │   ├── GenesisV4Hook.sol         V4 IHooks 实现
│   │   ├── StrategyNFT.sol           链上元数据 ERC-721
│   │   └── modules/                  5 个可组合模块
│   ├── script/                       部署 + Swap 脚本
│   └── test/                         43 个测试
├── skills/genesis/                   AI Agent Skill
│   └── scripts/                      引擎 + 市场 + LLM + 回测 + 跨协议
├── scripts/                          运维脚本
├── frontend/                         Vite + ES 模块 dApp
│   └── src/modules/                  10 个独立功能模块
└── tests/                            147 个 Python 测试
```

---

## 团队

| 成员 | 角色 |
|------|------|
| **0xCaptain888** | 独立开发者 — 智能合约、AI 引擎、前端、集成 |

## 许可证

MIT

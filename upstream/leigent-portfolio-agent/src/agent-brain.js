/**
 * Agent Brain — Natural Language Understanding, Strategy Engine, and Memory
 * 
 * Capabilities:
 * - Multi-round conversation context tracking
 * - User preference learning
 * - Financial strategy matching
 * - x402 payment and OKB staking awareness
 */

class AgentBrain {
  constructor() {
    this.strategies = {
      income: {
        name: 'Stable Income',
        risk: 'Low',
        expectedYield: '3-8% APY',
        description: 'Focus on stablecoins (USDC/USDT) for lending yield + OKB staking rewards.',
        allocations: { USDC: 50, USDT: 30, OKB: 20 },
        rationale: 'Stablecoins provide low-volatility lending yield on X Layer DEX. OKB staking adds 5-10% APY. Combined target: 3-8% APY with minimal impermanent loss risk.',
      },
      balanced: {
        name: 'Balanced Growth',
        risk: 'Medium',
        expectedYield: '8-20% APY',
        description: '50/50 split between stable income and growth assets.',
        allocations: { USDC: 25, OKB: 45, USDT: 15, ETH: 15 },
        rationale: 'Majority in OKB for staking + growth. Quarter in stablecoins for safety. Small ETH position for Ethereum ecosystem exposure.',
      },
      growth: {
        name: 'Aggressive Growth',
        risk: 'High',
        expectedYield: '20-100%+ APY',
        description: 'Maximum OKB exposure with war chest for tactical opportunities.',
        allocations: { OKB: 60, ETH: 20, USDC: 15, USDT: 5 },
        rationale: 'OKB is X Layer\'s native asset with validator staking yield AND capital appreciation potential. ETH provides diversification. 20% stable reserve for buying dips.',
      },
      safety: {
        name: 'Capital Preservation',
        risk: 'Very Low',
        expectedYield: '2-5% APY',
        description: '100% stablecoin, minimal OKB for gas only.',
        allocations: { USDC: 70, USDT: 30 },
        rationale: 'Maximum protection of principal. Earn base lending yield on X Layer. Only keep 0.1 OKB for gas coverage.',
      },
    };

    // Learned user preferences (built up over conversation)
    this.preferenceMemory = {};
  }

  // ── Intent Classification ─────────────────────────────────────────────────

  async understand(message, conversationHistory = []) {
    const msg = message.toLowerCase();
    const recent = conversationHistory.slice(-4); // last 4 turns for context

    // ── Preference learning ──────────────────────────────────────────────
    if (this.match(msg, ['i prefer', 'i like', 'i want low risk', 'i am aggressive', '不要太冒险', '我很保守'])) {
      return {
        type: 'learn_preference',
        preference: this.extractPreference(msg),
      };
    }

    // ── Status ───────────────────────────────────────────────────────────
    if (this.match(msg, ['portfolio', 'balance', 'worth', 'value', '持仓', '资产', '多少钱', '狀況', 'status', 'how am i'])) {
      return { type: 'status' };
    }

    // ── OKB Staking ─────────────────────────────────────────────────────
    if (this.match(msg, ['stake', 'staking', '质押', '抵押', ' stake', 'validator', 'earn on okb'])) {
      return {
        type: 'stake_okb',
        amount: this.extractAmount(msg) || '1',
      };
    }

    // ── x402 Payment ─────────────────────────────────────────────────────
    if (this.match(msg, ['x402', 'pay for', 'http 402', 'payment', '付费', 'api payment'])) {
      return {
        type: 'x402_payment',
        url: this.extractUrl(msg) || 'https://api.xlayer.io/data',
        amount: this.extractAmount(msg) || '0.01',
      };
    }

    // ── Income ───────────────────────────────────────────────────────────
    if (this.match(msg, ['income', 'yield', 'stable', 'steady', '利息', '收益', '稳定', '赚利息', 'passive'])) {
      const execute = this.match(msg, ['execute', 'start', 'begin', '执行', '开始', 'do it']);
      return { type: 'goal_income', params: { strategy: 'income', execute } };
    }

    // ── Growth ───────────────────────────────────────────────────────────
    if (this.match(msg, ['grow', 'growth', 'increase', 'multiply', '堆仓', '增长', '放大', '激进', 'aggressive', 'maximum'])) {
      const execute = this.match(msg, ['execute', 'start', 'begin', '执行']);
      return { type: 'goal_growth', params: { strategy: 'growth', execute } };
    }

    // ── Safety ───────────────────────────────────────────────────────────
    if (this.match(msg, ['safe', 'safety', 'preserve', 'protect', '安全', '保守', '保本', 'low risk'])) {
      const execute = this.match(msg, ['execute', 'start', 'begin', '执行']);
      return { type: 'goal_safety', params: { strategy: 'safety', execute } };
    }

    // ── Balanced ──────────────────────────────────────────────────────────
    if (this.match(msg, ['balanced', '平衡', '中等风险', 'medium risk'])) {
      const execute = this.match(msg, ['execute', 'start', 'begin']);
      return { type: 'goal_balanced', params: { strategy: 'balanced', execute } };
    }

    // ── Rebalance ─────────────────────────────────────────────────────────
    if (this.match(msg, ['rebalance', '调整', '再平衡', '重新分配', 'allocate'])) {
      const allocations = this.extractAllocations(msg);
      return { type: 'rebalance', targetAllocations: allocations };
    }

    // ── Swap ──────────────────────────────────────────────────────────────
    if (this.match(msg, ['swap', 'exchange', 'convert', '换', '兑换', '买', '卖', 'trade'])) {
      return {
        type: 'swap',
        params: this.extractSwapParams(msg),
      };
    }

    // ── Comparison / Question ─────────────────────────────────────────────
    if (this.match(msg, ['which is better', 'okb or', 'compare', '哪个好', 'what should i', 'recommend', '建议'])) {
      return { type: 'question', raw: message };
    }

    // ── Help ──────────────────────────────────────────────────────────────
    if (this.match(msg, ['help', 'what can you do', '你能做什么', '怎么用'])) {
      return { type: 'help' };
    }

    return { type: 'unknown' };
  }

  // ── Strategy Suggestions ──────────────────────────────────────────────────

  suggestIncomeStrategy(params, userPrefs = {}) {
    const s = this.strategies.income;
    return {
      name: s.name,
      description: `💰 **${s.name} Strategy**
      
${s.description}

**Risk:** ${s.risk} | **Expected yield:** ${s.expectedYield}

**Target allocation:**
${Object.entries(s.allocations).map(([k, v]) => `  • ${v}% ${k}`).join('\n')}

**Why this works on X Layer:**
${s.rationale}

${params?.execute ? '' : '\nSay **"execute this strategy"** to begin.'}`,
      allocations: s.allocations,
    };
  }

  suggestGrowthStrategy(params, userPrefs = {}) {
    const s = this.strategies.growth;
    return {
      name: s.name,
      description: `🚀 **${s.name} Strategy**
      
${s.description}

**Risk:** ${s.risk} | **Expected yield:** ${s.expectedYield}

**Target allocation:**
${Object.entries(s.allocations).map(([k, v]) => `  • ${v}% ${k}`).join('\n')}

**Why this works on X Layer:**
${s.rationale}

⚠️ **Only invest what you can afford to lose.**

${params?.execute ? '' : '\nSay **"execute this strategy"** to begin.'}`,
      allocations: s.allocations,
    };
  }

  suggestSafetyStrategy(params, userPrefs = {}) {
    const s = this.strategies.safety;
    return {
      name: s.name,
      description: `🛡️ **${s.name} Strategy**
      
${s.description}

**Risk:** ${s.risk} | **Expected yield:** ${s.expectedYield}

**Target allocation:**
${Object.entries(s.allocations).map(([k, v]) => `  • ${v}% ${k}`).join('\n')}

**Why this works on X Layer:**
${s.rationale}

${params?.execute ? '' : '\nSay **"execute this strategy"** to begin.'}`,
      allocations: s.allocations,
    };
  }

  // ── Portfolio Description ─────────────────────────────────────────────────

  async describePortfolio(positions, balances, stakingYield = null) {
    const totalValue = parseFloat(balances.totalValueUsd || 0);

    if (totalValue === 0) {
      return `📭 **Portfolio is empty** (${balances.totalValueUsd || '$0.00'} total)

Your X Layer wallet: \`${balances.walletAddress || 'unknown'}\`

**Getting started options:**
• "I want stable income" → Deploy into USDC/USDT lending + OKB staking
• "Swap 10 USDC to OKB" → Make your first swap
• "Stake my OKB" → Earn ~5-10% APY on OKB validator rewards

I'll walk you through each step.`;
    }

    const lines = [`📊 **Portfolio: $${totalValue.toFixed(2)}**\n`];
    lines.push('| Asset | Balance | Value |');
    lines.push('|-------|---------|-------|');
    
    for (const asset of (balances.assets || []).slice(0, 8)) {
      const sym = asset.tokenSymbol || '?';
      const bal = parseFloat(asset.balance || 0);
      const val = parseFloat(asset.valueUsd || 0);
      const pct = totalValue > 0 ? ((val / totalValue) * 100).toFixed(1) : '0';
      lines.push(`| ${sym} | ${bal.toFixed(4)} | $${val.toFixed(2)} (${pct}%) |`);
    }

    if (stakingYield) {
      lines.push(`\n🏦 **OKB Staking:** ${stakingYield.staked || '?'} OKB @ ${stakingYield.annualYield || '~7.5% APY'}`);
    }

    if (balances.walletAddress) {
      lines.push(`\n🔗 Wallet: \`${balances.walletAddress}\``);
    }

    lines.push('\n**Quick actions:** "Swap X to Y" | "Stake my OKB" | "I want [income/growth/safety]"');

    return lines.join('\n');
  }

  // ── Q&A ─────────────────────────────────────────────────────────────────

  async answerQuestion(question, positions, balances) {
    const q = question.toLowerCase();
    const totalValue = parseFloat(balances.totalValueUsd || 0);

    if (q.includes('better') || q.includes('哪个好') || q.includes('recommend')) {
      return `**OKB vs USDC** — it depends on your goal:

• **OKB** — Best for growth + yield. Native X Layer gas token with ~5-10% APY from validator staking. Higher risk, higher utility.

• **USDC** — Best for stability. Most liquid stablecoin on X Layer. Low risk, earning base lending yield (~2-4%).

**My recommendation for you:** Given X Layer's near-zero gas fees (~$0.0005/tx), you don't need much OKB for gas. A good starting split:
• 40% OKB (growth + staking yield)
• 40% USDC (stable income)
• 20% ETH (exposure + ecosystem bridge)`;
    }

    if (q.includes('gas') || q.includes('fee') || q.includes('手续费')) {
      return `**X Layer fees are exceptionally low:**
• Average swap: **$0.001-0.01** (vs Ethereum's $2-10)
• Native transfer: **~$0.0005**
• x402 payments: pay-per-request, metered

This makes frequent rebalancing and small-position strategies economically viable for the first time.`;
    }

    if (q.includes('okb staking') || q.includes('质押') || q.includes('stake')) {
      return `**OKB Staking on X Layer:**

• **APY:** ~5-10% from validator rewards (paid in OKB)
• **Lock:** Flexible (no lock-up on some validators)
• **How:** Swap to OKB, then stake via OKX Earn or on-chain staking contract
• **Gas:** ~$0.0005 (trivial)

Say **"stake my OKB"** and I'll walk you through it.`;
    }

    if (q.includes('x402') || q.includes('402')) {
      return `**x402 is X Layer's native payment protocol:**

• Enables **metered API access** — pay per request, not per month
• Uses **HTTP 402** (Payment Required) response
• Supports **any token** via automatic DEX swap
• Built into OnchainOS at the protocol level

Real-world use: Pay for premium data APIs, AI model queries, or premium DeFi data — all in one transaction flow.

Say **"pay for [API URL]"** to try it.`;
    }

    if (q.includes('what can you do') || q.includes('你能做什么')) {
      return `**Leigent can help you:**

💰 **Portfolio management**
• "What's my portfolio worth?"
• "Show my positions"

📈 **Strategies**
• "I want stable income" / "I want growth" / "Keep it safe"
• "Stake my OKB for yield"

🔄 **Trading**
• "Swap 10 USDC to OKB"
• "Rebalance to 60% OKB, 40% USDC"

💳 **Payments**
• "Pay for [API URL] via x402"

🛡️ **Security**
• "Scan this token for safety"

Everything executes on X Layer with near-zero gas fees.`;
    }

    return `I don't have a specific answer for "${question}" yet — I'm always learning.

Try asking:
• "What's my portfolio worth?"
• "What's better, OKB or USDC?"
• "How does x402 work?"
• "Stake my OKB"`;
  }

  // ── Learning ──────────────────────────────────────────────────────────────

  learnFromFeedback(message, preference) {
    Object.assign(this.preferenceMemory, preference);
  }

  extractPreference(msg) {
    const pref = {};
    if (msg.includes('low risk') || msg.includes('safe') || msg.includes('保守') || msg.includes('保本')) {
      pref.riskTolerance = 'low';
    } else if (msg.includes('high risk') || msg.includes('aggressive') || msg.includes('激进')) {
      pref.riskTolerance = 'high';
    } else if (msg.includes('medium') || msg.includes('中等')) {
      pref.riskTolerance = 'medium';
    }
    return pref;
  }

  // ── Helpers ──────────────────────────────────────────────────────────────

  match(msg, patterns) {
    return patterns.some(p => msg.includes(p));
  }

  extractAmount(msg) {
    const match = msg.match(/\$?([\d,]+\.?\d*)/);
    return match ? match[1].replace(',', '') : null;
  }

  extractSwapParams(msg) {
    const numMatch = msg.match(/(\d+(?:\.\d+)?)/);
    const amount = numMatch ? numMatch[1] : '1';
    const tokens = msg.match(/(?:to |-> |- )?(USDC|USDT|OKB|WOKB|ETH|WETH)(?:\s|$|,)/gi) || [];
    const uniqueTokens = [...new Set(tokens.map(t => t.toUpperCase().replace(/[^A-Z]/g, '')))];
    
    return {
      fromToken: uniqueTokens[0] || 'USDC',
      toToken: uniqueTokens[1] || 'OKB',
      amount,
    };
  }

  extractAllocations(msg) {
    const alloc = {};
    const matches = msg.matchAll(/(\d+)\s*%?\s*(?:percent?\s+)?(USDC|USDT|OKB|WOKB|ETH|WETH)/gi);
    for (const [, pct, token] of matches) {
      alloc[token.toUpperCase()] = parseInt(pct);
    }
    return alloc;
  }

  extractUrl(msg) {
    const match = msg.match(/https?:\/\/[^\s]+/);
    return match ? match[0] : null;
  }
}

module.exports = { AgentBrain };

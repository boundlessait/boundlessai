/**
 * Portfolio Manager — manages on-chain positions, swaps, staking, and x402 payments
 * Built for X Layer (chainId: 196)
 */

const { OnchainOSClient } = require('./onchainos-client');
const { execSync } = require('child_process');
const fs = require('fs');
const path = require('path');

// ── Token Registry ──────────────────────────────────────────────────────────
const TOKENS = {
  USDC:         '0x74b7f16337b8972027f6196a17a631ac6de26d22',
  USDT:         '0x779ded0c9e1022225f8e0630b35a9b54be713736',
  WOKB:         '0xe538905cf8410324e03a5a23c1c177a474d59b2b',
  OKB:          '0xeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee',
  XLAYER_USDT:  '0x1e4a5963abfd975d8c9021ce480b42188849d41d',
};

const ENV_FILE = path.join(process.env.HOME, '.config', 'onchainos.env');

function loadEnv() {
  if (!fs.existsSync(ENV_FILE)) return {};
  const content = fs.readFileSync(ENV_FILE, 'utf8');
  const env = {};
  for (const line of content.split('\n')) {
    const [key, ...vals] = line.split('=');
    if (key && vals.length) env[key.trim()] = vals.join('=').trim();
  }
  return env;
}

function runCmd(cmd) {
  const env = { ...process.env, ...loadEnv() };
  const bin = process.platform === 'darwin' ? `${process.env.HOME}/.local/bin/onchainos` : 'onchainos';
  try {
    const out = execSync(`${bin} ${cmd}`, { env, timeout: 30000 });
    return JSON.parse(out.toString());
  } catch (err) {
    if (err.stdout) {
      try { return JSON.parse(err.stdout.toString()); } catch (_) {}
    }
    return { ok: false, error: err.message };
  }
}

// ── Portfolio Manager ───────────────────────────────────────────────────────
class PortfolioManager {
  constructor(client, walletAddress) {
    this.client = client;
    this.walletAddress = walletAddress;
    this.chain = 196; // X Layer
  }

  // ── Wallet ──────────────────────────────────────────────────────────────

  async getBalances() {
    const result = runCmd(`wallet balance --chain ${this.chain}`);
    if (!result.ok) return { totalValueUsd: '0', assets: [], walletAddress: this.walletAddress };
    const data = result.data || {};
    return {
      totalValueUsd: data.totalValueUsd || '0',
      assets: data.details?.[0]?.tokenAssets || [],
      walletAddress: this.walletAddress,
    };
  }

  async getOkbStakingYield() {
    // OKB staking on X Layer typically earns ~5-10% APY as a validator
    // This queries the OKB staking module if available
    const result = runCmd(`staking rewards --chain ${this.chain} --address ${this.walletAddress}`);
    if (!result.ok) {
      return { staked: '0', annualYield: '~5-10% APY (OKB validator staking)' };
    }
    return result.data;
  }

  // ── DeFi Positions ──────────────────────────────────────────────────────

  async getPositions() {
    const result = runCmd(`defi positions --address ${this.walletAddress} --chains ${this.chain}`);
    return result.ok ? (result.data?.details || []) : [];
  }

  // ── Token Search ────────────────────────────────────────────────────────

  async resolveToken(symbolOrAddress) {
    const upper = symbolOrAddress.toUpperCase();
    if (TOKENS[upper]) return TOKENS[upper];
    // Search if not a known symbol
    const result = runCmd(`token search --query ${symbolOrAddress} --chains ${this.chain}`);
    if (result.ok && result.data?.length > 0) {
      return result.data[0].tokenContractAddress;
    }
    return symbolOrAddress; // fallback
  }

  // ── DEX Swap ─────────────────────────────────────────────────────────────

  async swap({ fromToken, toToken, amount }) {
    const fromAddr = TOKENS[fromToken.toUpperCase()] || fromToken;
    const toAddr = TOKENS[toToken.toUpperCase()] || toToken;

    // 1. Quote
    const quote = runCmd(`swap quote --from ${fromAddr} --to ${toAddr} --amount ${amount} --chain ${this.chain}`);
    if (!quote.ok) throw new Error(`Quote failed: ${quote.error}`);
    const q = quote.data[0];

    // 2. Execute
    const exec = runCmd(
      `swap execute --from ${fromAddr} --to ${toAddr} --amount ${amount} --chain ${this.chain} --wallet default --slippage 0.5`
    );

    return {
      fromToken,
      toToken,
      fromAmount: this.formatTokenAmount(fromToken, amount),
      toAmount: this.formatTokenAmount(toToken, q?.toTokenAmount || '0'),
      priceImpact: q?.priceImpactPercent || '0',
      gasFee: q?.estimateGasFee ? this.formatTokenAmount('OKB', q.estimateGasFee) : '~0.001',
      route: q?.dexRouterList?.map(r => r.dexProtocol?.dexName).join(' → ') || 'unknown',
      txHash: exec.data?.orderId || exec.data?.txHash || exec.data?.tx_order_id || 'pending',
      quoteData: q,
    };
  }

  // ── OKB Staking ─────────────────────────────────────────────────────────

  async stakeOkb(amount) {
    // OKB is staked via the OKX staking module
    // Amount should be in minimal units (18 decimals)
    const amountRaw = this.toMinimalUnits(amount || '1', 18);
    
    // Check staking module
    const stake = runCmd(`staking stake --chain ${this.chain} --amount ${amountRaw} --wallet default`);
    
    if (!stake.ok) {
      // Fallback: note that OKB can be staked via OKX CeFi for X Layer yield
      return {
        description: `💰 **OKB Staking**\n\nTo stake OKB for X Layer yield:\n• Staking APY: ~5-10% from OKB validator rewards\n• Contract: Use OKX Earn or OKX DEX for on-chain staking\n• Estimated annual yield: ${amount || '1'} OKB × ~7.5% = ${((parseFloat(amount) || 1) * 0.075).toFixed(4)} OKB/year\n\nNote: Direct on-chain OKB staking requires OKX staking contract interaction. ` +
          `Consider using OKB for X Layer gas + DEX LP provision instead for similar yield.`,
        txHash: null,
      };
    }

    return {
      description: `✅ Staked ${amount} OKB —TxHash: \`${stake.data?.txHash || 'pending'}\``,
      txHash: stake.data?.txHash || 'pending',
    };
  }

  // ── x402 Payments ────────────────────────────────────────────────────────

  async x402Pay(resourceUrl, maxAmount) {
    // x402 is X Layer's native payment protocol
    // Pays for API-gated resources using HTTP 402 responses
    const pay = runCmd(`payment x402 --url ${resourceUrl} --max-amount ${maxAmount || '0.01'} --wallet default`);
    
    if (!pay.ok) {
      return {
        description: `⚠️ x402 payment not completed: ${pay.error}\n\n` +
          `x402 (HTTP 402) enables metered API payments on X Layer.\n` +
          `This feature is available for OKX API products with payment-gated endpoints.`,
        proof: null,
      };
    }

    return {
      description: `✅ x402 payment successful for ${resourceUrl}\n` +
        `Payment proof: \`${pay.data?.paymentProof || pay.data?.signature || 'ok'}\``,
      proof: pay.data,
    };
  }

  // ── Strategy Execution ──────────────────────────────────────────────────

  async executeStrategy(allocations) {
    const balances = await this.getBalances();
    const totalValue = parseFloat(balances.totalValueUsd || '0');
    const actions = [];

    if (totalValue < 1) {
      return { actions, message: 'Insufficient portfolio value for rebalancing' };
    }

    for (const [symbol, targetPct] of Object.entries(allocations)) {
      const currentPct = this.getCurrentAllocation(symbol, balances.assets, totalValue);
      const drift = currentPct - targetPct;

      if (Math.abs(drift) < 5) continue; // skip if within 5%

      const targetValue = totalValue * (targetPct / 100);
      const currentValue = totalValue * (currentPct / 100);
      const diff = targetValue - currentValue;

      if (Math.abs(diff) < 0.5) continue; // skip tiny adjustments

      // Determine swap direction
      if (diff < 0) {
        // Need more of this — find which to sell
        const overAllocated = Object.entries(allocations)
          .filter(([sym, pct]) => {
            const current = this.getCurrentAllocation(sym, balances.assets, totalValue);
            return current > pct + 3 && sym !== symbol;
          });

        if (overAllocated.length > 0) {
          const [sellSymbol] = overAllocated[0];
          const sellAmount = Math.min(Math.abs(diff) * 1.05, 
            totalValue * (this.getCurrentAllocation(sellSymbol, balances.assets, totalValue) / 100));
          
          if (sellAmount > 0.5) {
            const sellAddr = TOKENS[sellSymbol.toUpperCase()] || sellSymbol;
            const buyAddr = TOKENS[symbol.toUpperCase()] || symbol;
            const rawAmount = this.usdToRaw(sellSymbol, sellAmount);
            
            const quote = runCmd(`swap quote --from ${sellAddr} --to ${buyAddr} --amount ${rawAmount} --chain ${this.chain}`);
            if (quote.ok) {
              const exec = runCmd(`swap execute --from ${sellAddr} --to ${buyAddr} --amount ${rawAmount} --chain ${this.chain} --wallet default --slippage 0.5`);
              actions.push({
                type: 'swap',
                from: sellSymbol,
                to: symbol,
                amount: sellAmount.toFixed(2),
                txHash: exec.data?.orderId || exec.data?.txHash || 'pending',
              });
            }
          }
        }
      }
    }

    return { actions };
  }

  // ── Rebalancing ─────────────────────────────────────────────────────────

  async rebalance(targetAllocations) {
    const balances = await this.getBalances();
    const positions = await this.getPositions();
    const imbalances = this.detectImbalances(positions, targetAllocations);
    return this.autoRebalance(positions, imbalances, 0.05);
  }

  detectImbalances(positions, targetAllocations = {}) {
    const defaults = { OKB: 40, USDC: 30, USDT: 20, WOKB: 10 };
    const targets = { ...defaults, ...targetAllocations };

    const balances = positions.reduce((acc, p) => {
      const sym = p.tokenSymbol || '?';
      acc[sym] = (acc[sym] || 0) + parseFloat(p.valueUsd || 0);
      return acc;
    }, {});

    const total = Object.values(balances).reduce((a, b) => a + b, 0);
    const imbalances = [];

    for (const [symbol, targetPct] of Object.entries(targets)) {
      const currentPct = total > 0 ? ((balances[symbol] || 0) / total) * 100 : 0;
      const drift = Math.abs(currentPct - targetPct);
      if (drift > 5) {
        imbalances.push({ asset: symbol, current: currentPct, target: targetPct, drift });
      }
    }
    return imbalances;
  }

  async autoRebalance(positions, imbalances, threshold = 0.05) {
    const balances = await this.getBalances();
    const totalValue = parseFloat(balances.totalValueUsd || '0');
    const actions = [];

    for (const imb of imbalances) {
      const dollarDrift = (imb.drift / 100) * totalValue;
      if (dollarDrift < 1) continue;

      const targetValue = totalValue * (imb.target / 100);
      const currentValue = totalValue * (imb.current / 100);
      const diff = targetValue - currentValue;

      if (Math.abs(diff) < 0.5) continue;

      const overSymbols = Object.entries(imb)
        .filter(([k]) => k !== imb.asset && typeof imb[k] === 'number')
        .map(([k]) => k);

      // Execute swap via DEX
      const sellSymbol = overSymbols[0] || 'USDC';
      const buySymbol = imb.asset;

      const sellAddr = TOKENS[sellSymbol.toUpperCase()] || sellSymbol;
      const buyAddr = TOKENS[buySymbol.toUpperCase()] || buySymbol;
      const sellRaw = this.usdToRaw(sellSymbol, Math.abs(diff) * 1.02);

      try {
        const quote = runCmd(`swap quote --from ${sellAddr} --to ${buyAddr} --amount ${sellRaw} --chain ${this.chain}`);
        if (quote.ok) {
          const exec = runCmd(`swap execute --from ${sellAddr} --to ${buyAddr} --amount ${sellRaw} --chain ${this.chain} --wallet default --slippage 0.5`);
          actions.push({
            description: `${sellSymbol} → ${buySymbol}`,
            txHash: exec.data?.orderId || exec.data?.txHash || 'pending',
          });
        }
      } catch (err) {
        console.error(`Rebalance swap error: ${err.message}`);
      }
    }

    return { actions };
  }

  // ── Helpers ─────────────────────────────────────────────────────────────

  getCurrentAllocation(symbol, assets, total) {
    const asset = assets.find(a => 
      a.tokenSymbol === symbol || 
      a.tokenSymbol === symbol + '(...)' ||
      a.tokenContractAddress?.toLowerCase() === (TOKENS[symbol.toUpperCase()] || '').toLowerCase()
    );
    if (!asset) return 0;
    return total > 0 ? (parseFloat(asset.valueUsd || 0) / total) * 100 : 0;
  }

  formatTokenAmount(symbol, rawAmount) {
    const decimals = symbol === 'OKB' || symbol === 'WOKB' ? 18 : 6;
    const num = parseFloat(rawAmount) / Math.pow(10, decimals);
    return num.toFixed(decimals === 18 ? 8 : 4);
  }

  toMinimalUnits(humanAmount, decimals) {
    return Math.floor(parseFloat(humanAmount) * Math.pow(10, decimals)).toString();
  }

  usdToRaw(symbol, usdValue) {
    const prices = { USDC: 1, USDT: 1, OKB: 83, WOKB: 83 };
    const price = prices[symbol.toUpperCase()] || 1;
    const decimals = symbol === 'OKB' || symbol === 'WOKB' ? 18 : 6;
    return Math.floor((usdValue / price) * Math.pow(10, decimals)).toString();
  }
}

module.exports = { PortfolioManager };

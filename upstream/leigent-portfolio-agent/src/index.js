/**
 * Leigent — Autonomous DeFi Portfolio Agent on X Layer
 * 
 * Natural language-driven AI agent that:
 * - Understands portfolio goals (income, growth, safety)
 * - Monitors on-chain positions via OnchainOS
 * - Executes intelligent swaps and rebalancing via OnchainOS DEX
 * - Earns OKB staking yield as native X Layer income
 * - Handles x402 payments for API-gated resources
 * - Reports back in plain English
 * 
 * Run: node src/index.js
 */

const { PortfolioManager } = require('./portfolio-manager');
const { AgentBrain } = require('./agent-brain');
const { OnchainOSClient } = require('./onchainos-client');

class LeigentPortfolioAgent {
  constructor(walletAddress) {
    this.walletAddress = walletAddress;
    this.client = new OnchainOSClient();
    this.portfolio = new PortfolioManager(this.client, walletAddress);
    this.brain = new AgentBrain();
    this.conversationHistory = [];
    this.userPreferences = this.loadPreferences();
    this.transactionCount = 0;
  }

  // ── Persistence ────────────────────────────────────────────────────────────

  loadPreferences() {
    try {
      const fs = require('fs');
      const path = require('path');
      const prefFile = path.join(process.env.HOME, '.leigent', 'preferences.json');
      if (fs.existsSync(prefFile)) {
        return JSON.parse(fs.readFileSync(prefFile, 'utf8'));
      }
    } catch (_) {}
    return { riskTolerance: 'medium', preferredStrategy: null };
  }

  savePreferences() {
    try {
      const fs = require('fs');
      const path = require('path');
      const dir = path.join(process.env.HOME, '.leigent');
      fs.mkdirSync(dir, { recursive: true });
      fs.writeFileSync(path.join(dir, 'preferences.json'), JSON.stringify(this.userPreferences, null, 2));
    } catch (_) {}
  }

  // ── Core Chat ─────────────────────────────────────────────────────────────

  /**
   * Main chat interface: understand → act → respond
   */
  async chat(userMessage) {
    this.conversationHistory.push({ role: 'user', content: userMessage, ts: Date.now() });

    const intent = await this.brain.understand(userMessage, this.conversationHistory);
    
    let response;
    let actions = [];

    switch (intent.type) {
      case 'status':
        const positions = await this.portfolio.getPositions();
        const balances = await this.portfolio.getBalances();
        const stakingYield = await this.portfolio.getOkbStakingYield();
        response = await this.brain.describePortfolio(positions, balances, stakingYield);
        break;

      case 'goal_income':
        const incomePlan = this.brain.suggestIncomeStrategy(intent.params, this.userPreferences);
        response = incomePlan.description;
        if (intent.params?.execute) {
          const result = await this.portfolio.executeStrategy(incomePlan.allocations);
          actions = result.actions;
          response += `\n\n✅ **Executed ${result.actions.length} transactions:**\n` +
            result.actions.map(a => `  • ${a.txHash ? `Tx: ${a.txHash.slice(0,12)}...` : a.description}`).join('\n');
          this.transactionCount += result.actions.length;
        }
        break;

      case 'goal_growth':
        const growthPlan = this.brain.suggestGrowthStrategy(intent.params, this.userPreferences);
        response = growthPlan.description;
        if (intent.params?.execute) {
          const result = await this.portfolio.executeStrategy(growthPlan.allocations);
          actions = result.actions;
          response += `\n\n✅ **Executed ${result.actions.length} transactions**`;
          this.transactionCount += result.actions.length;
        }
        break;

      case 'rebalance':
        const rebalanceResult = await this.portfolio.rebalance(intent.targetAllocations);
        actions = rebalanceResult.actions;
        response = `**Rebalancing to:** ${JSON.stringify(intent.targetAllocations)}\n\n`;
        response += rebalanceResult.actions.length > 0
          ? `✅ Executed ${rebalanceResult.actions.length} swaps`
          : '✅ Already balanced — no swaps needed';
        this.transactionCount += rebalanceResult.actions.length;
        break;

      case 'swap':
        const swapResult = await this.portfolio.swap(intent.params);
        response = `**Swap executed:**\n  ${swapResult.fromAmount} ${swapResult.fromToken} → ${swapResult.toAmount} ${swapResult.toToken}\n  Route: ${swapResult.route}\n  Price impact: ${swapResult.priceImpact}%\n  Gas: ~${swapResult.gasFee} OKB\n  TxHash: \`${swapResult.txHash}\``;
        this.transactionCount++;
        break;

      case 'stake_okb':
        const stakeResult = await this.portfolio.stakeOkb(intent.amount);
        response = stakeResult.description;
        this.transactionCount++;
        break;

      case 'x402_payment':
        const payResult = await this.portfolio.x402Pay(intent.url, intent.amount);
        response = payResult.description;
        this.transactionCount++;
        break;

      case 'learn_preference':
        this.brain.learnFromFeedback(userMessage, intent.preference);
        this.userPreferences = { ...this.userPreferences, ...intent.preference };
        this.savePreferences();
        response = `Got it — I've updated your preferences: ${JSON.stringify(this.userPreferences)}`;
        break;

      case 'question':
        response = await this.brain.answerQuestion(userMessage, 
          await this.portfolio.getPositions(), 
          await this.portfolio.getBalances()
        );
        break;

      default:
        response = "I'm not sure what you mean. Try:\n" +
          "• 'What's my portfolio worth?'\n" +
          "• 'I want stable income'\n" +
          "• 'Swap 10 USDC to OKB'\n" +
          "• 'Stake my OKB for yield'\n" +
          "• 'Rebalance to 60% OKB, 40% USDC'\n" +
          "• 'I prefer low risk'";
    }

    this.conversationHistory.push({ role: 'assistant', content: response, ts: Date.now(), actions });
    
    return { intent, response, actions, txCount: this.transactionCount };
  }

  /**
   * Autonomous mode: periodic portfolio management
   */
  async runAutonomous(intervalMs = 300000) {
    console.log(`[Leigent] Autonomous mode started — checking every ${intervalMs/1000}s`);
    
    setInterval(async () => {
      try {
        const positions = await this.portfolio.getPositions();
        const imbalances = this.portfolio.detectImbalances(positions, this.userPreferences.targetAllocation);
        
        if (imbalances.length > 0) {
          console.log(`[Leigent] ${new Date().toISOString()} — Drift detected:`);
          for (const imb of imbalances) {
            console.log(`  ${imb.asset}: ${imb.current.toFixed(1)}% vs ${imb.target}% target`);
          }
          
          if (imbalances.some(i => Math.abs(i.current - i.target) > 8)) {
            console.log('[Leigent] Drift > 8% — initiating rebalance...');
            const result = await this.portfolio.autoRebalance(positions, imbalances, 0.08);
            this.transactionCount += result.actions.length;
            console.log(`[Leigent] Rebalanced: ${result.actions.length} swaps. Total txs: ${this.transactionCount}`);
          }
        }
      } catch (err) {
        console.error(`[Leigent] Error: ${err.message}`);
      }
    }, intervalMs);
  }
}

module.exports = { LeigentPortfolioAgent };

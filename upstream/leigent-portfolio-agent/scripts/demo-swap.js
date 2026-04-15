/**
 * Demo script — shows a complete swap flow on X Layer
 * Run: node scripts/demo-swap.js
 */

require('dotenv').config();
const { OnchainOSClient } = require('../src/onchainos-client');

const CLIENT = new OnchainOSClient();
const WALLET = process.env.WALLET_ADDRESS || '0xd1b3c96f1854791eb01f84c43b1bf4949264a75d';

// X Layer token addresses
const TOKENS = {
  USDC:  '0x74b7f16337b8972027f6196a17a631ac6de26d22',
  USDT:  '0x779ded0c9e1022225f8e0630b35a9b54be713736',
  WOKB:  '0xe538905cf8410324e03a5a23c1c177a474d59b2b',
  OKB:   '0xeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee',
};

async function demo() {
  console.log('=== Leigent X Layer Swap Demo ===\n');
  console.log(`Wallet: ${WALLET}\n`);

  // Step 1: Check balance
  console.log('1. Checking wallet balance...');
  const balance = await CLIENT.getBalance();
  console.log(`   Total value: $${balance.data?.totalValueUsd || 0}`);
  const assets = balance.data?.details?.[0]?.tokenAssets || [];
  console.log(`   Assets: ${assets.length}`);
  for (const a of assets.slice(0, 5)) {
    console.log(`   - ${a.tokenSymbol}: ${parseFloat(a.balance||0).toFixed(4)} ($${parseFloat(a.valueUsd||0).toFixed(2)})`);
  }
  console.log();

  // Step 2: Get swap quote (USDC → OKB)
  const usdcAmount = '1000000'; // 1 USDC (6 decimals)
  console.log(`2. Getting swap quote: 1 USDC → OKB...`);
  const quote = await CLIENT.getSwapQuote({
    fromAddress: TOKENS.USDC,
    toAddress: TOKENS.OKB,
    amount: usdcAmount,
  });

  if (!quote.ok) {
    console.log(`   ❌ Quote failed: ${quote.error}`);
    return;
  }

  const q = quote.data[0];
  console.log(`   ✅ Route: ${q.fromToken?.tokenSymbol} → ${q.toToken?.tokenSymbol}`);
  console.log(`   DEX: ${q.dexRouterList?.map(r => r.dexProtocol?.dexName).join(' → ')}`);
  console.log(`   Output: ${(q.toTokenAmount / 1e18).toFixed(8)} OKB`);
  console.log(`   Price impact: ${q.priceImpactPercent}%`);
  console.log(`   Gas estimate: ${q.estimateGasFee} (${(parseFloat(q.estimateGasFee || 0) / 1e18).toFixed(6)} OKB)`);
  console.log();

  // Step 3: Execute swap (if wallet has funds)
  console.log('3. Ready to execute swap...');
  console.log('   (Run with WALLET_ADDRESS=... node scripts/demo-swap.js to execute)');
  console.log();
  console.log('=== Demo Complete ===');
}

demo().catch(console.error);

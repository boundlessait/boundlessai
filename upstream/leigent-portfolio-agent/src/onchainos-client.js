/**
 * OnchainOS Client — wraps the `onchainos` CLI for portfolio operations
 */

const { execSync, spawn } = require('child_process');
const path = require('path');
const fs = require('fs');

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

function runOnchainOS(args, envOverrides = {}) {
  const env = { ...process.env, ...loadEnv(), ...envOverrides };
  const binPath = process.platform === 'darwin' 
    ? `${process.env.HOME}/.local/bin/onchainos`
    : 'onchainos';
  
  try {
    const output = execSync(`${binPath} ${args}`, { env, timeout: 30000 });
    return JSON.parse(output.toString());
  } catch (err) {
    // Try parsing as non-JSON output
    if (err.stdout) return { ok: true, data: err.stdout.toString() };
    return { ok: false, error: err.message };
  }
}

class OnchainOSClient {
  constructor() {
    this.chain = 196; // X Layer
    this.walletAddress = null;
  }

  setWallet(address) {
    this.walletAddress = address;
  }

  // ── Wallet ────────────────────────────────────────────────────────────────

  async getWalletAddresses() {
    return runOnchainOS('wallet addresses');
  }

  async getBalance(chain = this.chain) {
    return runOnchainOS(`wallet balance --chain ${chain}`);
  }

  // ── Token ────────────────────────────────────────────────────────────────

  async searchToken(query, chain = this.chain) {
    return runOnchainOS(`token search --query ${query} --chains ${chain}`);
  }

  // ── DEX Swap ─────────────────────────────────────────────────────────────

  async getSwapQuote({ fromAddress, toAddress, amount, chain = this.chain }) {
    return runOnchainOS(
      `swap quote --from ${fromAddress} --to ${toAddress} --amount ${amount} --chain ${chain}`
    );
  }

  async executeSwap({ fromAddress, toAddress, amount, chain = this.chain, slippage = 0.5 }) {
    return runOnchainOS(
      `swap execute --from ${fromAddress} --to ${toAddress} --amount ${amount} --chain ${chain} --wallet default --slippage ${slippage}`
    );
  }

  async getSwapCalldata({ fromAddress, toAddress, amount, chain = this.chain }) {
    return runOnchainOS(
      `swap swap --from ${fromAddress} --to ${toAddress} --amount ${amount} --chain ${chain}`
    );
  }

  // ── Portfolio / DeFi ─────────────────────────────────────────────────────

  async getDeFiPositions(address, chains = [this.chain]) {
    return runOnchainOS(`defi positions --address ${address} --chains ${chains.join(',')}`);
  }

  async getDeFiPositionDetail(address, chain, platformId) {
    return runOnchainOS(
      `defi position-detail --address ${address} --chain ${chain} --platform-id ${platformId}`
    );
  }

  // ── Gateway ──────────────────────────────────────────────────────────────

  async simulateTransaction({ from, to, data, value, chain = this.chain }) {
    return runOnchainOS(
      `gateway simulate --chain ${chain} --from ${from} --to ${to} --data "${data}" --value ${value}`
    );
  }

  async broadcastTransaction({ rawTx, chain = this.chain }) {
    return runOnchainOS(`gateway broadcast --chain ${chain} --tx ${rawTx}`);
  }

  // ── Security ─────────────────────────────────────────────────────────────

  async scanToken(address, chain = this.chain) {
    return runOnchainOS(`security token-scan --address ${address} --chain ${chain}`);
  }

  async scanContract(address, chain = this.chain) {
    return runOnchainOS(`security contract-scan --address ${address} --chain ${chain}`);
  }

  // ── Token Lists ──────────────────────────────────────────────────────────

  async getSupportedSwapChains() {
    return runOnchainOS('swap chains');
  }
}

module.exports = { OnchainOSClient };

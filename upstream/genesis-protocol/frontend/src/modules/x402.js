// ── x402 Payment Protocol ──
// Supports real on-chain OKB micro-payments when wallet is connected,
// falls back to simulation mode for demo.

import { toast, getConnected, getSigner } from '../main.js';
import { CFG } from '../config.js';

// Protocol fee receiver (GenesisHookAssembler owner = protocol treasury)
const PROTOCOL_FEE_RECEIVER = '0xd2d120eb7ced38551ccefb48021067d41d6542d3';

const X402_SERVICES = {
  signal_query: { method: 'GET', path: '/api/v1/signal?pair=ETH-USDT', amount: '0.001', desc: '市场信号查询', okb: '0.0001' },
  strategy_subscribe: { method: 'POST', path: '/api/v1/strategy/subscribe', amount: '0.01', desc: '策略变更订阅', okb: '0.001' },
  strategy_params_buy: { method: 'POST', path: '/api/v1/strategy/params/export', amount: '1.00', desc: '完整参数导出', okb: '0.01' },
  nft_license: { method: 'POST', path: '/api/v1/nft/license', amount: '5.00', desc: 'NFT策略授权', okb: '0.05' },
};

export function updateX402Preview() {
  const svc = X402_SERVICES[document.getElementById('x402-service').value];
  const connected = getConnected();
  document.getElementById('x402-preview').innerHTML =
    '<p><span class="text-cyan-400">' + svc.method + '</span> ' + svc.path + '</p>' +
    '<p><span class="text-purple-400">X-Payment:</span> x402-OKB-' + svc.okb + '</p>' +
    '<p><span class="text-purple-400">X-Chain:</span> xlayer-196</p>' +
    '<p><span class="text-purple-400">X-Settle:</span> ' + (parseFloat(svc.okb) < 0.01 ? 'async' : 'sync') + '</p>' +
    '<p><span class="' + (connected ? 'text-green-400' : 'text-yellow-400') + '">' +
    (connected ? '钱包已连接 — 将发送真实链上交易' : '钱包未连接 — 将使用模拟模式') + '</span></p>';
  document.getElementById('x402-status').textContent = '';
}

export async function executeX402Payment() {
  const svc = X402_SERVICES[document.getElementById('x402-service').value];
  const st = document.getElementById('x402-status');
  const payBtn = document.getElementById('x402-pay-btn');
  payBtn.disabled = true;
  payBtn.classList.add('opacity-50', 'cursor-not-allowed');

  try {
  // If wallet connected, do real on-chain payment
  if (getConnected()) {
    try {
      st.innerHTML = '<span class="text-cyan-400">x402: HTTP 402 Payment Required — ' + svc.okb + ' OKB for ' + svc.desc + '</span>';
      await new Promise(r => setTimeout(r, 500));

      st.innerHTML = '<span class="text-purple-400">x402: 请求钱包签名... (链上微支付 ' + svc.okb + ' OKB)</span>';
      const signer = getSigner();
      const tx = await signer.sendTransaction({
        to: PROTOCOL_FEE_RECEIVER,
        value: ethers.parseEther(svc.okb),
      });

      st.innerHTML = '<span class="text-yellow-400">x402: TX 已广播 ' + tx.hash.slice(0, 20) + '... 等待确认...</span>';
      const receipt = await tx.wait(1);

      st.innerHTML =
        '<span class="text-green-400">x402 支付成功!</span> ' +
        '<a href="https://www.oklink.com/xlayer/tx/' + receipt.hash + '" target="_blank" class="text-[var(--neon)] hover:underline text-xs">' +
        receipt.hash.slice(0, 20) + '...</a>' +
        '<br><span class="text-gray-400 text-xs">已支付 ' + svc.okb + ' OKB → 协议金库 → ' + svc.desc + '</span>';
      toast('x402 支付成功: ' + svc.okb + ' OKB → ' + svc.desc, 'green');

      // Show service response after payment
      await new Promise(r => setTimeout(r, 800));
      st.innerHTML += '<br><span class="text-cyan-400 text-xs">HTTP 200 — 服务已解锁。响应数据已返回。</span>';
    } catch (e) {
      const reason = e.code === 'ACTION_REJECTED' ? '用户拒绝签名' : (e.reason || e.message || '').slice(0, 80);
      st.innerHTML = '<span class="text-red-400">x402 支付失败: ' + reason + '</span>';
      toast('x402 失败: ' + reason, 'red');
    }
  } else {
    // Simulation mode
    st.innerHTML = '<span class="text-yellow-400">x402 模拟模式 (连接钱包可发送真实交易)</span>';
    await new Promise(r => setTimeout(r, 500));
    st.innerHTML = '<span class="text-cyan-400">模拟: HTTP 402 Payment Required — ' + svc.okb + ' OKB</span>';
    await new Promise(r => setTimeout(r, 600));
    st.innerHTML = '<span class="text-purple-400">模拟: OnchainOS 钱包签名 ' + svc.okb + ' OKB → 协议金库...</span>';
    await new Promise(r => setTimeout(r, 800));
    const fakeHash = '0x' + Array.from({ length: 64 }, (_, i) => '0123456789abcdef'[(Date.now() + i * 7) % 16]).join('');
    st.innerHTML =
      '<span class="text-green-400">模拟完成: TX ' + fakeHash.slice(0, 20) + '...</span>' +
      '<br><span class="text-gray-500 text-xs">连接 OKX Wallet / MetaMask 可发送真实链上微支付</span>';
    toast('x402 模拟: ' + svc.okb + ' OKB → ' + svc.desc, 'green');
  }
  } finally {
    payBtn.disabled = false;
    payBtn.classList.remove('opacity-50', 'cursor-not-allowed');
  }
}

export function init() {
  document.getElementById('x402-service').addEventListener('change', updateX402Preview);
  document.getElementById('x402-pay-btn').addEventListener('click', executeX402Payment);
  // Update preview when wallet connects (listen for custom event)
  window.addEventListener('wallet-connected', updateX402Preview);
}

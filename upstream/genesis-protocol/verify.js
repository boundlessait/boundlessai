const { chromium } = require('playwright');
(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1400, height: 5000 } });
  const errors = [];
  page.on('console', msg => { if (msg.type() === 'error') errors.push(msg.text()); });
  
  await page.goto('https://jnq7rage.mule.page/', { waitUntil: 'networkidle', timeout: 60000 });
  await page.waitForTimeout(12000);

  console.log('=== P0-1: 仪表盘全部显示 "--" ===');
  const stats = await page.evaluate(() => ({
    strategies: document.getElementById('stat-strategies').textContent,
    decisions: document.getElementById('stat-decisions').textContent,
    swaps: document.getElementById('stat-swaps').textContent,
    nfts: document.getElementById('stat-nfts').textContent,
    volume: document.getElementById('stat-volume').textContent,
  }));
  const hasDash = Object.values(stats).some(v => v === '--' || !v);
  console.log('  数据:', JSON.stringify(stats));
  console.log('  ' + (hasDash ? 'FAIL' : 'PASS'));

  console.log('\n=== P0-2: 交易列表/时间线/策略表全空 ===');
  const checks = await page.evaluate(() => {
    const tx = document.getElementById('recent-tx-list');
    const strat = document.getElementById('strategies-table');
    const tl = document.getElementById('activity-timeline-list');
    return {
      txCount: tx ? tx.children.length : 0,
      txEmpty: (tx && tx.textContent.includes('未找到')),
      stratCount: strat ? strat.children.length : 0,
      stratEmpty: (strat && strat.textContent.includes('暂无')),
      tlCount: tl ? tl.children.length : 0,
      tlEmpty: (tl && tl.textContent.includes('暂无')),
    };
  });
  console.log('  交易列表: ' + checks.txCount + ' 条 ' + (checks.txEmpty ? 'FAIL' : 'PASS'));
  console.log('  策略表: ' + checks.stratCount + ' 行 ' + (checks.stratEmpty ? 'FAIL' : 'PASS'));
  console.log('  活动时间线: ' + checks.tlCount + ' 条 ' + (checks.tlEmpty ? 'FAIL' : 'PASS'));

  console.log('\n=== P0-3: NFT 画廊为空 ===');
  const nft = await page.evaluate(() => {
    const el = document.getElementById('nft-gallery');
    return { count: el ? el.children.length : 0, empty: el && el.textContent.includes('暂无') };
  });
  console.log('  NFT 卡片: ' + nft.count + ' 个 ' + (nft.empty || nft.count === 0 ? 'FAIL' : 'PASS'));

  console.log('\n=== P0-4: Backtest 数据硬编码 ===');
  const bt = await page.evaluate(() => {
    const chart = document.getElementById('chart-backtest');
    const inst = chart ? echarts.getInstanceByDom(chart) : null;
    if (!inst) return null;
    const opt = inst.getOption();
    return opt.series[0].data;
  });
  const oldValues = [18.3, 24.7, 31.2, 21.5];
  const isOld = bt && JSON.stringify(bt) === JSON.stringify(oldValues);
  console.log('  当前值: ' + JSON.stringify(bt));
  console.log('  ' + (isOld ? 'FAIL - 仍是旧硬编码' : 'PASS - 动态计算'));

  console.log('\n=== P0-5: Agent 状态静态快照 ===');
  const agent = await page.evaluate(() => ({
    cycles: document.getElementById('agent-cycles').textContent,
    accuracy: document.getElementById('agent-accuracy').textContent,
  }));
  const oldAgent = agent.cycles === '3' && agent.accuracy === '50.0%';
  console.log('  循环: ' + agent.cycles + ', 准确率: ' + agent.accuracy);
  console.log('  ' + (oldAgent ? 'FAIL - 仍是旧值' : 'PASS'));

  console.log('\n=== P0-6: localhost:8402 每 10 秒报错 ===');
  const has8402 = errors.some(e => e.includes('8402') || e.includes('CONNECTION_REFUSED'));
  console.log('  Console 错误总数: ' + errors.length);
  console.log('  含 8402 错误: ' + has8402);
  console.log('  ' + (errors.length === 0 ? 'PASS - 零错误' : has8402 ? 'FAIL' : 'WARN - 有其他错误(' + errors.length + ')'));
  if (errors.length > 0) errors.slice(0, 3).forEach(e => console.log('    > ' + e.substring(0, 120)));

  console.log('\n=== P1: 跨协议集成状态 ===');
  const protos = await page.evaluate(() => ({
    uniswap: document.getElementById('proto-uniswap-status').textContent,
    okx: document.getElementById('proto-okx-status').textContent,
    onchain: document.getElementById('proto-onchain-status').textContent,
    x402: document.getElementById('proto-x402-status').textContent,
  }));
  console.log('  ' + JSON.stringify(protos));
  console.log('  ' + (protos.x402.includes('Error') ? 'FAIL' : 'PASS'));

  console.log('\n=== P1: 决策日志 ===');
  const jnl = await page.evaluate(() => {
    const el = document.getElementById('journal-timeline');
    return { count: el ? el.children.length : 0, empty: el && el.textContent.includes('暂无') };
  });
  console.log('  决策条目: ' + jnl.count + ' 条 ' + (jnl.empty || jnl.count === 0 ? 'FAIL' : 'PASS'));

  console.log('\n========================================');
  console.log('逐项验证完毕');
  
  await browser.close();
})();

/**
 * Genesis Protocol — Production Server
 * Serves static frontend + proxies OKX API + LLM reasoning endpoint.
 */
import http from 'node:http';
import https from 'node:https';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const DIST = path.join(__dirname, 'dist');
const PORT = process.env.PORT || 3000;
const DEEPSEEK_API_KEY = process.env.DEEPSEEK_API_KEY || 'sk-76afd04c39dc4e50a8fdf78cc65f754e';

const SYSTEM_PROMPT = `You are Genesis Protocol's 5-layer cognitive engine (Perception→Analysis→Planning→Evolution→Meta-cognition) for autonomous DeFi on X Layer/OKX (Chain 196). You run DynamicFee sigmoid pricing, MEV sandwich detection, and AutoRebalance tick boundaries on Uniswap V4 Hooks. Respond in English, 3-4 sentences max: state risk assessment with numbers from the data, recommend a specific action, and give confidence reasoning. Only execute above the 0.7 confidence gate.`;

const MIME = {
  '.html': 'text/html',
  '.js':   'application/javascript',
  '.css':  'text/css',
  '.json': 'application/json',
  '.png':  'image/png',
  '.svg':  'image/svg+xml',
  '.ico':  'image/x-icon',
};

/** Proxy a request to an external HTTPS host. */
function proxyTo(targetHost, pathRewrite, req, res) {
  const url = new URL(req.url, `http://localhost`);
  const targetPath = url.pathname.replace(pathRewrite.from, pathRewrite.to) + url.search;
  const opts = {
    hostname: targetHost,
    port: 443,
    path: targetPath,
    method: req.method,
    headers: {
      'User-Agent': 'genesis-protocol/1.0',
      'Accept': 'application/json',
    },
    timeout: 15000,
  };
  const proxyReq = https.request(opts, (proxyRes) => {
    res.writeHead(proxyRes.statusCode, {
      'Content-Type': proxyRes.headers['content-type'] || 'application/json',
      'Access-Control-Allow-Origin': '*',
      'Cache-Control': 'public, max-age=5',
    });
    proxyRes.pipe(res);
  });
  proxyReq.on('error', (e) => {
    res.writeHead(502, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ error: 'proxy_error', detail: e.message }));
  });
  proxyReq.end();
}

/** Call DeepSeek LLM for AI reasoning. */
function handleLLM(req, res) {
  let body = '';
  req.on('data', chunk => { body += chunk; });
  req.on('end', () => {
    if (!DEEPSEEK_API_KEY) {
      res.writeHead(200, { 'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*' });
      return res.end(JSON.stringify({ error: 'no_api_key', text: '' }));
    }
    let parsed;
    try { parsed = JSON.parse(body); } catch { parsed = {}; }
    const userMsg = parsed.prompt || 'Analyze the current market conditions.';
    const payload = JSON.stringify({
      model: 'deepseek-chat',
      messages: [
        { role: 'system', content: SYSTEM_PROMPT },
        { role: 'user', content: userMsg },
      ],
      max_tokens: 300,
      temperature: 0.7,
    });
    const opts = {
      hostname: 'api.deepseek.com',
      port: 443,
      path: '/v1/chat/completions',
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${DEEPSEEK_API_KEY}`,
        'Content-Length': Buffer.byteLength(payload),
      },
      timeout: 20000,
    };
    const llmReq = https.request(opts, (llmRes) => {
      let data = '';
      llmRes.on('data', chunk => { data += chunk; });
      llmRes.on('end', () => {
        try {
          const j = JSON.parse(data);
          const text = j.choices?.[0]?.message?.content || '';
          res.writeHead(200, { 'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*' });
          res.end(JSON.stringify({ text, model: j.model || 'deepseek-chat' }));
        } catch {
          res.writeHead(200, { 'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*' });
          res.end(JSON.stringify({ error: 'parse_error', text: '' }));
        }
      });
    });
    llmReq.on('error', (e) => {
      res.writeHead(200, { 'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*' });
      res.end(JSON.stringify({ error: e.message, text: '' }));
    });
    llmReq.write(payload);
    llmReq.end();
  });
}

const server = http.createServer((req, res) => {
  const url = new URL(req.url, `http://localhost`);

  // CORS preflight
  if (req.method === 'OPTIONS') {
    res.writeHead(204, {
      'Access-Control-Allow-Origin': '*',
      'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
      'Access-Control-Allow-Headers': 'Content-Type',
    });
    return res.end();
  }

  // LLM reasoning endpoint
  if (url.pathname === '/api/llm' && req.method === 'POST') {
    return handleLLM(req, res);
  }

  // API proxies
  if (url.pathname.startsWith('/okx-api/')) {
    return proxyTo('www.okx.com', { from: /^\/okx-api/, to: '' }, req, res);
  }
  if (url.pathname.startsWith('/okx-web3/')) {
    return proxyTo('web3.okx.com', { from: /^\/okx-web3/, to: '' }, req, res);
  }
  if (url.pathname.startsWith('/cg-api/')) {
    return proxyTo('api.coingecko.com', { from: /^\/cg-api/, to: '' }, req, res);
  }

  // RPC proxy to X Layer
  if (url.pathname === '/rpc' && req.method === 'POST') {
    let body = '';
    req.on('data', chunk => { body += chunk; });
    req.on('end', () => {
      const payload = Buffer.from(body);
      const opts = {
        hostname: 'rpc.xlayer.tech',
        port: 443,
        path: '/',
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Content-Length': payload.length,
        },
        timeout: 15000,
      };
      const proxyReq = https.request(opts, (proxyRes) => {
        res.writeHead(proxyRes.statusCode, {
          'Content-Type': proxyRes.headers['content-type'] || 'application/json',
          'Access-Control-Allow-Origin': '*',
        });
        proxyRes.pipe(res);
      });
      proxyReq.on('error', (e) => {
        res.writeHead(502, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ error: 'rpc_proxy_error', detail: e.message }));
      });
      proxyReq.write(payload);
      proxyReq.end();
    });
    return;
  }

  // Static files
  let filePath = path.join(DIST, url.pathname === '/' ? 'index.html' : url.pathname);
  if (!fs.existsSync(filePath)) filePath = path.join(DIST, 'index.html'); // SPA fallback

  const ext = path.extname(filePath);
  const contentType = MIME[ext] || 'application/octet-stream';

  try {
    const data = fs.readFileSync(filePath);
    res.writeHead(200, {
      'Content-Type': contentType,
      'Cache-Control': ext === '.html' ? 'no-cache' : 'public, max-age=86400',
    });
    res.end(data);
  } catch {
    res.writeHead(404, { 'Content-Type': 'text/plain' });
    res.end('Not Found');
  }
});

server.listen(PORT, '0.0.0.0', () => {
  console.log(`Genesis Protocol running on http://localhost:${PORT}`);
});

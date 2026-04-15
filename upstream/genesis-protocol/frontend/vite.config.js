import { defineConfig } from 'vite';

export default defineConfig({
  root: '.',
  build: {
    outDir: 'dist',
    emptyOutDir: true,
  },
  server: {
    port: 3000,
    open: true,
    proxy: {
      // Proxy OKX Market API (www.okx.com)
      '/okx-api': {
        target: 'https://www.okx.com',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/okx-api/, ''),
        headers: {
          'User-Agent': 'genesis-protocol/1.0',
        },
      },
      // Proxy OKX Web3 API (web3.okx.com)
      '/okx-web3': {
        target: 'https://web3.okx.com',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/okx-web3/, ''),
        headers: {
          'User-Agent': 'genesis-protocol/1.0',
        },
      },
      // Proxy CoinGecko API (fallback)
      '/cg-api': {
        target: 'https://api.coingecko.com',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/cg-api/, ''),
      },
    },
  },
});

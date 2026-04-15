/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Suppress browser extension errors from the dev overlay
  onDemandEntries: { maxInactiveAge: 60 * 1000 },
  webpack: (config) => {
    // No changes needed, just extend if required
    return config;
  },
};

// Suppress MetaMask/extension errors from Next.js dev error overlay
if (process.env.NODE_ENV === 'development') {
  const originalConsoleError = console.error;
  const SUPPRESS = ['MetaMask', 'chrome-extension', 'Failed to connect', 'inpage.js'];
  console.error = (...args) => {
    const msg = args.join(' ');
    if (SUPPRESS.some(p => msg.includes(p))) return;
    originalConsoleError(...args);
  };
}

module.exports = nextConfig;

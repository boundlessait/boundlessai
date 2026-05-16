import { defineChain } from 'viem';

export const KITE_TESTNET_CHAIN_ID = 2368;
export const KITE_MAINNET_CHAIN_ID = 2366;
export const KITE_TESTNET_RPC_URL = 'https://rpc-testnet.gokite.ai';
export const KITE_MAINNET_RPC_URL = 'https://rpc.gokite.ai';
export const KITE_TESTNET_EXPLORER_BASE_URL = 'https://testnet.kitescan.ai';
export const KITE_MAINNET_EXPLORER_BASE_URL = 'https://kitescan.ai';
export const KITE_TESTNET_USDT_ADDRESS = '0x0fF5393387ad2f9f691FD6Fd28e07E3969e27e63';

export const kiteTestnetChain = defineChain({
  id: KITE_TESTNET_CHAIN_ID,
  name: 'KiteAI Testnet',
  nativeCurrency: {
    name: 'KITE',
    symbol: 'KITE',
    decimals: 18,
  },
  rpcUrls: {
    default: {
      http: [KITE_TESTNET_RPC_URL],
    },
  },
  blockExplorers: {
    default: {
      name: 'KiteScan Testnet',
      url: KITE_TESTNET_EXPLORER_BASE_URL,
    },
  },
  testnet: true,
});

export const kiteMainnetChain = defineChain({
  id: KITE_MAINNET_CHAIN_ID,
  name: 'KiteAI Mainnet',
  nativeCurrency: {
    name: 'KITE',
    symbol: 'KITE',
    decimals: 18,
  },
  rpcUrls: {
    default: {
      http: [KITE_MAINNET_RPC_URL],
    },
  },
  blockExplorers: {
    default: {
      name: 'KiteScan',
      url: KITE_MAINNET_EXPLORER_BASE_URL,
    },
  },
});

export function kiteChainById(chainId: number) {
  if (chainId === KITE_MAINNET_CHAIN_ID) {
    return kiteMainnetChain;
  }
  return kiteTestnetChain;
}

export function networkLabelFromChainId(chainId: number): 'kite-mainnet' | 'kite-testnet' | 'kite-custom' {
  if (chainId === KITE_MAINNET_CHAIN_ID) return 'kite-mainnet';
  if (chainId === KITE_TESTNET_CHAIN_ID) return 'kite-testnet';
  return 'kite-custom';
}

export function humanNetworkLabel(value?: string | null): string {
  if (!value) return 'Onchain';
  if (value === 'kite-mainnet') return 'Kite Mainnet';
  if (value === 'kite-testnet') return 'Kite Testnet';
  return 'Onchain';
}

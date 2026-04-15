'use client';

import { useEffect, useState } from 'react';

const CONNECTED_WALLET_STORAGE_KEY = 'trust-leases.connected-wallet';

type EthereumProvider = {
  request: (args: { method: string; params?: unknown[] }) => Promise<unknown>;
  on?: (event: string, handler: (...args: unknown[]) => void) => void;
  removeListener?: (event: string, handler: (...args: unknown[]) => void) => void;
};

declare global {
  interface Window {
    ethereum?: EthereumProvider;
  }
}

function shortAddress(address?: string | null): string {
  if (!address || address.length < 10) {
    return 'Wallet Connected';
  }
  return `${address.slice(0, 6)}...${address.slice(-4)}`;
}

function emitWalletUpdate(address: string): void {
  window.dispatchEvent(
    new CustomEvent('trust-leases-wallet-updated', {
      detail: { address },
    }),
  );
}

export function TopWalletConnect() {
  const [walletAddress, setWalletAddress] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    const cached = localStorage.getItem(CONNECTED_WALLET_STORAGE_KEY);
    if (cached) {
      setWalletAddress(cached);
    }

    const onWalletUpdate = (event: Event) => {
      const detail = (event as CustomEvent<{ address?: string }>).detail;
      if (!detail?.address) {
        return;
      }
      setWalletAddress(detail.address);
      localStorage.setItem(CONNECTED_WALLET_STORAGE_KEY, detail.address);
    };

    window.addEventListener('trust-leases-wallet-updated', onWalletUpdate);
    return () => {
      window.removeEventListener('trust-leases-wallet-updated', onWalletUpdate);
    };
  }, []);

  async function connectWallet() {
    setError(null);
    setMessage(null);
    setBusy(true);
    try {
      if (!window.ethereum) {
        throw new Error('No browser wallet found.');
      }

      const accounts = await window.ethereum.request({ method: 'eth_requestAccounts' }) as string[];
      const account = accounts[0];
      if (!account) {
        throw new Error('Wallet did not return an account.');
      }

      try {
        await window.ethereum.request({
          method: 'wallet_switchEthereumChain',
          params: [{ chainId: '0xc4' }],
        });
      } catch {
        await window.ethereum.request({
          method: 'wallet_addEthereumChain',
          params: [{
            chainId: '0xc4',
            chainName: 'X Layer',
            nativeCurrency: { name: 'OKB', symbol: 'OKB', decimals: 18 },
            rpcUrls: ['https://xlayer.drpc.org'],
            blockExplorerUrls: ['https://www.oklink.com/xlayer'],
          }],
        });
      }

      setWalletAddress(account);
      localStorage.setItem(CONNECTED_WALLET_STORAGE_KEY, account);
      emitWalletUpdate(account);
      setMessage(`Connected ${shortAddress(account)} on X Layer`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Wallet connection failed.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="nav-wallet-wrap">
      <div className="nav-wallet-stack">
        <button
          type="button"
          className="nav-wallet-btn"
          onClick={connectWallet}
          disabled={busy}
          title={error ?? (walletAddress ? `Connected: ${walletAddress}` : 'Connect wallet on X Layer')}
        >
          {busy ? 'Connecting...' : walletAddress ? shortAddress(walletAddress) : 'Connect Wallet'}
        </button>
        {busy ? <div className="nav-wallet-status pending">Waiting for wallet signature…</div> : null}
        {!busy && error ? <div className="nav-wallet-status error">{error}</div> : null}
        {!busy && !error && message ? <div className="nav-wallet-status success">{message}</div> : null}
      </div>
    </div>
  );
}

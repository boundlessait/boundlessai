import 'dotenv/config';
import { HardhatUserConfig } from 'hardhat/config';
import '@nomicfoundation/hardhat-toolbox';

const privateKey = process.env.LEASE_CONTROLLER_WRITER_PRIVATE_KEY
  || process.env.KITE_PRIVATE_KEY
  || process.env.KITE_SETTLEMENT_PRIVATE_KEY
  || process.env.XLAYER_PRIVATE_KEY
  || process.env.XLAYER_SETTLEMENT_PRIVATE_KEY
  || process.env.PRIVATE_KEY;

const accounts = privateKey ? [privateKey] : [];

const config: HardhatUserConfig = {
  solidity: {
    version: '0.8.24',
    settings: {
      optimizer: {
        enabled: true,
        runs: 200,
      },
      viaIR: true,
    },
  },
  networks: {
    kiteTestnet: {
      url: process.env.KITE_RPC_URL || process.env.XLAYER_RPC_URL || 'https://rpc-testnet.gokite.ai',
      chainId: 2368,
      accounts,
    },
    kite: {
      url: process.env.KITE_MAINNET_RPC_URL || 'https://rpc.gokite.ai',
      chainId: 2366,
      accounts,
    },
  },
};

export default config;

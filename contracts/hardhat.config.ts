import 'dotenv/config';
import { HardhatUserConfig } from 'hardhat/config';
import '@nomicfoundation/hardhat-toolbox';

const privateKey = process.env.LEASE_CONTROLLER_WRITER_PRIVATE_KEY
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
    xlayerTestnet: {
      url: process.env.XLAYER_TESTNET_RPC_URL || 'https://testrpc.xlayer.tech',
      chainId: 195,
      accounts,
    },
    xlayer: {
      url: process.env.XLAYER_RPC_URL || 'https://xlayer-rpc.com',
      chainId: 196,
      accounts,
    },
  },
};

export default config;

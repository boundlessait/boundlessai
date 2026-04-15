import { ethers } from 'hardhat';

function requireEnv(name: string): string {
  const value = process.env[name];
  if (!value || value.trim().length === 0) {
    throw new Error(`Missing ${name}`);
  }
  return value.trim();
}

async function main(): Promise<void> {
  const [deployer] = await ethers.getSigners();

  const controllerFactory = await ethers.getContractFactory('TrustLeaseController');
  const controller = await controllerFactory.deploy(deployer.address);
  await controller.waitForDeployment();

  const consumerName = process.env.LEASE_CONSUMER_NAME || 'strategy-office';
  const operatorName = process.env.LEASE_OPERATOR_NAME || 'human-principal';
  const vaultOwner = requireEnv('BOUNDLESS_VAULT_OWNER');

  const vaultFactory = await ethers.getContractFactory('BoundlessVault');
  const vault = await vaultFactory.deploy(
    await controller.getAddress(),
    vaultOwner,
    consumerName,
    operatorName,
  );
  await vault.waitForDeployment();

  await (await controller.setExecutor(await vault.getAddress(), true)).wait();

  const network = await ethers.provider.getNetwork();
  console.log(`deployer=${deployer.address}`);
  console.log(`network=${network.name}`);
  console.log(`controller=${await controller.getAddress()}`);
  console.log(`vault=${await vault.getAddress()}`);
  console.log(`vaultOwner=${vaultOwner}`);
  console.log(`consumerName=${consumerName}`);
  console.log(`operatorName=${operatorName}`);
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});

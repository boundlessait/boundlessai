import { ethers } from 'hardhat';

async function main(): Promise<void> {
  const [deployer] = await ethers.getSigners();
  const factory = await ethers.getContractFactory('TrustLeaseController');
  const controller = await factory.deploy(deployer.address);
  await controller.waitForDeployment();

  const address = await controller.getAddress();
  console.log(`deployer=${deployer.address}`);
  console.log(`controller=${address}`);
  console.log(`network=${(await ethers.provider.getNetwork()).name}`);
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});

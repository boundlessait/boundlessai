import { MemberTestPage } from '@/components/member-test-page';
import { getSiteData } from '@/lib/site-data';

export const dynamic = 'force-dynamic';

export default async function MemberTestRoutePage() {
  const siteData = await getSiteData();
  return (
    <MemberTestPage
      vaultAddress={process.env.BOUNDLESS_VAULT_ADDRESS ?? null}
      defaultLeaseId={siteData.lease?.leaseId ?? null}
      controllerAddress={process.env.LEASE_CONTROLLER_ADDRESS ?? null}
      consumerName={process.env.LEASE_CONSUMER_NAME ?? 'strategy-office'}
      rpcUrl={process.env.XLAYER_RPC_URL || 'https://xlayer.drpc.org'}
    />
  );
}

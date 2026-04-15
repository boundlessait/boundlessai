import { ProofPage } from '@/components/proof-page';
import { getSiteData } from '@/lib/site-data';

export const dynamic = 'force-dynamic';

type ProofRoutePageProps = {
  searchParams?: Promise<Record<string, string | string[] | undefined>>;
};

export default async function ProofRoutePage({ searchParams }: ProofRoutePageProps) {
  const resolvedSearchParams = await searchParams;
  const requestIdValue = resolvedSearchParams?.requestId;
  const requestId = Array.isArray(requestIdValue) ? requestIdValue[0] : requestIdValue;
  const siteData = await getSiteData({ requestId });
  return <ProofPage {...siteData} />;
}

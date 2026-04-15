import { SubmissionPage } from '@/components/submission-page';
import { getSiteData } from '@/lib/site-data';

export const dynamic = 'force-dynamic';

export default async function SubmissionRoutePage() {
  const siteData = await getSiteData();
  return <SubmissionPage {...siteData} />;
}

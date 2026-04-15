import LandingPage from '@/components/landing-page';
import { getSiteData } from '@/lib/site-data';

export const dynamic = 'force-dynamic';

export default async function HomePage() {
  const siteData = await getSiteData();
  return <LandingPage {...siteData} />;
}

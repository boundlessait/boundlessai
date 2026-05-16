import type { Metadata } from 'next';
import { Inter, JetBrains_Mono } from 'next/font/google';
import './globals.css';

const metadataBase = (() => {
  const explicit = process.env.NEXT_PUBLIC_APP_URL;
  if (explicit) {
    return new URL(explicit);
  }

  const vercelUrl = process.env.VERCEL_URL;
  if (vercelUrl) {
    return new URL(`https://${vercelUrl}`);
  }

  return new URL('http://localhost:3000');
})();

const inter = Inter({
  subsets: ['latin'],
  weight: ['400', '500', '600', '700', '800'],
  variable: '--font-sans'
});

const jetbrainsMono = JetBrains_Mono({
  subsets: ['latin'],
  weight: ['400', '500'],
  variable: '--font-mono'
});

export const metadata: Metadata = {
  metadataBase,
  title: 'Boundless — Governed Agent Finance',
  description: 'Boundless is the governance layer for Kite Passport-powered agent payments.',
  icons: {
    icon: '/icon.svg',
    apple: '/apple-icon.svg',
    shortcut: '/icon.svg',
  },
  openGraph: {
    title: 'Boundless — Governed Agent Finance',
    description: 'Boundless is the governance layer for Kite Passport-powered agent payments.',
    images: ['/boundless-mark.svg'],
  },
  twitter: {
    card: 'summary_large_image',
    title: 'Boundless — Governed Agent Finance',
    description: 'Boundless is the governance layer for Kite Passport-powered agent payments.',
    images: ['/boundless-mark.svg'],
  },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang='en'>
      <body className={`${inter.variable} ${jetbrainsMono.variable}`}>
        {children}
      </body>
    </html>
  );
}

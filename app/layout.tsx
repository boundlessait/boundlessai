import type { Metadata } from 'next';
import { Inter, JetBrains_Mono } from 'next/font/google';
import './globals.css';

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
  title: 'Boundless — Agent Execution Guard',
  description: 'Boundless — Let agents run, within your rules, budget, and verifiable proof.',
  icons: {
    icon: '/icon.svg',
    apple: '/apple-icon.svg',
    shortcut: '/icon.svg',
  },
  openGraph: {
    title: 'Boundless — Agent Execution Guard',
    description: 'Boundless — Let agents run, within your rules, budget, and verifiable proof.',
    images: ['/boundless-mark.svg'],
  },
  twitter: {
    card: 'summary_large_image',
    title: 'Boundless — Agent Execution Guard',
    description: 'Boundless — Let agents run, within your rules, budget, and verifiable proof.',
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

import type { Metadata } from 'next';

import { BRAND_DESCRIPTION, BRAND_DOMAIN, BRAND_NAME, BRAND_TAGLINE } from '@/lib/brand';
import { Providers } from '@/components/providers';

import './globals.css';

export const metadata: Metadata = {
  metadataBase: new URL(`https://${BRAND_DOMAIN}`),
  title: BRAND_NAME,
  description: BRAND_DESCRIPTION,
  openGraph: {
    title: BRAND_NAME,
    description: BRAND_TAGLINE,
    url: `https://${BRAND_DOMAIN}`,
    siteName: BRAND_NAME,
    locale: 'pt_BR',
    type: 'website',
  },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="pt-BR">
      <body>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}

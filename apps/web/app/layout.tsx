import type { Metadata, Viewport } from 'next';

import { BRAND_DESCRIPTION, BRAND_NAME, BRAND_SITE_URL, BRAND_TAGLINE } from '@/lib/brand';
import { Providers } from '@/components/providers';

import './globals.css';

export const metadata: Metadata = {
  metadataBase: new URL(BRAND_SITE_URL),
  title: BRAND_NAME,
  description: BRAND_DESCRIPTION,
  manifest: '/site.webmanifest',
  icons: {
    icon: [
      { url: '/favicon.ico', sizes: 'any' },
      { url: '/favicon-16x16.png', type: 'image/png', sizes: '16x16' },
      { url: '/favicon-32x32.png', type: 'image/png', sizes: '32x32' },
    ],
    apple: [{ url: '/apple-touch-icon.png', sizes: '180x180' }],
    shortcut: ['/favicon.ico'],
  },
  openGraph: {
    title: BRAND_NAME,
    description: BRAND_TAGLINE,
    url: BRAND_SITE_URL,
    siteName: BRAND_NAME,
    locale: 'pt_BR',
    type: 'website',
  },
};

export const viewport: Viewport = {
  width: 'device-width',
  initialScale: 1,
  minimumScale: 1,
  maximumScale: 1,
  userScalable: false,
  viewportFit: 'cover',
  interactiveWidget: 'resizes-visual',
  themeColor: '#06251F',
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

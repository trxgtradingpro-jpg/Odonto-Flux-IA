/** @type {import('next').NextConfig} */
const isProductionBuild = process.env.NODE_ENV === 'production';

const nextConfig = {
  distDir: isProductionBuild ? '.next' : '.next-dev',
  reactStrictMode: true,
  transpilePackages: ['@odontoflux/ui', '@odontoflux/shared-types'],
  webpack: (config, { dev }) => {
    if (dev) {
      // Em Docker + volume do Windows, o cache de filesystem pode corromper módulos em HMR.
      config.cache = false;
    }
    return config;
  },
  async rewrites() {
    const apiTarget = process.env.ODONTOFLUX_API_INTERNAL_URL || 'http://api:8000';
    return [
      {
        source: '/api/v1/:path*',
        destination: `${apiTarget}/api/v1/:path*`,
      },
    ];
  },
};

export default nextConfig;

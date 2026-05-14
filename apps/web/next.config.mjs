const nextConfig = {
  distDir: ".next",
  reactStrictMode: true,
  transpilePackages: ["@odontoflux/ui", "@odontoflux/shared-types"],
  async rewrites() {
    const apiTarget = process.env.ODONTOFLUX_API_INTERNAL_URL || "http://api:8000";
    return [
      {
        source: "/api/v1/:path*",
        destination: `${apiTarget}/api/v1/:path*`,
      },
    ];
  },
};

export default nextConfig;

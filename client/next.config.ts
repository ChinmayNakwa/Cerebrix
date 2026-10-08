import type { NextConfig } from "next";

const API_URL = process.env.API_URL ?? 'http://127.0.0.1:8000';

const nextConfig: NextConfig = {
  // Pin the workspace root so a lockfile outside the project can't be picked up instead.
  turbopack: {
    root: __dirname,
  },
  async rewrites() {
    return [
      {
        source: '/api/py/:path*',
        destination: `${API_URL}/:path*`, // Proxy to Python
      },
    ];
  },
};

export default nextConfig;

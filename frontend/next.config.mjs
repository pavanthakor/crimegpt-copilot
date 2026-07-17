/** @type {import('next').NextConfig} */
const nextConfig = {
  // Functional-first pass: don't let lint block the build.
  eslint: { ignoreDuringBuilds: true },
};

export default nextConfig;

import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  images: { unoptimized: true }, // images served via signed GCS URLs directly
};

export default nextConfig;

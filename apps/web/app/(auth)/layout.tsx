import type { Metadata } from "next";

import { BRAND_NAME } from "@/lib/brand";

export const metadata: Metadata = {
  robots: {
    follow: false,
    index: false,
  },
  title: `Entrar | ${BRAND_NAME}`,
};

export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-screen items-center justify-center overflow-hidden px-4 py-8 sm:px-6 lg:px-8">
      <div className="w-full max-w-6xl">{children}</div>
    </div>
  );
}

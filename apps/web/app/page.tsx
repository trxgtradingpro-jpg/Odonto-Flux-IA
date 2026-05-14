import type { Metadata } from "next";

import { BRAND_DESCRIPTION, BRAND_NAME, BRAND_TAGLINE } from "@/lib/brand";
import { LandingPage } from "@/components/marketing/landing-page";

export const metadata: Metadata = {
  title: `${BRAND_NAME} | ${BRAND_TAGLINE}`,
  description: BRAND_DESCRIPTION,
};

export default function HomePage() {
  return <LandingPage />;
}

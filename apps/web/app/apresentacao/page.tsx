import type { Metadata } from "next";

import { BRAND_DESCRIPTION, BRAND_NAME, BRAND_TAGLINE } from "@/lib/brand";
import { LandingPage } from "@/components/marketing/landing-page";

export const metadata: Metadata = {
  title: `Ver demonstracao | ${BRAND_NAME}`,
  description: `${BRAND_TAGLINE} ${BRAND_DESCRIPTION}`,
};

export default function PresentationPage() {
  return <LandingPage />;
}

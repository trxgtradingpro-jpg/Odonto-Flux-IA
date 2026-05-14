import type { Metadata } from "next";

import { LandingPage } from "@/components/marketing/landing-page";

export const metadata: Metadata = {
  title: "Apresentacao OdontoFlux",
  description: "Pagina comercial do OdontoFlux para apresentar a plataforma a clinicas odontologicas.",
};

export default function PresentationPage() {
  return <LandingPage />;
}

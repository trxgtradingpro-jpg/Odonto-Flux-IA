import type { Metadata } from "next";

import { LandingPage } from "@/components/marketing/landing-page";

export const metadata: Metadata = {
  title: "OdontoFlux | Operacao odontologica em tempo real",
  description: "Central operacional para clinicas odontologicas com WhatsApp, agenda, pacientes, equipe e implantacao assistida.",
};

export default function HomePage() {
  return <LandingPage />;
}

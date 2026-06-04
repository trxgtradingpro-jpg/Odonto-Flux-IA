import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { SiteTemplateSectionPage } from "@/components/site-templates/site-template-landing";
import { BRAND_NAME } from "@/lib/brand";
import type { SiteTemplateSectionKey } from "@/lib/site-templates";
import { SITE_TEMPLATES, getSiteTemplateBySlug } from "@/lib/site-templates";

type TemplateSectionPreviewPageProps = {
  params: Promise<{ slug: string; section: string }>;
  searchParams?: Promise<Record<string, string | string[] | undefined>>;
};

const SECTION_LABELS: Record<SiteTemplateSectionKey, string> = {
  tratamentos: "Tratamentos",
  equipe: "Equipe",
  estrutura: "Estrutura",
  contato: "Contato",
};

function singleParam(value: string | string[] | undefined) {
  if (Array.isArray(value)) return value[0] || "";
  return value || "";
}

function isTemplateSectionKey(value: string): value is SiteTemplateSectionKey {
  return value === "tratamentos" || value === "equipe" || value === "estrutura" || value === "contato";
}

export function generateStaticParams() {
  return SITE_TEMPLATES.flatMap((template) =>
    Object.keys(SECTION_LABELS).map((section) => ({
      slug: template.slug,
      section,
    })),
  );
}

export async function generateMetadata({ params }: TemplateSectionPreviewPageProps): Promise<Metadata> {
  const { slug, section } = await params;
  const template = getSiteTemplateBySlug(slug);

  if (!template || !isTemplateSectionKey(section)) {
    return {
      title: `Modelo de site | ${BRAND_NAME}`,
    };
  }

  return {
    title: `${SECTION_LABELS[section]} | ${template.name} | ${BRAND_NAME}`,
    description: `${SECTION_LABELS[section]} do modelo premium ${template.name}.`,
  };
}

export default async function TemplateSectionPreviewPage({ params, searchParams }: TemplateSectionPreviewPageProps) {
  const { slug, section } = await params;
  const template = getSiteTemplateBySlug(slug);

  if (!template || !isTemplateSectionKey(section)) {
    notFound();
  }

  const resolvedSearchParams = (await searchParams) ?? {};
  const clinicName = singleParam(resolvedSearchParams.clinic);
  const city = singleParam(resolvedSearchParams.city);
  const whatsapp = singleParam(resolvedSearchParams.whatsapp);

  return (
    <SiteTemplateSectionPage
      template={template}
      page={section}
      clinicName={clinicName}
      city={city}
      whatsapp={whatsapp}
    />
  );
}

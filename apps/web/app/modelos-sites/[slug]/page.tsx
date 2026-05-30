import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { SiteTemplateLanding } from "@/components/site-templates/site-template-landing";
import { TemplateSelectionForm } from "@/components/site-templates/template-selection-form";
import { BRAND_NAME } from "@/lib/brand";
import { SITE_TEMPLATES, getSiteTemplateBySlug } from "@/lib/site-templates";

type TemplatePreviewPageProps = {
  params: Promise<{ slug: string }>;
  searchParams?: Promise<Record<string, string | string[] | undefined>>;
};

function singleParam(value: string | string[] | undefined) {
  if (Array.isArray(value)) return value[0] || "";
  return value || "";
}

export function generateStaticParams() {
  return SITE_TEMPLATES.map((template) => ({ slug: template.slug }));
}

export async function generateMetadata({ params }: TemplatePreviewPageProps): Promise<Metadata> {
  const { slug } = await params;
  const template = getSiteTemplateBySlug(slug);
  if (!template) {
    return {
      title: `Modelo de site | ${BRAND_NAME}`,
    };
  }
  return {
    title: `${template.name} | Modelos de sites ${BRAND_NAME}`,
    description: template.subheadline,
  };
}

export default async function TemplatePreviewPage({ params, searchParams }: TemplatePreviewPageProps) {
  const { slug } = await params;
  const template = getSiteTemplateBySlug(slug);
  if (!template) notFound();

  const resolvedSearchParams = (await searchParams) ?? {};
  const clinicName = singleParam(resolvedSearchParams.clinic);
  const city = singleParam(resolvedSearchParams.city);
  const whatsapp = singleParam(resolvedSearchParams.whatsapp);

  return (
    <>
      <SiteTemplateLanding template={template} clinicName={clinicName} city={city} whatsapp={whatsapp} />
      <TemplateSelectionForm templates={SITE_TEMPLATES} defaultTemplateSlug={template.slug} />
    </>
  );
}

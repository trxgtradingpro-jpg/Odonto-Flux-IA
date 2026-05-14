"use client";

import type { SessionContext } from "@/hooks/use-session";

import { GuidedDemoController } from "@/components/demo-tour/guided-demo-controller";

export function DemoGuidedTour({
  session,
  pathname,
}: {
  session: SessionContext | undefined;
  pathname: string;
}) {
  return <GuidedDemoController session={session} pathname={pathname} />;
}

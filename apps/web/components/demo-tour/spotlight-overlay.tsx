"use client";

import type { CSSProperties, ReactNode } from "react";

import { cn } from "@odontoflux/ui";

import { TourTooltipCard } from "./tour-tooltip-card";

type SpotlightOverlayProps = {
  rect: DOMRect | null;
  badge?: string;
  title: string;
  description: ReactNode;
  primaryLabel?: string;
  secondaryLabel?: string;
  statusLabel?: string;
  testActions?: Array<{
    label: string;
    onClick: () => void;
  }>;
  align?: "top" | "bottom" | "center" | "left";
  compact?: boolean;
  showTargetFrame?: boolean;
  primaryLoading?: boolean;
  visualState?: "idle" | "exiting";
  onPrimaryAction?: () => void;
  onSecondaryAction?: () => void;
};

type SpotlightCardLayout = {
  cardStyle: CSSProperties;
  cardWidth: number;
  pointerStyle: CSSProperties | null;
  pointerPosition: "top" | "bottom" | "right" | null;
};

function clamp(value: number, min: number, max: number) {
  return Math.max(min, Math.min(max, value));
}

function resolveCardLayout(
  rect: DOMRect | null,
  align: SpotlightOverlayProps["align"],
  compact: boolean,
): SpotlightCardLayout {
  const viewportWidth = typeof window === "undefined" ? 1440 : window.innerWidth;
  const viewportHeight = typeof window === "undefined" ? 900 : window.innerHeight;
  const cardWidth = Math.min(compact ? 352 : 384, viewportWidth - 24);

  if (!rect || align === "center") {
    return {
      cardStyle: {
        left: "50%",
        top: "50%",
        width: cardWidth,
        transform: "translate(-50%, -50%)",
      },
      cardWidth,
      pointerStyle: null,
      pointerPosition: null,
    };
  }

  if (align === "left") {
    const cardHeight = compact ? 208 : 236;
    const gap = 18;
    const preferredLeft = rect.left - cardWidth - gap;
    const safeLeft = clamp(preferredLeft, 12, viewportWidth - cardWidth - 12);
    const preferredTop = rect.top + rect.height / 2 - cardHeight / 2;
    const safeTop = clamp(preferredTop, 16, viewportHeight - cardHeight - 16);
    const pointerTop = clamp(rect.top + rect.height / 2 - safeTop - 10, 28, cardHeight - 28);

    return {
      cardStyle: {
        left: safeLeft,
        top: safeTop,
        width: cardWidth,
      },
      cardWidth,
      pointerStyle: {
        top: pointerTop,
      },
      pointerPosition: "right",
    };
  }

  const preferredLeft = rect.left + rect.width / 2 - cardWidth / 2;
  const safeLeft = clamp(preferredLeft, 12, viewportWidth - cardWidth - 12);
  const prefersTop = align === "top";
  const cardHeight = compact ? 208 : 236;
  const gap = 18;
  const preferredTop = prefersTop ? rect.top - cardHeight - gap : rect.bottom + gap;
  const safeTop = clamp(preferredTop, 16, viewportHeight - cardHeight - 16);
  const pointerLeft = clamp(rect.left + rect.width / 2 - safeLeft - 10, 28, cardWidth - 28);

  return {
    cardStyle: {
      left: safeLeft,
      top: safeTop,
      width: cardWidth,
    },
    cardWidth,
    pointerStyle: {
      left: pointerLeft,
    },
    pointerPosition: prefersTop ? "bottom" : "top",
  };
}

export function SpotlightOverlay({
  rect,
  badge,
  title,
  description,
  primaryLabel,
  secondaryLabel,
  statusLabel,
  testActions,
  align = "bottom",
  compact = false,
  showTargetFrame = true,
  primaryLoading = false,
  visualState = "idle",
  onPrimaryAction,
  onSecondaryAction,
}: SpotlightOverlayProps) {
  const { cardStyle, pointerPosition, pointerStyle } = resolveCardLayout(rect, align, compact);
  const viewportWidth = typeof window === "undefined" ? 1440 : window.innerWidth;
  const viewportHeight = typeof window === "undefined" ? 900 : window.innerHeight;
  const veilColor = "rgba(6,37,31,0.24)";
  const paddedTop = rect && showTargetFrame ? clamp(rect.top - 10, 0, viewportHeight) : 0;
  const paddedLeft = rect && showTargetFrame ? clamp(rect.left - 10, 0, viewportWidth) : 0;
  const paddedRect =
    rect && showTargetFrame
      ? {
          top: paddedTop,
          left: paddedLeft,
          width: Math.max(0, Math.min(rect.width + 20, viewportWidth - paddedLeft)),
          height: Math.max(0, Math.min(rect.height + 20, viewportHeight - paddedTop)),
        }
      : null;

  return (
    <div className="pointer-events-none fixed inset-0 z-[92]">
      {!paddedRect ? <div className="absolute inset-0 bg-[rgba(6,37,31,0.34)]" /> : null}

      {paddedRect ? (
        <>
          <div className="absolute left-0 right-0 top-0" style={{ height: paddedRect.top, backgroundColor: veilColor }} />
          <div
            className="absolute left-0"
            style={{ top: paddedRect.top, width: paddedRect.left, height: paddedRect.height, backgroundColor: veilColor }}
          />
          <div
            className="absolute right-0"
            style={{
              top: paddedRect.top,
              left: paddedRect.left + paddedRect.width,
              height: paddedRect.height,
              backgroundColor: veilColor,
            }}
          />
          <div
            className="absolute bottom-0 left-0 right-0"
            style={{ top: paddedRect.top + paddedRect.height, backgroundColor: veilColor }}
          />
        </>
      ) : null}

      {paddedRect ? (
        <div
          className="absolute rounded-[30px] border border-white/85 transition-all duration-300"
          style={{
            ...paddedRect,
            boxShadow: "0 0 0 1px rgba(255,255,255,0.48), 0 0 26px rgba(0,168,132,0.2)",
          }}
        />
      ) : null}

      <div
        className={cn(
          "pointer-events-auto absolute transition-all duration-300",
          align === "center" && "flex justify-center",
        )}
        style={cardStyle}
      >
        {pointerPosition ? (
          <div
            className={cn(
              "absolute h-5 w-5 rotate-45 rounded-[6px] border border-white/60 bg-[linear-gradient(180deg,rgba(247,255,252,0.98),rgba(255,255,255,0.96))] shadow-[0_14px_40px_rgba(6,37,31,0.12)]",
              pointerPosition === "top" && "-top-2.5",
              pointerPosition === "bottom" && "-bottom-2.5",
              pointerPosition === "right" && "-right-2.5",
            )}
            style={pointerStyle ?? undefined}
          />
        ) : null}
        <TourTooltipCard
          badge={badge}
          title={title}
          description={description}
          primaryLabel={primaryLabel}
          secondaryLabel={secondaryLabel}
          statusLabel={statusLabel}
          testActions={testActions}
          compact={compact}
          primaryLoading={primaryLoading}
          visualState={visualState}
          onPrimaryAction={onPrimaryAction}
          onSecondaryAction={onSecondaryAction}
        />
      </div>
    </div>
  );
}

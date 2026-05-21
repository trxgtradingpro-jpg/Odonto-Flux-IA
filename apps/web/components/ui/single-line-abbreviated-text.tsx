"use client";

import { useLayoutEffect, useRef, useState } from "react";

import { cn } from "@odontoflux/ui";

function abbreviateToFit(text: string, maxWidth: number, measure: HTMLSpanElement) {
  measure.textContent = text;
  if (measure.scrollWidth <= maxWidth) {
    return text;
  }

  let low = 1;
  let high = text.length;
  let best = ".";

  while (low <= high) {
    const mid = Math.floor((low + high) / 2);
    const candidate = `${text.slice(0, mid).trimEnd()}.`;
    measure.textContent = candidate;

    if (measure.scrollWidth <= maxWidth) {
      best = candidate;
      low = mid + 1;
    } else {
      high = mid - 1;
    }
  }

  return best;
}

export function SingleLineAbbreviatedText({
  text,
  className,
  title,
}: {
  text: string;
  className?: string;
  title?: string;
}) {
  const hostRef = useRef<HTMLSpanElement | null>(null);
  const measureRef = useRef<HTMLSpanElement | null>(null);
  const [displayText, setDisplayText] = useState(text);

  useLayoutEffect(() => {
    const host = hostRef.current;
    const measure = measureRef.current;
    if (!host || !measure) return;

    const sync = () => {
      const nextText = abbreviateToFit(text, host.clientWidth, measure);
      setDisplayText((current) => (current === nextText ? current : nextText));
    };

    sync();

    const observer = new ResizeObserver(sync);
    observer.observe(host);
    return () => observer.disconnect();
  }, [text]);

  useLayoutEffect(() => {
    setDisplayText(text);
  }, [text]);

  return (
    <>
      <span ref={hostRef} className={cn("block min-w-0 max-w-full truncate whitespace-nowrap", className)} title={title ?? text}>
        {displayText}
      </span>
      <span
        ref={measureRef}
        aria-hidden="true"
        className={cn(
          "pointer-events-none fixed left-[-9999px] top-[-9999px] block whitespace-nowrap opacity-0",
          className,
        )}
      />
    </>
  );
}

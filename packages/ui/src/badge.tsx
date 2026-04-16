import * as React from 'react';

import { cn } from './utils';

export function Badge({ className, ...props }: React.HTMLAttributes<HTMLSpanElement>) {
  return (
    <span
      className={cn(
        'inline-flex items-center rounded-full border border-transparent bg-stone-200 px-2.5 py-1 text-xs font-semibold text-stone-700',
        className,
      )}
      {...props}
    />
  );
}

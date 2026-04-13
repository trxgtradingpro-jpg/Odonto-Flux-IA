import * as React from 'react';

import { cn } from './utils';

export function Badge({ className, ...props }: React.HTMLAttributes<HTMLSpanElement>) {
  return (
    <span
      className={cn(
        'inline-flex items-center rounded-full bg-stone-200 px-2.5 py-1 text-xs font-medium text-stone-700',
        className,
      )}
      {...props}
    />
  );
}

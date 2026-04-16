import * as React from 'react';

import { cn } from './utils';

export function Input({ className, ...props }: React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      className={cn(
        'h-10 min-w-0 w-full rounded-md border border-border bg-white px-3 text-base outline-none transition focus:border-primary focus:ring-2 focus:ring-primary/20 sm:text-sm',
        className,
      )}
      {...props}
    />
  );
}

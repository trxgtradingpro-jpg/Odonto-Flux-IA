import * as React from 'react';

import { cn } from './utils';

export function Input({ className, ...props }: React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      className={cn(
        'h-11 min-w-0 w-full rounded-lg border border-border bg-white px-3.5 text-sm text-foreground shadow-[inset_0_1px_0_rgba(255,255,255,0.8)] outline-none transition placeholder:text-slate-500 hover:border-slate-400 focus:border-primary focus:ring-4 focus:ring-primary/15',
        className,
      )}
      {...props}
    />
  );
}

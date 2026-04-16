import * as React from 'react';

import { cn } from './utils';

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'default' | 'outline' | 'destructive' | 'ghost';
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant = 'default', ...props }, ref) => {
    const variants = {
      default:
        'bg-primary text-primary-foreground shadow-sm hover:opacity-95 focus-visible:ring-4 focus-visible:ring-primary/25',
      outline:
        'bg-white text-foreground border border-border hover:bg-stone-50 hover:border-stone-400 focus-visible:ring-4 focus-visible:ring-primary/15',
      destructive:
        'bg-red-600 text-white shadow-sm hover:bg-red-700 focus-visible:ring-4 focus-visible:ring-red-300',
      ghost:
        'bg-transparent text-foreground hover:bg-stone-100 focus-visible:ring-4 focus-visible:ring-primary/15',
    };

    return (
      <button
        ref={ref}
        className={cn(
          'inline-flex h-10 min-w-0 items-center justify-center gap-1.5 rounded-lg px-4 text-sm font-semibold whitespace-nowrap transition duration-150 active:translate-y-[1px] disabled:pointer-events-none disabled:cursor-not-allowed disabled:opacity-60',
          variants[variant],
          className,
        )}
        {...props}
      />
    );
  },
);

Button.displayName = 'Button';

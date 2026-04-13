"use client";

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ReactQueryDevtools } from '@tanstack/react-query-devtools';
import { PropsWithChildren, useEffect, useState } from 'react';
import { Toaster } from 'sonner';

export function Providers({ children }: PropsWithChildren) {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            retry: 1,
            refetchOnWindowFocus: false,
            staleTime: 20_000,
          },
        },
      }),
  );

  useEffect(() => {
    const guardKey = 'odontoflux_chunk_reload_guard';

    const shouldReload = (message?: string) => {
      if (!message) return false;
      const normalized = message.toLowerCase();
      return normalized.includes('chunkloaderror') || normalized.includes('loading chunk');
    };

    const triggerReload = () => {
      if (sessionStorage.getItem(guardKey) === '1') return;
      sessionStorage.setItem(guardKey, '1');
      window.location.reload();
    };

    const clearGuard = () => {
      sessionStorage.removeItem(guardKey);
    };

    const onError = (event: ErrorEvent) => {
      if (shouldReload(event.message) || shouldReload(event.error?.message)) {
        triggerReload();
      }
    };

    const onUnhandledRejection = (event: PromiseRejectionEvent) => {
      const reason = event.reason;
      const reasonMessage =
        typeof reason === 'string'
          ? reason
          : typeof reason?.message === 'string'
            ? reason.message
            : undefined;
      if (shouldReload(reasonMessage)) {
        triggerReload();
      }
    };

    window.addEventListener('error', onError);
    window.addEventListener('unhandledrejection', onUnhandledRejection);
    window.addEventListener('pageshow', clearGuard);

    return () => {
      window.removeEventListener('error', onError);
      window.removeEventListener('unhandledrejection', onUnhandledRejection);
      window.removeEventListener('pageshow', clearGuard);
    };
  }, []);

  return (
    <QueryClientProvider client={queryClient}>
      {children}
      <Toaster richColors position="top-right" />
      <ReactQueryDevtools initialIsOpen={false} />
    </QueryClientProvider>
  );
}

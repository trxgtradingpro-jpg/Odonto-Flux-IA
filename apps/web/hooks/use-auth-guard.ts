"use client";

import { useRouter } from 'next/navigation';
import { useEffect, useState } from 'react';

import { clearAccessToken, hasSessionToken } from '@/lib/auth';

export function useAuthGuard() {
  const router = useRouter();
  const [ready, setReady] = useState(false);

  useEffect(() => {
    if (!hasSessionToken()) {
      router.replace('/login');
      return;
    }
    setReady(true);
  }, [router]);

  function logout() {
    clearAccessToken();
    router.replace('/login');
  }

  return { ready, logout };
}

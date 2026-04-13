"use client";

import { useRouter } from 'next/navigation';
import { useEffect, useState } from 'react';

import { clearAccessToken, getAccessToken } from '@/lib/auth';

export function useAuthGuard() {
  const router = useRouter();
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const token = getAccessToken();
    if (!token) {
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

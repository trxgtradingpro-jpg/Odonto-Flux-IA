"use client";

import { AxiosRequestConfig } from "axios";
import { useQuery } from '@tanstack/react-query';

import { api } from '@/lib/api';

export function useResource<TData = unknown>(
  endpoint: string,
  queryKey: string,
  config?: AxiosRequestConfig,
) {
  return useQuery<TData>({
    queryKey: [queryKey, config?.params ?? null],
    queryFn: async () => {
      const response = await api.get(endpoint, config);
      return response.data;
    },
  });
}

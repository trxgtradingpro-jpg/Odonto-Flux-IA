"use client";

import { useQuery } from '@tanstack/react-query';

import { DashboardKPI } from '@odontoflux/shared-types';

import { api } from '@/lib/api';

export function useDashboard() {
  return useQuery<DashboardKPI>({
    queryKey: ['dashboard-kpis'],
    queryFn: async () => {
      const response = await api.get('/dashboards/kpis');
      return response.data;
    },
  });
}

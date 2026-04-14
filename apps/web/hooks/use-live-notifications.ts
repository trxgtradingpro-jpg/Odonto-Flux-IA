"use client";

import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api";
import { ApiPage, AppointmentItem, ConversationItem } from "@/lib/domain-types";

type NotificationItem = {
  id: string;
  title: string;
  description: string;
  level: "info" | "warning" | "success";
  href?: string;
};

type LiveNotifications = {
  badges: {
    conversations: number;
    leads: number;
    appointmentsToday: number;
    pendingConfirmations: number;
  };
  notifications: NotificationItem[];
  updatedAt: string;
};

function startOfToday(): Date {
  const now = new Date();
  return new Date(now.getFullYear(), now.getMonth(), now.getDate());
}

function endOfToday(): Date {
  const today = startOfToday();
  return new Date(today.getFullYear(), today.getMonth(), today.getDate() + 1);
}

export function useLiveNotifications() {
  return useQuery<LiveNotifications>({
    queryKey: ["live-notifications"],
    queryFn: async () => {
      const [appointmentsResponse, conversationsResponse, leadsResponse] = await Promise.all([
        api.get<ApiPage<AppointmentItem>>("/appointments", { params: { limit: 300, offset: 0 } }),
        api.get<ApiPage<ConversationItem>>("/conversations", { params: { limit: 300, offset: 0 } }),
        api.get<ApiPage<Record<string, unknown>>>("/leads", { params: { limit: 1, offset: 0 } }),
      ]);

      const appointments = appointmentsResponse.data.data ?? [];
      const conversations = conversationsResponse.data.data ?? [];
      const leadsMeta = leadsResponse.data.meta ?? { total: 0 };

      const todayStart = startOfToday();
      const todayEnd = endOfToday();

      const appointmentsToday = appointments.filter((item) => {
        const date = new Date(item.starts_at);
        return date >= todayStart && date < todayEnd;
      });
      const pendingConfirmations = appointmentsToday.filter((item) => item.confirmation_status === "pendente").length;
      const openConversations = conversations.filter((item) => item.status === "aberta").length;

      const nextAppointment = appointments
        .filter((item) => item.status !== "cancelada")
        .sort((left, right) => new Date(left.starts_at).getTime() - new Date(right.starts_at).getTime())
        .find((item) => new Date(item.starts_at).getTime() >= Date.now());

      const notifications: NotificationItem[] = [];
      notifications.push({
        id: "pending-confirmations",
        title: "Confirmacoes pendentes",
        description: `${pendingConfirmations} consulta(s) aguardando confirmacao hoje.`,
        level: pendingConfirmations > 0 ? "warning" : "success",
        href: "/agenda",
      });
      notifications.push({
        id: "open-conversations",
        title: "Conversas abertas",
        description: `${openConversations} conversa(s) em aberto na fila de atendimento.`,
        level: openConversations > 0 ? "info" : "success",
        href: "/conversas",
      });
      notifications.push({
        id: "lead-pipeline",
        title: "Pipeline de leads",
        description: `${leadsMeta.total ?? 0} lead(s) ativos no funil.`,
        level: "info",
        href: "/leads",
      });
      if (nextAppointment) {
        notifications.push({
          id: "next-appointment",
          title: "Proxima consulta",
          description: `Agendada para ${new Date(nextAppointment.starts_at).toLocaleString("pt-BR")}.`,
          level: "info",
          href: "/agenda",
        });
      }

      return {
        badges: {
          conversations: openConversations,
          leads: leadsMeta.total ?? 0,
          appointmentsToday: appointmentsToday.length,
          pendingConfirmations,
        },
        notifications: notifications.slice(0, 6),
        updatedAt: new Date().toISOString(),
      };
    },
    staleTime: 5_000,
    refetchInterval: 12_000,
    refetchOnWindowFocus: true,
  });
}


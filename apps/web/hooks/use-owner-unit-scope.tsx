"use client";

import { createContext, useContext, useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api";
import { ApiPage, UnitItem } from "@/lib/domain-types";
import { SessionContext } from "@/hooks/use-session";

type OwnerUnitScopeContextValue = {
  canSwitchUnits: boolean;
  selectedUnitId: string;
  selectedUnitName: string;
  units: UnitItem[];
  setSelectedUnitId: (value: string) => void;
};

const OwnerUnitScopeContext = createContext<OwnerUnitScopeContextValue | null>(null);

function storageKey(tenantId?: string | null) {
  return `odontoflux.owner-unit-scope.${tenantId ?? "default"}`;
}

function resolveInitialUnitId(session?: SessionContext, units: UnitItem[] = []) {
  if (session?.unit_id && units.some((unit) => unit.id === session.unit_id)) {
    return session.unit_id;
  }
  return "all";
}

export function OwnerUnitScopeProvider({
  session,
  children,
}: {
  session?: SessionContext;
  children: React.ReactNode;
}) {
  const canSwitchUnits = Boolean(session?.roles?.includes("owner") && session?.tenant_id);
  const unitsQuery = useQuery<ApiPage<UnitItem>>({
    queryKey: ["owner-unit-scope-units", session?.tenant_id],
    queryFn: async () => (await api.get<ApiPage<UnitItem>>("/units", { params: { limit: 100, offset: 0 } })).data,
    enabled: canSwitchUnits,
    staleTime: 60_000,
  });
  const units = unitsQuery.data?.data ?? [];
  const [selectedUnitId, setSelectedUnitIdState] = useState<string>("all");

  useEffect(() => {
    if (!canSwitchUnits) {
      setSelectedUnitIdState("all");
      return;
    }
    if (typeof window === "undefined") return;

    const stored = window.localStorage.getItem(storageKey(session?.tenant_id));
    const validStored =
      stored === "all" || units.some((unit) => unit.id === stored) ? stored : null;
    const fallback = resolveInitialUnitId(session, units);
    setSelectedUnitIdState(validStored ?? fallback);
  }, [canSwitchUnits, session, units]);

  const setSelectedUnitId = (value: string) => {
    if (!canSwitchUnits) return;
    const nextValue =
      value === "all" || units.some((unit) => unit.id === value)
        ? value
        : resolveInitialUnitId(session, units);
    setSelectedUnitIdState(nextValue);
    if (typeof window !== "undefined") {
      window.localStorage.setItem(storageKey(session?.tenant_id), nextValue);
    }
  };

  const selectedUnitName = useMemo(() => {
    if (!canSwitchUnits) {
      return session?.unit_name ?? "Unidade principal";
    }
    if (selectedUnitId === "all") {
      return "Todas as unidades";
    }
    return units.find((unit) => unit.id === selectedUnitId)?.name ?? session?.unit_name ?? "Unidade principal";
  }, [canSwitchUnits, selectedUnitId, session?.unit_name, units]);

  const value = useMemo<OwnerUnitScopeContextValue>(
    () => ({
      canSwitchUnits,
      selectedUnitId,
      selectedUnitName,
      units,
      setSelectedUnitId,
    }),
    [canSwitchUnits, selectedUnitId, selectedUnitName, units],
  );

  return <OwnerUnitScopeContext.Provider value={value}>{children}</OwnerUnitScopeContext.Provider>;
}

export function useOwnerUnitScope() {
  const context = useContext(OwnerUnitScopeContext);
  if (!context) {
    return {
      canSwitchUnits: false,
      selectedUnitId: "all",
      selectedUnitName: "Unidade principal",
      units: [] as UnitItem[],
      setSelectedUnitId: (_value: string) => {},
    };
  }
  return context;
}

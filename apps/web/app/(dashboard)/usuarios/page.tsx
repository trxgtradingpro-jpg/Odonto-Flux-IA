"use client";

import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { MailPlus, UserPlus } from "lucide-react";
import { toast } from "sonner";

import { DataTable, FilterBar, PageHeader, StatusBadge } from "@/components/premium";
import { ErrorState, LoadingState } from "@/components/page-state";
import { api } from "@/lib/api";
import { ApiPage, UnitItem, UserItem } from "@/lib/domain-types";
import { formatDateTimeBR, ROLE_LABELS } from "@/lib/formatters";
import { Button, Card, CardContent, CardHeader, CardTitle, Input } from "@odontoflux/ui";

const ROLE_OPTIONS = ["owner", "manager", "receptionist", "analyst", "admin_platform"];

export default function UsuariosPage() {
  const queryClient = useQueryClient();
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");

  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState("receptionist");

  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRole, setInviteRole] = useState("receptionist");

  const usersQuery = useQuery<{ users: UserItem[]; units: UnitItem[] }>({
    queryKey: ["users-dataset"],
    queryFn: async () => {
      const [usersResponse, unitsResponse] = await Promise.all([
        api.get<ApiPage<UserItem>>("/users", { params: { limit: 200, offset: 0 } }),
        api.get<ApiPage<UnitItem>>("/units", { params: { limit: 100, offset: 0 } }),
      ]);
      return {
        users: usersResponse.data.data ?? [],
        units: unitsResponse.data.data ?? [],
      };
    },
  });

  const createMutation = useMutation({
    mutationFn: async () => api.post("/users", { email, full_name: name, password, roles: [role] }),
    onSuccess: () => {
      toast.success("Usuário criado com sucesso.");
      setName("");
      setEmail("");
      setPassword("");
      setRole("receptionist");
      queryClient.invalidateQueries({ queryKey: ["users-dataset"] });
    },
    onError: () => toast.error("Não foi possível criar o usuário."),
  });

  const inviteMutation = useMutation({
    mutationFn: async () => (await api.post("/users/invite", { email: inviteEmail, role_name: inviteRole })).data,
    onSuccess: (data) => {
      toast.success(`Convite criado. Token de demo: ${String(data.invite_token).slice(0, 12)}...`);
      setInviteEmail("");
      setInviteRole("receptionist");
    },
    onError: () => toast.error("Não foi possível gerar convite."),
  });

  const updateMutation = useMutation({
    mutationFn: async ({ userId, payload }: { userId: string; payload: Record<string, unknown> }) =>
      api.patch(`/users/${userId}`, payload),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["users-dataset"] }),
    onError: () => toast.error("Não foi possível atualizar o usuário."),
  });

  if (usersQuery.isLoading) return <LoadingState message="Carregando usuários..." />;
  if (usersQuery.isError || !usersQuery.data) return <ErrorState message="Não foi possível carregar usuários." />;

  const defaultUnit = usersQuery.data.units[0]?.name ?? "Unidade principal";
  const rows = usersQuery.data.users
    .filter((user) => {
      const term = search.toLowerCase().trim();
      const haystack = `${user.full_name} ${user.email} ${(user.roles || []).join(" ")}`.toLowerCase();
      const bySearch = !term || haystack.includes(term);
      const byStatus =
        statusFilter === "all" ||
        (statusFilter === "active" && user.is_active) ||
        (statusFilter === "inactive" && !user.is_active);
      return bySearch && byStatus;
    })
    .map((user) => ({
      ...user,
      role_label: ROLE_LABELS[user.roles?.[0] ?? ""] ?? "Perfil customizado",
      unit_name: defaultUnit,
      last_access: user.last_login_at ?? user.created_at,
    }));

  return (
    <div className="space-y-4">
      <PageHeader
        eyebrow="Acesso e governança"
        title="Usuários e permissões"
        description="Gestão de perfis, convites, ativação e segurança operacional."
      />

      <div className="grid gap-4 xl:grid-cols-2">
        <Card className="border-stone-200">
          <CardHeader>
            <CardTitle>Novo usuário</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid gap-2 md:grid-cols-5">
              <Input placeholder="Nome completo" value={name} onChange={(event) => setName(event.target.value)} />
              <Input placeholder="E-mail" type="email" value={email} onChange={(event) => setEmail(event.target.value)} />
              <Input placeholder="Senha temporária" type="password" value={password} onChange={(event) => setPassword(event.target.value)} />
              <select
                className="h-10 rounded-md border border-stone-300 bg-white px-3 text-sm"
                value={role}
                onChange={(event) => setRole(event.target.value)}
              >
                {ROLE_OPTIONS.map((option) => (
                  <option key={option} value={option}>
                    {ROLE_LABELS[option] ?? option}
                  </option>
                ))}
              </select>
              <Button
                className="gap-1.5"
                onClick={() => {
                  if (!name.trim() || !email.trim() || !password.trim()) {
                    toast.error("Preencha nome, e-mail e senha.");
                    return;
                  }
                  createMutation.mutate();
                }}
                disabled={createMutation.isPending}
              >
                <UserPlus size={14} />
                {createMutation.isPending ? "Criando..." : "Criar usuário"}
              </Button>
            </div>
          </CardContent>
        </Card>

        <Card className="border-stone-200">
          <CardHeader>
            <CardTitle>Convidar usuário</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid gap-2 md:grid-cols-4">
              <Input
                placeholder="E-mail para convite"
                type="email"
                value={inviteEmail}
                onChange={(event) => setInviteEmail(event.target.value)}
              />
              <select
                className="h-10 rounded-md border border-stone-300 bg-white px-3 text-sm"
                value={inviteRole}
                onChange={(event) => setInviteRole(event.target.value)}
              >
                {ROLE_OPTIONS.map((option) => (
                  <option key={option} value={option}>
                    {ROLE_LABELS[option] ?? option}
                  </option>
                ))}
              </select>
              <Button
                className="gap-1.5"
                onClick={() => {
                  if (!inviteEmail.trim()) {
                    toast.error("Informe o e-mail do convite.");
                    return;
                  }
                  inviteMutation.mutate();
                }}
                disabled={inviteMutation.isPending}
              >
                <MailPlus size={14} />
                {inviteMutation.isPending ? "Gerando..." : "Gerar convite"}
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>

      <FilterBar search={search} onSearchChange={setSearch} searchPlaceholder="Buscar por nome, e-mail ou perfil...">
        <select
          className="h-9 rounded-md border border-stone-300 bg-white px-2 text-sm"
          value={statusFilter}
          onChange={(event) => setStatusFilter(event.target.value)}
        >
          <option value="all">Todos os status</option>
          <option value="active">Ativos</option>
          <option value="inactive">Inativos</option>
        </select>
      </FilterBar>

      <DataTable<(typeof rows)[number]>
        title="Usuários"
        rows={rows}
        getRowId={(item) => item.id}
        searchBy={(item) => `${item.full_name} ${item.email} ${item.role_label}`}
        columns={[
          {
            key: "nome",
            label: "Usuário",
            render: (item) => (
              <div>
                <p className="font-semibold text-stone-800">{item.full_name}</p>
                <p className="text-xs text-stone-500">{item.email}</p>
              </div>
            ),
          },
          {
            key: "cargo",
            label: "Cargo",
            render: (item) => item.role_label,
          },
          {
            key: "unidade",
            label: "Unidade",
            render: (item) => item.unit_name,
          },
          {
            key: "status",
            label: "Status",
            render: (item) => <StatusBadge value={item.is_active ? "ativo" : "inativo"} />,
          },
          {
            key: "ultimo_acesso",
            label: "Último acesso",
            render: (item) => formatDateTimeBR(item.last_access),
          },
          {
            key: "permissoes",
            label: "Permissões",
            render: (item) => (item.roles || []).map((roleName) => ROLE_LABELS[roleName] ?? roleName).join(", "),
          },
          {
            key: "acoes",
            label: "Ações",
            render: (item) => (
              <div className="flex items-center gap-1">
                <select
                  className="h-8 rounded-md border border-stone-300 bg-white px-2 text-xs"
                  value={item.roles?.[0] ?? "receptionist"}
                  onChange={(event) =>
                    updateMutation.mutate({
                      userId: item.id,
                      payload: { roles: [event.target.value] },
                    })
                  }
                >
                  {ROLE_OPTIONS.map((option) => (
                    <option key={option} value={option}>
                      {ROLE_LABELS[option] ?? option}
                    </option>
                  ))}
                </select>
                <Button
                  variant={item.is_active ? "destructive" : "outline"}
                  className="h-8 px-2 text-xs"
                  onClick={() =>
                    updateMutation.mutate({
                      userId: item.id,
                      payload: { is_active: !item.is_active },
                    })
                  }
                >
                  {item.is_active ? "Desativar" : "Ativar"}
                </Button>
              </div>
            ),
          },
        ]}
        emptyTitle="Sem usuários"
        emptyDescription="Cadastre ou convide usuários para habilitar a operação."
      />
    </div>
  );
}

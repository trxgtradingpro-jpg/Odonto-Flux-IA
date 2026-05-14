"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { MailPlus, Pencil, ShieldCheck, Trash2, UserPlus, X } from "lucide-react";
import { toast } from "sonner";

import { DataTable, FilterBar, PageHeader, RightDrawer, StatusBadge } from "@/components/premium";
import { ErrorState, LoadingState } from "@/components/page-state";
import { useSession } from "@/hooks/use-session";
import { api } from "@/lib/api";
import { ApiPage, UnitItem, UserItem } from "@/lib/domain-types";
import { formatDateTimeBR, ROLE_LABELS } from "@/lib/formatters";
import {
  buildDefaultPagePermissionsForRole,
  canAccessPage,
  createEmptyPagePermissionMap,
  MANAGED_PAGES,
  normalizePagePermissions,
  PageKey,
  PagePermissionMap,
} from "@/lib/page-access";
import { Badge, Button, Card, CardContent, CardHeader, CardTitle, Input } from "@odontoflux/ui";

const ROLE_OPTIONS = ["owner", "manager", "receptionist", "analyst", "admin_platform"];
const UNIT_REQUIRED_ROLES = new Set(["manager", "receptionist"]);

function clonePermissions(input: PagePermissionMap): PagePermissionMap {
  return MANAGED_PAGES.reduce((acc, page) => {
    acc[page.key] = { ...input[page.key] };
    return acc;
  }, createEmptyPagePermissionMap());
}

function countVisiblePages(permissions: PagePermissionMap): number {
  return MANAGED_PAGES.filter((page) => canAccessPage(permissions, page.key, "view")).length;
}

function serializePermissions(permissions: PagePermissionMap): Record<string, { view: boolean; create: boolean; edit: boolean; delete: boolean }> {
  return MANAGED_PAGES.reduce((acc, page) => {
    acc[page.key] = { ...permissions[page.key] };
    return acc;
  }, {} as Record<string, { view: boolean; create: boolean; edit: boolean; delete: boolean }>);
}

function getApiErrorMessage(error: unknown, fallback: string): string {
  const responseData = (error as { response?: { data?: unknown } })?.response?.data;
  if (responseData && typeof responseData === "object") {
    const detail = (responseData as { detail?: Array<{ msg?: string }> }).detail;
    if (Array.isArray(detail) && detail[0]?.msg) {
      return detail[0].msg;
    }
    const apiMessage = (responseData as { error?: { message?: string } })?.error?.message;
    if (typeof apiMessage === "string" && apiMessage.trim()) {
      return apiMessage;
    }
    const directMessage = (responseData as { message?: string })?.message;
    if (typeof directMessage === "string" && directMessage.trim()) {
      return directMessage;
    }
  }
  if (error instanceof Error && error.message.trim()) {
    return error.message;
  }
  return fallback;
}

function PermissionMatrix({
  value,
  onChange,
  disabled = false,
}: {
  value: PagePermissionMap;
  onChange: (next: PagePermissionMap) => void;
  disabled?: boolean;
}) {
  const toggle = (pageKey: PageKey, field: keyof PagePermissionMap[PageKey], checked: boolean) => {
    const next = clonePermissions(value);
    next[pageKey][field] = checked;
    if (!checked && field === "view") {
      next[pageKey].create = false;
      next[pageKey].edit = false;
      next[pageKey].delete = false;
    }
    if (checked && field !== "view") {
      next[pageKey].view = true;
    }
    onChange(next);
  };

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between gap-2">
        <p className="text-sm font-semibold text-stone-800">Permissoes por pagina</p>
        <Badge className="bg-stone-200 text-stone-700">{countVisiblePages(value)} pagina(s) liberada(s)</Badge>
      </div>
      <div className="overflow-hidden rounded-2xl border border-stone-200">
        <div className="grid grid-cols-[minmax(0,1.7fr)_repeat(4,minmax(72px,0.65fr))] gap-px bg-stone-200 text-xs font-semibold uppercase tracking-wide text-stone-500">
          <div className="bg-stone-50 px-3 py-2">Pagina</div>
          <div className="bg-stone-50 px-3 py-2 text-center">Ver</div>
          <div className="bg-stone-50 px-3 py-2 text-center">Adicionar</div>
          <div className="bg-stone-50 px-3 py-2 text-center">Editar</div>
          <div className="bg-stone-50 px-3 py-2 text-center">Excluir</div>
        </div>
        {MANAGED_PAGES.map((page) => (
          <div
            key={page.key}
            className="grid grid-cols-[minmax(0,1.7fr)_repeat(4,minmax(72px,0.65fr))] gap-px border-t border-stone-200 bg-stone-200"
          >
            <div className="bg-white px-3 py-3">
              <p className="text-sm font-medium text-stone-800">{page.label}</p>
              <p className="text-xs text-stone-500">
                {page.menuGroup === "principal" ? "Menu principal horizontal" : "Menu secundario"}
              </p>
            </div>
            {(["view", "create", "edit", "delete"] as const).map((field) => (
              <label
                key={`${page.key}-${field}`}
                className={`flex items-center justify-center bg-white px-3 py-3 ${disabled ? "cursor-not-allowed opacity-70" : ""}`}
              >
                <input
                  type="checkbox"
                  checked={value[page.key][field]}
                  disabled={disabled}
                  onChange={(event) => toggle(page.key, field, event.target.checked)}
                />
              </label>
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}

export default function UsuariosPage() {
  const queryClient = useQueryClient();
  const sessionQuery = useSession();
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [createDrawerOpen, setCreateDrawerOpen] = useState(false);
  const [editDrawerOpen, setEditDrawerOpen] = useState(false);
  const [deleteConfirmOpen, setDeleteConfirmOpen] = useState(false);
  const [selectedUser, setSelectedUser] = useState<UserItem | null>(null);

  const [formName, setFormName] = useState("");
  const [formEmail, setFormEmail] = useState("");
  const [formPassword, setFormPassword] = useState("");
  const [formPhone, setFormPhone] = useState("");
  const [formRole, setFormRole] = useState("receptionist");
  const [formUnitId, setFormUnitId] = useState("");
  const [formForceFullscreen, setFormForceFullscreen] = useState(false);
  const [formPermissions, setFormPermissions] = useState<PagePermissionMap>(() =>
    buildDefaultPagePermissionsForRole("receptionist"),
  );

  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRole, setInviteRole] = useState("receptionist");
  const currentUserPermissions = sessionQuery.data?.resolved_page_permissions;
  const canCreateUsers = canAccessPage(currentUserPermissions, "usuarios", "create");
  const canEditUsers = canAccessPage(currentUserPermissions, "usuarios", "edit");
  const canDeleteUsers = canAccessPage(currentUserPermissions, "usuarios", "delete");

  const resetForm = (role = "receptionist") => {
    setFormName("");
    setFormEmail("");
    setFormPassword("");
    setFormPhone("");
    setFormRole(role);
    setFormUnitId("");
    setFormForceFullscreen(false);
    setFormPermissions(buildDefaultPagePermissionsForRole(role));
  };

  const populateFormFromUser = (user: UserItem) => {
    setFormName(user.full_name || "");
    setFormEmail(user.email || "");
    setFormPassword("");
    setFormPhone(user.phone || "");
    setFormRole(user.roles?.[0] ?? "receptionist");
    setFormUnitId(user.unit_id ?? "");
    setFormForceFullscreen(Boolean(user.force_fullscreen_mode));
    setFormPermissions(normalizePagePermissions(user.page_permissions, user.roles));
  };

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
    mutationFn: async () =>
      api.post("/users", {
        email: formEmail.trim(),
        full_name: formName.trim(),
        password: formPassword,
        phone: formPhone.trim() || null,
        unit_id: formUnitId || null,
        roles: [formRole],
        page_permissions: serializePermissions(formPermissions),
        force_fullscreen_mode: formForceFullscreen,
      }),
    onSuccess: () => {
      toast.success("Usuario criado com sucesso.");
      setCreateDrawerOpen(false);
      resetForm();
      queryClient.invalidateQueries({ queryKey: ["users-dataset"] });
      queryClient.invalidateQueries({ queryKey: ["session-context"] });
    },
    onError: (error) => toast.error(getApiErrorMessage(error, "Nao foi possivel criar o usuario.")),
  });

  const inviteMutation = useMutation({
    mutationFn: async () => (await api.post("/users/invite", { email: inviteEmail, role_name: inviteRole })).data,
    onSuccess: (data) => {
      toast.success(`Convite criado. Token de demo: ${String(data.invite_token).slice(0, 12)}...`);
      setInviteEmail("");
      setInviteRole("receptionist");
    },
    onError: () => toast.error("Nao foi possivel gerar convite."),
  });

  const updateMutation = useMutation({
    mutationFn: async (userId: string) =>
      api.patch(`/users/${userId}`, {
        full_name: formName.trim(),
        phone: formPhone.trim() || null,
        unit_id: formUnitId || null,
        roles: [formRole],
        page_permissions: serializePermissions(formPermissions),
        force_fullscreen_mode: formForceFullscreen,
      }),
    onSuccess: () => {
      toast.success("Usuario atualizado com sucesso.");
      setEditDrawerOpen(false);
      setSelectedUser(null);
      queryClient.invalidateQueries({ queryKey: ["users-dataset"] });
      queryClient.invalidateQueries({ queryKey: ["session-context"] });
    },
    onError: (error) => toast.error(getApiErrorMessage(error, "Nao foi possivel atualizar o usuario.")),
  });

  const toggleActiveMutation = useMutation({
    mutationFn: async ({ userId, isActive }: { userId: string; isActive: boolean }) =>
      api.patch(`/users/${userId}`, { is_active: isActive }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["users-dataset"] });
      queryClient.invalidateQueries({ queryKey: ["session-context"] });
    },
    onError: () => toast.error("Nao foi possivel atualizar o status do usuario."),
  });

  const deleteMutation = useMutation({
    mutationFn: async (userId: string) => api.delete(`/users/${userId}`),
    onSuccess: () => {
      toast.success("Usuario excluido com sucesso.");
      setDeleteConfirmOpen(false);
      setEditDrawerOpen(false);
      setSelectedUser(null);
      queryClient.invalidateQueries({ queryKey: ["users-dataset"] });
      queryClient.invalidateQueries({ queryKey: ["session-context"] });
    },
    onError: () => toast.error("Nao foi possivel excluir o usuario."),
  });

  if (usersQuery.isLoading) return <LoadingState message="Carregando usuarios..." />;
  if (usersQuery.isError || !usersQuery.data) return <ErrorState message="Nao foi possivel carregar usuarios." />;

  const unitsById = new Map(usersQuery.data.units.map((unit) => [unit.id, unit.name]));
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
    .map((user) => {
      const permissions = normalizePagePermissions(user.page_permissions, user.roles);
      return {
        ...user,
        resolved_permissions: permissions,
        visible_pages: countVisiblePages(permissions),
        role_label: ROLE_LABELS[user.roles?.[0] ?? ""] ?? "Perfil customizado",
        unit_name: user.unit_id ? unitsById.get(user.unit_id) ?? "Unidade nao identificada" : "Visao geral",
        last_access: user.last_login_at ?? user.created_at,
      };
    });

  const validateForm = (isCreate: boolean) => {
    if (!formName.trim()) {
      toast.error("Preencha o nome do usuario.");
      return false;
    }
    if (isCreate && (!formEmail.trim() || !formPassword.trim())) {
      toast.error("Preencha e-mail e senha temporaria.");
      return false;
    }
    if (isCreate && formPassword.trim().length < 10) {
      toast.error("A senha temporaria precisa ter pelo menos 10 caracteres.");
      return false;
    }
    if (UNIT_REQUIRED_ROLES.has(formRole) && !formUnitId) {
      toast.error("Gerente e recepcao precisam estar vinculados a uma unidade.");
      return false;
    }
    if (countVisiblePages(formPermissions) === 0) {
      toast.error("Libere pelo menos uma pagina para o usuario.");
      return false;
    }
    return true;
  };

  return (
    <div className="space-y-4">
      <PageHeader
        eyebrow="Acesso e governanca"
        title="Usuarios e permissoes"
        description="Controle de unidade, paginas visiveis, acoes por pagina e modo de operacao em tela cheia."
        actions={canCreateUsers ? (
          <Button
            className="gap-2"
            onClick={() => {
              setSelectedUser(null);
              resetForm();
              setCreateDrawerOpen(true);
            }}
          >
            <UserPlus size={16} />
            Novo usuario
          </Button>
        ) : undefined}
      />

      <div className="grid gap-4 xl:grid-cols-[1.3fr_0.9fr]">
        <Card className="border-stone-200">
          <CardHeader>
            <CardTitle>Visao geral das permissoes</CardTitle>
          </CardHeader>
          <CardContent className="grid gap-3 md:grid-cols-3">
            <div className="rounded-2xl border border-stone-200 bg-stone-50 p-4">
              <p className="text-xs font-semibold uppercase tracking-wide text-stone-500">Usuarios ativos</p>
              <p className="mt-2 text-3xl font-bold text-stone-900">
                {rows.filter((item) => item.is_active).length}
              </p>
            </div>
            <div className="rounded-2xl border border-stone-200 bg-stone-50 p-4">
              <p className="text-xs font-semibold uppercase tracking-wide text-stone-500">Modo tela cheia</p>
              <p className="mt-2 text-3xl font-bold text-stone-900">
                {rows.filter((item) => item.force_fullscreen_mode).length}
              </p>
            </div>
            <div className="rounded-2xl border border-stone-200 bg-stone-50 p-4">
              <p className="text-xs font-semibold uppercase tracking-wide text-stone-500">Paginas principais</p>
              <p className="mt-2 text-sm text-stone-700">
                WhatsApp, Agenda e Pacientes aparecem no topo. O resto entra no menu horizontal se liberado.
              </p>
            </div>
          </CardContent>
        </Card>

        {canCreateUsers ? (
        <Card className="border-stone-200">
          <CardHeader>
            <CardTitle>Convidar usuario</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
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
              className="gap-2"
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
          </CardContent>
        </Card>
        ) : null}
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
        title="Usuarios"
        rows={rows}
        getRowId={(item) => item.id}
        searchBy={(item) => `${item.full_name} ${item.email} ${item.role_label}`}
        columns={[
          {
            key: "nome",
            label: "Usuario",
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
            key: "paginas",
            label: "Paginas",
            render: (item) => (
              <div>
                <p className="text-sm font-semibold text-stone-800">{item.visible_pages} liberada(s)</p>
                <p className="text-xs text-stone-500">
                  {item.force_fullscreen_mode ? "Login direto em tela cheia" : "Modo normal"}
                </p>
              </div>
            ),
          },
          {
            key: "status",
            label: "Status",
            render: (item) => <StatusBadge value={item.is_active ? "ativo" : "inativo"} />,
          },
          {
            key: "ultimo_acesso",
            label: "Ultimo acesso",
            render: (item) => formatDateTimeBR(item.last_access),
          },
          {
            key: "acoes",
            label: "Acoes",
            render: (item) => (
              <div className="flex flex-wrap gap-2">
                <Button
                  variant="outline"
                  className="h-8 gap-1 px-2 text-xs"
                  onClick={() => {
                    setSelectedUser(item);
                    populateFormFromUser(item);
                    setDeleteConfirmOpen(false);
                    setEditDrawerOpen(true);
                  }}
                  disabled={!canEditUsers}
                >
                  <Pencil size={12} />
                  Editar
                </Button>
                <Button
                  variant={item.is_active ? "destructive" : "outline"}
                  className="h-8 px-2 text-xs"
                  disabled={!canEditUsers}
                  onClick={() =>
                    toggleActiveMutation.mutate(
                      { userId: item.id, isActive: !item.is_active },
                      {
                        onSuccess: () => {
                          toast.success(item.is_active ? "Usuario desativado." : "Usuario ativado.");
                        },
                      },
                    )
                  }
                >
                  {item.is_active ? "Desativar" : "Ativar"}
                </Button>
                <Button
                  variant="destructive"
                  className="h-8 gap-1 px-2 text-xs"
                  onClick={() => {
                    setSelectedUser(item);
                    populateFormFromUser(item);
                    setDeleteConfirmOpen(true);
                    setEditDrawerOpen(true);
                  }}
                  disabled={!canDeleteUsers || sessionQuery.data?.id === item.id}
                >
                  <Trash2 size={12} />
                  Excluir
                </Button>
              </div>
            ),
          },
        ]}
        emptyTitle="Sem usuarios"
        emptyDescription="Nenhum usuario encontrado com os filtros atuais."
      />

      <RightDrawer
        open={createDrawerOpen}
        onOpenChange={(open) => {
          setCreateDrawerOpen(open);
          if (!open) resetForm();
        }}
        title="Novo usuario"
        description="Escolha unidade, perfil, paginas liberadas, acoes disponiveis e modo de tela cheia."
      >
        {canCreateUsers ? (
        <Card className="border-stone-200">
          <CardContent className="space-y-4 p-4">
            <div className="grid gap-3 sm:grid-cols-2">
              <Input placeholder="Nome completo" value={formName} onChange={(event) => setFormName(event.target.value)} />
              <Input placeholder="E-mail" type="email" value={formEmail} onChange={(event) => setFormEmail(event.target.value)} />
            </div>
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="space-y-1.5">
                <label className="field-label">Senha temporaria</label>
                <Input
                  placeholder="Minimo de 10 caracteres"
                  type="password"
                  value={formPassword}
                  onChange={(event) => setFormPassword(event.target.value)}
                />
                <p className="field-help">Essa senha inicial precisa ter pelo menos 10 caracteres.</p>
              </div>
              <Input placeholder="Telefone (opcional)" value={formPhone} onChange={(event) => setFormPhone(event.target.value)} />
            </div>
            <div className="grid gap-3 sm:grid-cols-2">
              <select
                className="h-10 rounded-md border border-stone-300 bg-white px-3 text-sm"
                value={formUnitId}
                onChange={(event) => setFormUnitId(event.target.value)}
              >
                <option value="">Visao geral / sem unidade</option>
                {usersQuery.data.units.map((unit) => (
                  <option key={unit.id} value={unit.id}>
                    {unit.name}
                  </option>
                ))}
              </select>
              <select
                className="h-10 rounded-md border border-stone-300 bg-white px-3 text-sm"
                value={formRole}
                onChange={(event) => setFormRole(event.target.value)}
              >
                {ROLE_OPTIONS.map((option) => (
                  <option key={option} value={option}>
                    {ROLE_LABELS[option] ?? option}
                  </option>
                ))}
              </select>
            </div>

            <div className="rounded-2xl border border-stone-200 bg-stone-50 p-4">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <p className="text-sm font-semibold text-stone-900">Aplicar perfil base</p>
                  <p className="text-xs text-stone-500">
                    Isso preenche a matriz com um ponto de partida. Depois voce pode ajustar pagina por pagina.
                  </p>
                </div>
                <Button
                  variant="outline"
                  className="gap-2"
                  onClick={() => setFormPermissions(buildDefaultPagePermissionsForRole(formRole))}
                >
                  <ShieldCheck size={14} />
                  Aplicar padrao do perfil
                </Button>
              </div>
            </div>

            <label className="flex items-start gap-3 rounded-2xl border border-stone-200 bg-stone-50 p-4 text-sm text-stone-700">
              <input
                type="checkbox"
                className="mt-1"
                checked={formForceFullscreen}
                onChange={(event) => setFormForceFullscreen(event.target.checked)}
              />
              <span>
                <span className="block font-semibold text-stone-900">Entrar direto no workspace em tela cheia</span>
                <span className="mt-1 block text-xs text-stone-500">
                  Quando esse usuario fizer login, ele abre no modo operacional em tela cheia. Se sair da tela cheia, sera deslogado automaticamente.
                </span>
              </span>
            </label>

            <PermissionMatrix value={formPermissions} onChange={setFormPermissions} disabled={!canCreateUsers} />

            <div className="flex justify-end gap-2">
              <Button
                variant="outline"
                onClick={() => {
                  setCreateDrawerOpen(false);
                  resetForm();
                }}
              >
                Cancelar
              </Button>
              <Button
                onClick={() => {
                  if (!validateForm(true)) return;
                  createMutation.mutate();
                }}
                disabled={createMutation.isPending}
              >
                {createMutation.isPending ? "Criando..." : "Criar usuario"}
              </Button>
            </div>
          </CardContent>
        </Card>
        ) : (
          <p className="text-sm text-stone-500">Seu perfil atual nao pode criar usuarios.</p>
        )}
      </RightDrawer>

      <RightDrawer
        open={editDrawerOpen}
        onOpenChange={(open) => {
          setEditDrawerOpen(open);
          if (!open) {
            setDeleteConfirmOpen(false);
            setSelectedUser(null);
          }
        }}
        title={selectedUser ? `Editar ${selectedUser.full_name}` : "Editar usuario"}
        description="Atualize perfil, unidade, paginas permitidas, acoes e o modo de tela cheia."
      >
        {selectedUser ? (
          <Card className="border-stone-200">
            <CardContent className="space-y-4 p-4">
              <div className="grid gap-3 sm:grid-cols-2">
                <Input placeholder="Nome completo" value={formName} disabled={!canEditUsers} onChange={(event) => setFormName(event.target.value)} />
                <div className="flex items-center rounded-lg border border-stone-200 bg-stone-50 px-3 text-sm text-stone-600">
                  {formEmail}
                </div>
              </div>
              <div className="grid gap-3 sm:grid-cols-2">
                <Input placeholder="Telefone (opcional)" value={formPhone} disabled={!canEditUsers} onChange={(event) => setFormPhone(event.target.value)} />
                <select
                  className="h-10 rounded-md border border-stone-300 bg-white px-3 text-sm"
                  value={formUnitId}
                  disabled={!canEditUsers}
                  onChange={(event) => setFormUnitId(event.target.value)}
                >
                  <option value="">Visao geral / sem unidade</option>
                  {usersQuery.data.units.map((unit) => (
                    <option key={unit.id} value={unit.id}>
                      {unit.name}
                    </option>
                  ))}
                </select>
              </div>
              <div className="grid gap-3 sm:grid-cols-2">
                <select
                  className="h-10 rounded-md border border-stone-300 bg-white px-3 text-sm"
                  value={formRole}
                  disabled={!canEditUsers}
                  onChange={(event) => setFormRole(event.target.value)}
                >
                  {ROLE_OPTIONS.map((option) => (
                    <option key={option} value={option}>
                      {ROLE_LABELS[option] ?? option}
                    </option>
                  ))}
                </select>
                <div className="flex items-center rounded-lg border border-stone-200 bg-stone-50 px-3 text-sm text-stone-600">
                  Ultimo acesso: {formatDateTimeBR(selectedUser.last_login_at ?? selectedUser.created_at)}
                </div>
              </div>

              <label className="flex items-start gap-3 rounded-2xl border border-stone-200 bg-stone-50 p-4 text-sm text-stone-700">
                <input
                  type="checkbox"
                  className="mt-1"
                  checked={formForceFullscreen}
                  disabled={!canEditUsers}
                  onChange={(event) => setFormForceFullscreen(event.target.checked)}
                />
                  <span>
                    <span className="block font-semibold text-stone-900">Modo operacional em tela cheia</span>
                    <span className="mt-1 block text-xs text-stone-500">
                      O usuario entra direto no workspace em tela cheia, com menu horizontal e um modulo por vez ocupando toda a area.
                    </span>
                  </span>
                </label>

              <div className="rounded-2xl border border-stone-200 bg-stone-50 p-4">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <p className="text-sm font-semibold text-stone-900">Aplicar perfil base</p>
                    <p className="text-xs text-stone-500">
                      Recarrega as permissoes sugeridas para esse perfil e depois voce pode refinar.
                    </p>
                  </div>
                  <Button
                    variant="outline"
                    className="gap-2"
                    disabled={!canEditUsers}
                    onClick={() => setFormPermissions(buildDefaultPagePermissionsForRole(formRole))}
                  >
                    <ShieldCheck size={14} />
                    Aplicar padrao do perfil
                  </Button>
                </div>
              </div>

              {!canEditUsers ? (
                <div className="rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
                  Seu perfil atual pode visualizar esse usuario, mas nao pode alterar permissoes ou dados do cadastro.
                </div>
              ) : null}

              <PermissionMatrix value={formPermissions} onChange={setFormPermissions} disabled={!canEditUsers} />

              {deleteConfirmOpen ? (
                <Card className="border-rose-200 bg-rose-50">
                  <CardContent className="space-y-3 p-4">
                    <div>
                      <p className="text-sm font-semibold text-rose-900">Confirmar exclusao do usuario</p>
                      <p className="text-sm text-rose-700">
                        Essa conta sera removida do tenant. Se preferir, voce tambem pode apenas desativar o usuario.
                      </p>
                    </div>
                    <div className="flex flex-wrap justify-end gap-2">
                      <Button variant="outline" onClick={() => setDeleteConfirmOpen(false)}>
                        Nao
                      </Button>
                      <Button
                        variant="destructive"
                        onClick={() => deleteMutation.mutate(selectedUser.id)}
                        disabled={deleteMutation.isPending || sessionQuery.data?.id === selectedUser.id}
                      >
                        {deleteMutation.isPending ? "Excluindo..." : "Sim, excluir usuario"}
                      </Button>
                    </div>
                  </CardContent>
                </Card>
              ) : null}

              <div className="flex flex-wrap justify-between gap-2">
                <div className="flex flex-wrap gap-2">
                  <Button
                    variant="destructive"
                    className="gap-2"
                          onClick={() => setDeleteConfirmOpen(true)}
                    disabled={!canDeleteUsers || sessionQuery.data?.id === selectedUser.id}
                  >
                    <Trash2 size={14} />
                    Excluir usuario
                  </Button>
                  {sessionQuery.data?.id === selectedUser.id ? (
                    <span className="self-center text-xs text-stone-500">Seu proprio usuario nao pode ser excluido.</span>
                  ) : null}
                </div>
                <div className="flex flex-wrap gap-2">
                  <Button
                    variant="outline"
                    onClick={() => {
                      setEditDrawerOpen(false);
                      setDeleteConfirmOpen(false);
                      setSelectedUser(null);
                    }}
                  >
                    <X size={14} />
                    Fechar
                  </Button>
                  <Button
                    onClick={() => {
                      if (!selectedUser) return;
                      if (!validateForm(false)) return;
                      updateMutation.mutate(selectedUser.id);
                    }}
                    disabled={updateMutation.isPending || !canEditUsers}
                  >
                    {updateMutation.isPending ? "Salvando..." : "Salvar alteracoes"}
                  </Button>
                </div>
              </div>
            </CardContent>
          </Card>
        ) : (
          <p className="text-sm text-stone-500">Selecione um usuario para editar.</p>
        )}
      </RightDrawer>
    </div>
  );
}

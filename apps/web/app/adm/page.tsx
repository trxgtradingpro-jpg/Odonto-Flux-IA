"use client";

import { type ReactNode, useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Activity,
  ArrowRight,
  BarChart3,
  Building2,
  CalendarClock,
  CheckCircle2,
  Clipboard,
  Eye,
  FileText,
  Flame,
  KeyRound,
  Lock,
  MessageSquareText,
  PhoneCall,
  Plus,
  RefreshCw,
  Search,
  Send,
  ShieldCheck,
  SlidersHorizontal,
  UserRound,
} from "lucide-react";
import { toast } from "sonner";

import PlatformWhatsAppSettings from "@/components/adm/platform-whatsapp-settings";
import { EmptyState } from "@/components/premium";
import { api } from "@/lib/api";
import { clearAdminAccessToken, getAdminAccessToken, setAdminAccessToken } from "@/lib/auth";
import { BRAND_MONOGRAM, BRAND_NAME, BRAND_SALES_TEAM, BRAND_TAGLINE } from "@/lib/brand";
import { formatDateTimeBR, numberFormatter } from "@/lib/formatters";
import { Badge, Button, Card, CardContent, CardHeader, CardTitle, Input, cn } from "@odontoflux/ui";

type Prospect = {
  id: string;
  clinic_name: string;
  owner_name?: string | null;
  manager_name?: string | null;
  phone?: string | null;
  whatsapp_phone?: string | null;
  email?: string | null;
  website?: string | null;
  city?: string | null;
  state?: string | null;
  main_address?: string | null;
  notes: string;
  lead_source?: string | null;
  first_contact_channel?: string | null;
  first_contact_at?: string | null;
  uses_whatsapp_heavily: boolean;
  estimated_volume?: number | null;
  main_pain?: string | null;
  score: number;
  temperature: string;
  status: string;
  tags: string[];
  test_phone_number?: string | null;
  do_not_contact: boolean;
  demo_tenant_id?: string | null;
  demo_user_id?: string | null;
  demo_login_email?: string | null;
  demo_sent_at?: string | null;
  demo_first_login_at?: string | null;
  demo_last_login_at?: string | null;
  demo_status: string;
  demo_expires_at?: string | null;
  demo_checklist: Record<string, boolean>;
  last_activity_at?: string | null;
  score_explanation: { points?: Record<string, number>; event_counts?: Record<string, number>; sessions?: number };
  proposal_snapshot: Record<string, unknown>;
  roi_inputs: Record<string, unknown>;
  created_at: string;
  updated_at: string;
  units: Array<{ id: string; unit_name: string; address: string; phone?: string | null; email?: string | null; is_primary: boolean }>;
  services: Array<{ id: string; service_name: string; category?: string | null; duration_minutes: number; price_range?: string | null; description: string }>;
};

type Overview = {
  total_prospects: number;
  demos_created: number;
  demos_accessed: number;
  hot_leads: number;
  meetings_scheduled: number;
  won: number;
  recent_activity: TimelineEvent[];
};

type TimelineEvent = {
  id: string;
  event_type: string;
  event_label: string;
  actor_type: string;
  payload: Record<string, unknown>;
  created_at: string;
};

type ActivityEvent = {
  id: string;
  event_name: string;
  page_path?: string | null;
  session_id?: string | null;
  payload: Record<string, unknown>;
  occurred_at: string;
};

type OutreachResult = {
  prospect: Prospect;
  step: "reception_intro" | "decision_maker_pitch" | "video_followup" | string;
  destination: string;
  message_text: string;
  demo_login_url?: string | null;
  video_url?: string | null;
  sender_tenant_id: string;
  conversation_id: string;
  outbound_message_id: string;
};

type OutreachSnapshot = {
  automation_active?: boolean;
  automation_mode?: string | null;
  auto_progress?: boolean;
  auto_send_video_after_pitch?: boolean;
  automation_started_at?: string | null;
  automation_completed_at?: string | null;
  automation_stopped_at?: string | null;
  automation_stop_reason?: string | null;
  last_step?: string | null;
  last_sent_at?: string | null;
  last_reply_at?: string | null;
  last_reply_preview?: string | null;
};

type OutreachLabTurn = {
  id: string;
  role: "odontoflux" | "clinic_virtual" | "system" | string;
  label: string;
  text: string;
  step?: string | null;
  meta?: Record<string, unknown>;
};

type OutreachLabLastRun = {
  scenario?: string | null;
  scenario_label?: string | null;
  generated_at?: string | null;
  converted?: boolean;
  outcome?: string | null;
  recommendation?: string | null;
  demo_login_url?: string | null;
  video_url?: string | null;
  metrics?: Record<string, unknown>;
  transcript?: OutreachLabTurn[];
};

type OutreachLabSnapshot = {
  last_run_at?: string | null;
  last_scenario?: string | null;
  last_outcome?: string | null;
  last_converted?: boolean;
  last_run?: OutreachLabLastRun | null;
  scenario_stats?: Record<string, { runs?: number; conversions?: number; last_outcome?: string | null; last_run_at?: string | null }>;
};

type OutreachLabResult = {
  prospect: Prospect;
  scenario: string;
  scenario_label: string;
  status: string;
  outcome: string;
  converted: boolean;
  recommendation?: string | null;
  demo_login_url?: string | null;
  video_url?: string | null;
  transcript: OutreachLabTurn[];
  metrics: Record<string, unknown>;
};

const STATUS_OPTIONS = [
  "novo",
  "pesquisado",
  "contato_iniciado",
  "respondeu",
  "decisor_identificado",
  "demo_criada",
  "demo_enviada",
  "demo_acessada",
  "testou_whatsapp",
  "visitou_agenda",
  "configurou_dados",
  "followup",
  "reuniao_marcada",
  "proposta_enviada",
  "negociacao",
  "fechado_ganho",
  "fechado_perdido",
];

const PLAYBOOKS = [
  {
    title: "Ligacao inicial",
    text: "Oi, tudo bem? Estou falando porque montei uma demonstracao rapida de como a recepcao da clinica pode organizar WhatsApp, agenda e retornos em um fluxo unico. Posso te mostrar em 7 minutos?",
  },
  {
    title: "WhatsApp curto",
    text: `Oi! Vi que a clinica atende bastante pelo WhatsApp. Eu consigo te mostrar uma demo personalizada da ${BRAND_NAME} com IA, agenda e recuperacao de pacientes. Posso te enviar?`,
  },
  {
    title: "Follow-up apos acesso",
    text: "Vi que voce acessou a demonstracao. A parte mais importante e testar WhatsApp e Agenda, porque ali aparece onde a recepcao ganha tempo. Quer que eu te guie rapidinho?",
  },
  {
    title: "Ja tenho sistema",
    text: "Perfeito. A ideia nao e trocar uma agenda por outra. O ponto e organizar o caminho inteiro: WhatsApp, recepcao, agendamento, comparecimento e retorno.",
  },
];

const OUTREACH_LAB_SCENARIOS = [
  { value: "manager_interested", label: "Gerente pede reuniao" },
  { value: "asks_price", label: "Gerente pede preco" },
  { value: "already_has_system", label: "Ja tem sistema" },
  { value: "reception_blocks", label: "Recepcao bloqueia" },
] as const;

type AdmSection = "crm" | "whatsapp";

function humanize(value: string) {
  return value.replace(/_/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function getOutreachSnapshot(prospect: Prospect): OutreachSnapshot {
  const raw = prospect.proposal_snapshot?.outreach;
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return {};
  return raw as OutreachSnapshot;
}

function getOutreachLabSnapshot(prospect: Prospect): OutreachLabSnapshot {
  const raw = prospect.proposal_snapshot?.outreach_lab;
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return {};
  return raw as OutreachLabSnapshot;
}

function outreachAutomationLabel(snapshot: OutreachSnapshot) {
  if (snapshot.automation_active) return "Automacao ativa";
  if (snapshot.automation_completed_at) return "Fluxo inicial concluido";
  if (snapshot.automation_stop_reason === "video_url_missing") return "Parou sem video";
  if (snapshot.automation_stopped_at) return "Automacao pausada";
  return "Pronto para iniciar";
}

function temperatureClass(value: string) {
  if (value === "muito_quente") return "bg-red-100 text-red-700";
  if (value === "quente") return "bg-orange-100 text-orange-700";
  if (value === "morno") return "bg-amber-100 text-amber-800";
  return "bg-stone-200 text-stone-700";
}

function statusClass(value: string) {
  if (["fechado_ganho", "demo_acessada", "testou_whatsapp"].includes(value)) return "bg-emerald-100 text-emerald-700";
  if (["negociacao", "proposta_enviada", "reuniao_marcada"].includes(value)) return "bg-blue-100 text-blue-700";
  if (["fechado_perdido"].includes(value)) return "bg-rose-100 text-rose-700";
  return "bg-stone-200 text-stone-700";
}

function sessionId() {
  if (typeof window === "undefined") return "adm-session";
  const key = "odontoflux_adm_session_id";
  const current = window.sessionStorage.getItem(key);
  if (current) return current;
  const generated = crypto.randomUUID();
  window.sessionStorage.setItem(key, generated);
  return generated;
}

function LoginPanel({ onLogged }: { onLogged: (forceChange: boolean) => void }) {
  const [email, setEmail] = useState("netmultiverso@gmail.com");
  const [password, setPassword] = useState("Ia.123456789");

  const loginMutation = useMutation({
    mutationFn: async () => (await api.post("/admin/auth/login", { email, password })).data,
    onSuccess: (data) => {
      setAdminAccessToken(data.access_token, data.refresh_token);
      toast.success(data.force_password_change ? "Troque a senha inicial para continuar." : "Acesso administrativo liberado.");
      onLogged(Boolean(data.force_password_change));
    },
    onError: () => toast.error("Nao foi possivel entrar no /adm."),
  });

  return (
    <main className="grid min-h-screen place-items-center bg-stone-950 px-4 py-10 text-white">
      <div className="w-full max-w-md">
        <div className="mb-6 flex items-center gap-3">
          <div className="grid h-11 w-11 place-items-center rounded-lg bg-white text-sm font-black text-stone-950">{BRAND_MONOGRAM}</div>
          <div>
            <p className="text-xs font-semibold uppercase tracking-wide text-white/45">Admin comercial</p>
            <h1 className="text-xl font-bold">{BRAND_NAME} /adm</h1>
          </div>
        </div>
        <Card className="border-white/10 bg-white text-stone-950">
          <CardHeader>
            <CardTitle>Entrar no CRM de demos</CardTitle>
            <p className="text-sm text-stone-600">{BRAND_TAGLINE}</p>
          </CardHeader>
          <CardContent>
            <form
              className="space-y-4"
              onSubmit={(event) => {
                event.preventDefault();
                loginMutation.mutate();
              }}
            >
              <div className="space-y-1">
                <label className="text-sm font-medium">E-mail</label>
                <Input type="email" value={email} onChange={(event) => setEmail(event.target.value)} />
              </div>
              <div className="space-y-1">
                <label className="text-sm font-medium">Senha</label>
                <Input type="password" value={password} onChange={(event) => setPassword(event.target.value)} />
              </div>
              <Button className="w-full" disabled={loginMutation.isPending}>
                <Lock size={16} />
                {loginMutation.isPending ? "Entrando..." : "Entrar"}
              </Button>
            </form>
          </CardContent>
        </Card>
      </div>
    </main>
  );
}

function ChangePasswordPanel({ onDone }: { onDone: () => void }) {
  const [currentPassword, setCurrentPassword] = useState("Ia.123456789");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");

  const mutation = useMutation({
    mutationFn: async () =>
      (await api.post("/admin/auth/change-initial-password", { current_password: currentPassword, new_password: newPassword })).data,
    onSuccess: () => {
      toast.success("Senha inicial trocada. Pode operar o /adm.");
      onDone();
    },
    onError: (error: unknown) => {
      const response = (error as { response?: { data?: { error?: { message?: string; details?: { rules?: string[] } } } } }).response;
      const message = response?.data?.error?.message ?? "Nao foi possivel trocar a senha inicial.";
      const rules = response?.data?.error?.details?.rules;
      toast.error(rules?.length ? `${message}: ${rules.join(", ")}` : message);
    },
  });

  return (
    <main className="grid min-h-screen place-items-center bg-stone-950 px-4 py-10 text-white">
      <Card className="w-full max-w-md border-white/10 bg-white text-stone-950">
        <CardHeader>
          <CardTitle>Trocar senha inicial</CardTitle>
          <p className="text-sm text-stone-600">Para liberar o painel, defina uma senha propria antes de continuar.</p>
        </CardHeader>
        <CardContent>
          <form
            className="space-y-4"
            onSubmit={(event) => {
              event.preventDefault();
              if (newPassword !== confirmPassword) {
                toast.error("A confirmacao da senha nao confere.");
                return;
              }
              mutation.mutate();
            }}
          >
            <div className="space-y-1">
              <label className="text-sm font-medium">Senha inicial recebida</label>
              <Input type="password" value={currentPassword} onChange={(event) => setCurrentPassword(event.target.value)} placeholder="Senha atual" />
            </div>
            <div className="space-y-1">
              <label className="text-sm font-medium">Nova senha</label>
              <Input type="password" value={newPassword} onChange={(event) => setNewPassword(event.target.value)} placeholder="Nova senha forte" />
            </div>
            <div className="space-y-1">
              <label className="text-sm font-medium">Confirmar nova senha</label>
              <Input type="password" value={confirmPassword} onChange={(event) => setConfirmPassword(event.target.value)} placeholder="Repita a nova senha" />
            </div>
            <p className="text-xs leading-5 text-stone-500">
              Use ao menos 10 caracteres, com letra maiuscula, minuscula, numero e simbolo. A senha inicial precisa ser exatamente a senha temporaria do login.
            </p>
            <Button className="w-full" disabled={mutation.isPending}>
              <KeyRound size={16} />
              {mutation.isPending ? "Atualizando..." : "Atualizar senha"}
            </Button>
          </form>
        </CardContent>
      </Card>
    </main>
  );
}

function CreateProspectForm({ onCreated }: { onCreated: (prospect: Prospect) => void }) {
  const [open, setOpen] = useState(false);
  const [clinicName, setClinicName] = useState("");
  const [ownerName, setOwnerName] = useState("");
  const [whatsappPhone, setWhatsappPhone] = useState("");
  const [email, setEmail] = useState("");
  const [website, setWebsite] = useState("");
  const [city, setCity] = useState("");
  const [state, setState] = useState("");
  const [address, setAddress] = useState("");
  const [mainPain, setMainPain] = useState("");
  const [leadSource, setLeadSource] = useState("Google/Maps manual");
  const [testPhoneNumber, setTestPhoneNumber] = useState("");
  const [services, setServices] = useState("Consulta inicial, Avaliacao clinica, Retorno");
  const [notes, setNotes] = useState("");

  const mutation = useMutation({
    mutationFn: async () => {
      const serviceItems = services
        .split(",")
        .map((item) => item.trim())
        .filter(Boolean)
        .map((service_name) => ({ service_name, duration_minutes: service_name.toLowerCase().includes("clareamento") ? 75 : 60 }));
      return (
        await api.post("/admin/prospects", {
          clinic_name: clinicName,
          owner_name: ownerName || null,
          whatsapp_phone: whatsappPhone || null,
          email: email || null,
          website: website || null,
          city: city || null,
          state: state || null,
          main_address: address || null,
          main_pain: mainPain || null,
          lead_source: leadSource || "prospeccao_manual",
          first_contact_channel: "ligacao_whatsapp_manual",
          uses_whatsapp_heavily: true,
          test_phone_number: testPhoneNumber || null,
          notes,
          services: serviceItems,
        })
      ).data as Prospect;
    },
    onSuccess: (data) => {
      toast.success("Clinica cadastrada.");
      setOpen(false);
      setClinicName("");
      setOwnerName("");
      setWhatsappPhone("");
      setEmail("");
      setWebsite("");
      setCity("");
      setState("");
      setAddress("");
      setMainPain("");
      setLeadSource("Google/Maps manual");
      setTestPhoneNumber("");
      setNotes("");
      onCreated(data);
    },
    onError: () => toast.error("Nao foi possivel cadastrar a clinica."),
  });

  if (!open) {
    return (
      <Card className="overflow-hidden border-stone-200 bg-white">
        <CardContent className="p-0">
          <div className="grid gap-0 lg:grid-cols-[1.15fr_0.85fr]">
            <div className="space-y-5 p-6">
              <div className="inline-flex items-center gap-2 rounded-full bg-emerald-50 px-3 py-1 text-xs font-bold uppercase tracking-wide text-emerald-700">
                <ShieldCheck size={14} />
                CRM interno de vendas
              </div>
              <div>
                <h2 className="text-2xl font-black tracking-tight text-stone-950">Cadastrar clinica prospectada</h2>
                <p className="mt-2 max-w-2xl text-sm leading-6 text-stone-600">
                  Salve a clinica que respondeu ao primeiro contato manual, registre dores comerciais e prepare a base para gerar uma demo isolada com dados criveis.
                </p>
              </div>
              <div className="grid gap-3 sm:grid-cols-3">
                <MiniStep number="1" title="Contato" text="Nome, WhatsApp, decisor e origem do lead." />
                <MiniStep number="2" title="Contexto" text="Dor principal, cidade, endereco e observacoes." />
                <MiniStep number="3" title="Demo" text="Servicos iniciais e numero de teste da clinica." />
              </div>
            </div>
            <div className="flex flex-col justify-between border-t border-stone-200 bg-stone-950 p-6 text-white lg:border-l lg:border-t-0">
              <div>
                <p className="text-xs font-bold uppercase tracking-[0.18em] text-emerald-300">Operacao rapida</p>
                <h3 className="mt-3 text-xl font-black">Comece com o essencial e refine depois.</h3>
                <p className="mt-2 text-sm leading-6 text-white/65">
                  O cadastro pode nascer simples. Depois voce adiciona unidades, servicos, notas, gera a demo e acompanha o comportamento no painel.
                </p>
              </div>
              <Button className="mt-6 w-full bg-emerald-500 text-stone-950 hover:bg-emerald-400" onClick={() => setOpen(true)}>
                <Plus size={16} />
                Abrir cadastro da clinica
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className="overflow-hidden border-stone-200 bg-white">
      <CardHeader className="border-b border-stone-200 bg-stone-50/80">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <div className="mb-2 inline-flex items-center gap-2 rounded-full bg-white px-3 py-1 text-xs font-bold uppercase tracking-wide text-stone-500 shadow-sm">
              <Building2 size={14} />
              Novo prospect
            </div>
            <CardTitle className="text-2xl">Cadastrar clinica prospectada</CardTitle>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-stone-600">
              Preencha o suficiente para a {BRAND_NAME} montar uma demo personalizada. Os campos principais ajudam o follow-up, o score comercial e o provisionamento da demo.
            </p>
          </div>
          <Button type="button" variant="outline" onClick={() => setOpen(false)}>
            Cancelar cadastro
          </Button>
        </div>
      </CardHeader>
      <CardContent>
        <form
          className="space-y-6 pt-6"
          onSubmit={(event) => {
            event.preventDefault();
            mutation.mutate();
          }}
        >
          <section className="rounded-2xl border border-stone-200 p-4">
            <SectionIntro
              title="1. Identificacao da clinica"
              text="Dados que aparecem no CRM e ajudam a reconhecer rapidamente quem e o decisor."
            />
            <div className="mt-4 grid gap-3 lg:grid-cols-4">
              <Field label="Nome da clinica" helper="Nome comercial usado no atendimento e na demo." className="lg:col-span-2">
                <Input required placeholder="Ex.: Clinica Sorriso Sul" value={clinicName} onChange={(event) => setClinicName(event.target.value)} />
              </Field>
              <Field label="Dono ou gerente" helper="Opcional, mas ajuda no follow-up.">
                <Input placeholder="Ex.: Dra. Mariana" value={ownerName} onChange={(event) => setOwnerName(event.target.value)} />
              </Field>
              <Field label="Origem do lead" helper="De onde voce encontrou essa clinica.">
                <Input value={leadSource} onChange={(event) => setLeadSource(event.target.value)} />
              </Field>
            </div>
          </section>

          <section className="rounded-2xl border border-stone-200 p-4">
            <SectionIntro
              title="2. Contato e localizacao"
              text="Use o WhatsApp ou telefone do primeiro contato manual. Nada aqui dispara mensagem automatica."
            />
            <div className="mt-4 grid gap-3 lg:grid-cols-4">
              <Field label="WhatsApp principal" helper="Numero usado para falar com a clinica.">
                <Input placeholder="(11) 99999-0000" value={whatsappPhone} onChange={(event) => setWhatsappPhone(event.target.value)} />
              </Field>
              <Field label="E-mail" helper="Opcional para proposta ou acesso futuro.">
                <Input type="email" placeholder="contato@clinica.com.br" value={email} onChange={(event) => setEmail(event.target.value)} />
              </Field>
              <Field label="Cidade" helper="Ajuda a segmentar a prospeccao.">
                <Input placeholder="Osasco" value={city} onChange={(event) => setCity(event.target.value)} />
              </Field>
              <Field label="Estado" helper="UF ou estado.">
                <Input placeholder="SP" value={state} onChange={(event) => setState(event.target.value.toUpperCase())} />
              </Field>
              <Field label="Site ou Instagram" helper="Referencia para revisar depois." className="lg:col-span-2">
                <Input placeholder="https://..." value={website} onChange={(event) => setWebsite(event.target.value)} />
              </Field>
              <Field label="Endereco principal" helper="Se preencher, a demo ja cria uma unidade principal." className="lg:col-span-2">
                <Input placeholder="Rua, numero, bairro" value={address} onChange={(event) => setAddress(event.target.value)} />
              </Field>
            </div>
          </section>

          <section className="rounded-2xl border border-stone-200 p-4">
            <SectionIntro
              title="3. Dor comercial e demo"
              text="Essas informacoes deixam o discurso e a demo mais proximos da realidade da clinica."
            />
            <div className="mt-4 grid gap-3 lg:grid-cols-4">
              <Field label="Principal dor percebida" helper="Ex.: perde paciente no WhatsApp, agenda baguncada, retorno esquecido." className="lg:col-span-2">
                <Input placeholder="WhatsApp desorganizado e perda de pacientes" value={mainPain} onChange={(event) => setMainPain(event.target.value)} />
              </Field>
              <Field label="Numero de teste" helper="Numero que o dono pode usar para testar o fluxo. Se informar sem DDI, assumimos Brasil. Se for internacional, informe com + ou 00.">
                <Input placeholder="(11) 98888-7777 ou +44 7786 004289" value={testPhoneNumber} onChange={(event) => setTestPhoneNumber(event.target.value)} />
              </Field>
              <Field label="Servicos da clinica" helper="Separe por virgula. A demo usa isso para equipe, agenda e IA." className="lg:col-span-4">
                <textarea
                  className="min-h-[92px] w-full rounded-xl border border-stone-300 bg-white px-4 py-3 text-sm outline-none transition focus:border-emerald-600 focus:ring-2 focus:ring-emerald-600/15"
                  value={services}
                  onChange={(event) => setServices(event.target.value)}
                />
              </Field>
              <Field label="Observacoes internas" helper="Notas para abordagem, objeções ou contexto da conversa." className="lg:col-span-4">
                <textarea
                  className="min-h-[104px] w-full rounded-xl border border-stone-300 bg-white px-4 py-3 text-sm outline-none transition focus:border-emerald-600 focus:ring-2 focus:ring-emerald-600/15"
                  placeholder="Ex.: respondeu pelo WhatsApp, quer falar com o gerente, ja usa outro sistema..."
                  value={notes}
                  onChange={(event) => setNotes(event.target.value)}
                />
              </Field>
            </div>
          </section>

          <div className="flex flex-col gap-3 rounded-2xl border border-emerald-100 bg-emerald-50 p-4 lg:flex-row lg:items-center lg:justify-between">
            <div>
              <p className="font-bold text-emerald-950">Depois de criar, selecione a clinica na tabela.</p>
              <p className="mt-1 text-sm text-emerald-800">Voce podera gerar a demo personalizada, copiar o acesso e acompanhar os eventos comerciais.</p>
            </div>
            <div className="flex gap-2">
              <Button type="button" variant="outline" onClick={() => setOpen(false)}>
                Fechar
              </Button>
              <Button disabled={mutation.isPending}>
                <ArrowRight size={16} />
                {mutation.isPending ? "Criando..." : "Criar prospect"}
              </Button>
            </div>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}

function MiniStep({ number, title, text }: { number: string; title: string; text: string }) {
  return (
    <div className="rounded-2xl border border-stone-200 bg-stone-50 p-4">
      <div className="mb-3 grid h-8 w-8 place-items-center rounded-full bg-stone-950 text-xs font-black text-white">{number}</div>
      <p className="font-bold text-stone-950">{title}</p>
      <p className="mt-1 text-xs leading-5 text-stone-600">{text}</p>
    </div>
  );
}

function SectionIntro({ title, text }: { title: string; text: string }) {
  return (
    <div>
      <h3 className="text-base font-black text-stone-950">{title}</h3>
      <p className="mt-1 text-sm leading-6 text-stone-600">{text}</p>
    </div>
  );
}

function Field({
  label,
  helper,
  className,
  children,
}: {
  label: string;
  helper: string;
  className?: string;
  children: ReactNode;
}) {
  return (
    <label className={cn("block space-y-2", className)}>
      <span className="text-xs font-bold uppercase tracking-wide text-stone-500">{label}</span>
      {children}
      <span className="block text-xs leading-5 text-stone-500">{helper}</span>
    </label>
  );
}

export default function AdmPage() {
  const queryClient = useQueryClient();
  const [hasToken, setHasToken] = useState(false);
  const [forcePasswordChange, setForcePasswordChange] = useState(false);
  const [activeSection, setActiveSection] = useState<AdmSection>("crm");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [lastDemoLink, setLastDemoLink] = useState("");

  useEffect(() => {
    setHasToken(Boolean(getAdminAccessToken()));
  }, []);

  const overviewQuery = useQuery<Overview>({
    queryKey: ["adm-overview"],
    queryFn: async () => (await api.get("/admin/prospects/overview")).data,
    enabled: hasToken && !forcePasswordChange,
    retry: false,
  });

  const prospectsQuery = useQuery<{ data: Prospect[]; total: number }>({
    queryKey: ["adm-prospects", statusFilter, search],
    queryFn: async () =>
      (
        await api.get("/admin/prospects", {
          params: { status: statusFilter || undefined, q: search || undefined, limit: 200, offset: 0 },
        })
      ).data,
    enabled: hasToken && !forcePasswordChange,
    retry: false,
  });

  const selectedProspect = useMemo(() => {
    const rows = prospectsQuery.data?.data ?? [];
    return rows.find((item) => item.id === selectedId) ?? rows[0] ?? null;
  }, [prospectsQuery.data?.data, selectedId]);

  useEffect(() => {
    if (!selectedId && selectedProspect) setSelectedId(selectedProspect.id);
  }, [selectedId, selectedProspect]);

  const timelineQuery = useQuery<TimelineEvent[]>({
    queryKey: ["adm-prospect-timeline", selectedProspect?.id],
    queryFn: async () => (await api.get(`/admin/prospects/${selectedProspect?.id}/timeline`)).data,
    enabled: hasToken && !forcePasswordChange && Boolean(selectedProspect?.id),
  });

  const activityQuery = useQuery<ActivityEvent[]>({
    queryKey: ["adm-prospect-activity", selectedProspect?.id],
    queryFn: async () => (await api.get(`/admin/prospects/${selectedProspect?.id}/activity`)).data,
    enabled: hasToken && !forcePasswordChange && Boolean(selectedProspect?.id),
  });

  const generateDemoMutation = useMutation({
    mutationFn: async (prospectId: string) => (await api.post(`/admin/prospects/${prospectId}/generate-demo`)).data,
    onSuccess: (data) => {
      setLastDemoLink(data.demo_login_url);
      navigator.clipboard?.writeText(data.demo_login_url);
      toast.success("Demo gerada e link copiado.");
      queryClient.invalidateQueries({ queryKey: ["adm-prospects"] });
      queryClient.invalidateQueries({ queryKey: ["adm-overview"] });
      queryClient.invalidateQueries({ queryKey: ["adm-prospect-timeline"] });
    },
    onError: () => toast.error("Nao foi possivel gerar a demo."),
  });

  const accessMutation = useMutation({
    mutationFn: async (prospectId: string) => (await api.post(`/admin/prospects/${prospectId}/send-demo-access`)).data,
    onSuccess: (data) => {
      setLastDemoLink(data.demo_login_url);
      navigator.clipboard?.writeText(data.demo_login_url);
      toast.success("Link de demo copiado.");
      queryClient.invalidateQueries({ queryKey: ["adm-prospects"] });
      queryClient.invalidateQueries({ queryKey: ["adm-prospect-timeline"] });
    },
    onError: () => toast.error("Nao foi possivel emitir acesso."),
  });

  const statusMutation = useMutation({
    mutationFn: async ({ prospectId, status }: { prospectId: string; status: string }) =>
      (await api.post(`/admin/prospects/${prospectId}/mark-status`, { status })).data,
    onSuccess: () => {
      toast.success("Status atualizado.");
      queryClient.invalidateQueries({ queryKey: ["adm-prospects"] });
      queryClient.invalidateQueries({ queryKey: ["adm-overview"] });
      queryClient.invalidateQueries({ queryKey: ["adm-prospect-timeline"] });
    },
  });

  const contactMutation = useMutation({
    mutationFn: async (prospectId: string) =>
      (
        await api.post(`/admin/prospects/${prospectId}/record-contact`, {
          channel: "ligacao_whatsapp_manual",
          summary: "Contato manual registrado pelo /adm.",
          next_step: "Enviar ou acompanhar demo personalizada.",
        })
      ).data,
    onSuccess: () => {
      toast.success("Contato registrado.");
      queryClient.invalidateQueries({ queryKey: ["adm-prospects"] });
      queryClient.invalidateQueries({ queryKey: ["adm-prospect-timeline"] });
    },
  });

  const outreachMutation = useMutation({
    mutationFn: async ({
      prospectId,
      step,
      recipientName,
    }: {
      prospectId: string;
      step: "reception_intro" | "decision_maker_pitch" | "video_followup";
      recipientName?: string | null;
    }) =>
      (
        await api.post<OutreachResult>(
          `/admin/prospects/${prospectId}/outreach`,
          {
            step,
            recipient_name: recipientName || null,
          },
        )
      ).data,
    onSuccess: (data) => {
      if (data.demo_login_url) {
        setLastDemoLink(data.demo_login_url);
        navigator.clipboard?.writeText(data.demo_login_url);
      }
      const label =
        data.step === "reception_intro"
          ? "Contato com recepção enviado."
          : data.step === "decision_maker_pitch"
            ? "Apresentação com demo enviada."
            : "Follow-up com vídeo enviado.";
      toast.success(label);
      queryClient.invalidateQueries({ queryKey: ["adm-prospects"] });
      queryClient.invalidateQueries({ queryKey: ["adm-overview"] });
      queryClient.invalidateQueries({ queryKey: ["adm-prospect-timeline"] });
    },
    onError: (error: unknown) => {
      const response = (error as { response?: { data?: { error?: { message?: string } } } }).response;
      toast.error(response?.data?.error?.message || "Nao foi possivel enviar o outreach comercial.");
    },
  });

  const automationMutation = useMutation({
    mutationFn: async (prospectId: string) =>
      (await api.post<OutreachResult>(`/admin/prospects/${prospectId}/outreach/automation/start`)).data,
    onSuccess: (data) => {
      if (data.demo_login_url) {
        setLastDemoLink(data.demo_login_url);
        navigator.clipboard?.writeText(data.demo_login_url);
      }
      toast.success("Automacao comercial iniciada. O WhatsApp vai acompanhar a resposta e avancar para pitch e video.");
      queryClient.invalidateQueries({ queryKey: ["adm-prospects"] });
      queryClient.invalidateQueries({ queryKey: ["adm-overview"] });
      queryClient.invalidateQueries({ queryKey: ["adm-prospect-timeline"] });
    },
    onError: (error: unknown) => {
      const response = (error as { response?: { data?: { error?: { message?: string } } } }).response;
      toast.error(response?.data?.error?.message || "Nao foi possivel iniciar a automacao comercial.");
    },
  });

  const outreachLabMutation = useMutation({
    mutationFn: async ({ prospectId, scenario }: { prospectId: string; scenario: string }) =>
      (
        await api.post<OutreachLabResult>(`/admin/prospects/${prospectId}/outreach/lab`, {
          scenario,
        })
      ).data,
    onSuccess: (data) => {
      if (data.demo_login_url) {
        setLastDemoLink(data.demo_login_url);
      }
      toast.success(
        data.converted
          ? "IA Lab comercial concluiu a simulacao com proximo passo claro."
          : "IA Lab comercial concluiu a simulacao e mostrou onde o fluxo trava.",
      );
      queryClient.invalidateQueries({ queryKey: ["adm-prospects"] });
      queryClient.invalidateQueries({ queryKey: ["adm-overview"] });
      queryClient.invalidateQueries({ queryKey: ["adm-prospect-timeline"] });
    },
    onError: (error: unknown) => {
      const response = (error as { response?: { data?: { error?: { message?: string } } } }).response;
      toast.error(response?.data?.error?.message || "Nao foi possivel rodar o IA Lab comercial.");
    },
  });

  if (!hasToken) {
    return <LoginPanel onLogged={(forceChange) => {
      setHasToken(true);
      setForcePasswordChange(forceChange);
    }} />;
  }

  if (forcePasswordChange) {
    return <ChangePasswordPanel onDone={() => setForcePasswordChange(false)} />;
  }

  const prospects = prospectsQuery.data?.data ?? [];
  const overview = overviewQuery.data;

  return (
    <main className="min-h-screen bg-stone-100 text-stone-950">
      <header className="sticky top-0 z-20 border-b border-stone-200 bg-white/95 backdrop-blur">
        <div className="mx-auto flex max-w-[1600px] items-center justify-between gap-4 px-5 py-3">
          <div className="flex items-center gap-3">
            <div className="grid h-10 w-10 place-items-center rounded-lg bg-stone-950 text-sm font-black text-white">OF</div>
            <div>
              <p className="text-xs font-semibold uppercase tracking-wide text-stone-500">Admin comercial</p>
              <h1 className="text-lg font-bold">
                {activeSection === "crm" ? "Prospeccao e demos personalizadas" : "WhatsApp oficial do sistema"}
              </h1>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              onClick={() => {
                clearAdminAccessToken();
                setHasToken(false);
              }}
            >
              Sair
            </Button>
          </div>
        </div>
      </header>

      <div className="mx-auto max-w-[1600px] space-y-4 px-5 py-5">
        <Card className="border-stone-200 bg-white">
          <CardContent className="flex flex-col gap-3 p-4 lg:flex-row lg:items-center lg:justify-between">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.18em] text-stone-500">Menu do /adm</p>
              <h2 className="mt-1 text-xl font-black text-stone-950">Escolha a area que quer operar agora</h2>
              <p className="mt-1 text-sm text-stone-600">
                Alterne entre o CRM comercial e a configuracao do WhatsApp oficial da plataforma sem sair da pagina administrativa.
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              <Button
                variant={activeSection === "crm" ? "default" : "outline"}
                className={cn(activeSection === "crm" && "bg-emerald-600 text-white hover:bg-emerald-500")}
                onClick={() => setActiveSection("crm")}
              >
                <Building2 size={16} />
                CRM comercial
              </Button>
              <Button
                variant={activeSection === "whatsapp" ? "default" : "outline"}
                className={cn(activeSection === "whatsapp" && "bg-emerald-600 text-white hover:bg-emerald-500")}
                onClick={() => setActiveSection("whatsapp")}
              >
                <SlidersHorizontal size={16} />
                WhatsApp do sistema
              </Button>
            </div>
          </CardContent>
        </Card>

        {activeSection === "whatsapp" ? <PlatformWhatsAppSettings /> : null}

        {activeSection === "crm" ? (
          <>
        <CreateProspectForm
          onCreated={(prospect) => {
            setSelectedId(prospect.id);
            queryClient.invalidateQueries({ queryKey: ["adm-prospects"] });
            queryClient.invalidateQueries({ queryKey: ["adm-overview"] });
          }}
        />

        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-6">
          <MetricCard icon={<Building2 size={18} />} label="Prospects" value={overview?.total_prospects ?? 0} />
          <MetricCard icon={<ShieldCheck size={18} />} label="Demos criadas" value={overview?.demos_created ?? 0} />
          <MetricCard icon={<Eye size={18} />} label="Demos acessadas" value={overview?.demos_accessed ?? 0} />
          <MetricCard icon={<Flame size={18} />} label="Quentes" value={overview?.hot_leads ?? 0} />
          <MetricCard icon={<CalendarClock size={18} />} label="Reunioes" value={overview?.meetings_scheduled ?? 0} />
          <MetricCard icon={<CheckCircle2 size={18} />} label="Ganhos" value={overview?.won ?? 0} />
        </div>

        <div className="grid gap-4 xl:grid-cols-[1fr_520px]">
          <section className="space-y-4">
            <div className="flex flex-col gap-3 rounded-lg border border-stone-200 bg-white p-3 lg:flex-row lg:items-center">
              <div className="relative flex-1">
                <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-stone-400" />
                <Input className="pl-9" placeholder="Buscar clinica, cidade ou telefone" value={search} onChange={(event) => setSearch(event.target.value)} />
              </div>
              <select
                className="h-10 rounded-lg border border-stone-200 bg-white px-3 text-sm"
                value={statusFilter}
                onChange={(event) => setStatusFilter(event.target.value)}
              >
                <option value="">Todos os status</option>
                {STATUS_OPTIONS.map((status) => (
                  <option key={status} value={status}>
                    {humanize(status)}
                  </option>
                ))}
              </select>
              <Button variant="outline" onClick={() => prospectsQuery.refetch()}>
                <RefreshCw size={16} />
                Atualizar
              </Button>
            </div>

            <div className="overflow-hidden rounded-lg border border-stone-200 bg-white">
              <div className="grid grid-cols-[1.3fr_0.8fr_0.8fr_0.7fr_0.9fr_0.8fr] gap-3 border-b border-stone-200 bg-stone-50 px-4 py-3 text-xs font-bold uppercase tracking-wide text-stone-500">
                <span>Clinica</span>
                <span>Status</span>
                <span>Temperatura</span>
                <span>Score</span>
                <span>Demo</span>
                <span>Acoes</span>
              </div>
              <div className="max-h-[620px] overflow-auto">
                {prospectsQuery.isLoading ? (
                  <div className="p-6 text-sm text-stone-500">Carregando prospects...</div>
                ) : prospects.length ? (
                  prospects.map((prospect) => (
                    <div
                      key={prospect.id}
                      role="button"
                      tabIndex={0}
                      className={cn(
                        "grid w-full grid-cols-[1.3fr_0.8fr_0.8fr_0.7fr_0.9fr_0.8fr] gap-3 border-b border-stone-100 px-4 py-3 text-left text-sm transition hover:bg-stone-50",
                        selectedProspect?.id === prospect.id && "bg-emerald-50/70",
                      )}
                      onClick={() => setSelectedId(prospect.id)}
                      onKeyDown={(event) => {
                        if (event.key === "Enter" || event.key === " ") setSelectedId(prospect.id);
                      }}
                    >
                      <span className="min-w-0">
                        <strong className="block truncate text-stone-950">{prospect.clinic_name}</strong>
                        <span className="block truncate text-xs text-stone-500">
                          {[prospect.city, prospect.whatsapp_phone || prospect.phone].filter(Boolean).join(" - ") || "Sem contato"}
                        </span>
                      </span>
                      <span>
                        <Badge className={statusClass(prospect.status)}>{humanize(prospect.status)}</Badge>
                      </span>
                      <span>
                        <Badge className={temperatureClass(prospect.temperature)}>{humanize(prospect.temperature)}</Badge>
                      </span>
                      <span className="font-bold">{prospect.score}</span>
                      <span className="text-xs text-stone-600">{prospect.demo_tenant_id ? humanize(prospect.demo_status) : "Nao criada"}</span>
                      <span className="flex gap-1">
                        <Button
                          type="button"
                          className="h-8 px-2"
                          variant="outline"
                          onClick={(event) => {
                            event.stopPropagation();
                            generateDemoMutation.mutate(prospect.id);
                          }}
                        >
                          <ShieldCheck size={14} />
                        </Button>
                        <Button
                          type="button"
                          className="h-8 px-2"
                          variant="outline"
                          onClick={(event) => {
                            event.stopPropagation();
                            accessMutation.mutate(prospect.id);
                          }}
                        >
                          <Send size={14} />
                        </Button>
                        <Button
                          type="button"
                          className="h-8 px-2"
                          variant="outline"
                          onClick={(event) => {
                            event.stopPropagation();
                            automationMutation.mutate(prospect.id);
                          }}
                        >
                          <MessageSquareText size={14} />
                        </Button>
                      </span>
                    </div>
                  ))
                ) : (
                  <div className="p-8">
                    <EmptyState title="Nenhuma clinica cadastrada" description="Cadastre o primeiro prospect para gerar uma demo personalizada." />
                  </div>
                )}
              </div>
            </div>
          </section>

          <aside className="space-y-4">
            {selectedProspect ? (
              <ProspectDetail
                prospect={selectedProspect}
                timeline={timelineQuery.data ?? []}
                activity={activityQuery.data ?? []}
                lastDemoLink={lastDemoLink}
                onGenerateDemo={() => generateDemoMutation.mutate(selectedProspect.id)}
                onIssueAccess={() => accessMutation.mutate(selectedProspect.id)}
                onRecordContact={() => contactMutation.mutate(selectedProspect.id)}
                onStartAutomation={() => automationMutation.mutate(selectedProspect.id)}
                onSendReceptionOutreach={() =>
                  outreachMutation.mutate({ prospectId: selectedProspect.id, step: "reception_intro" })
                }
                onSendDecisionMakerPitch={() =>
                  outreachMutation.mutate({
                    prospectId: selectedProspect.id,
                    step: "decision_maker_pitch",
                    recipientName: selectedProspect.owner_name || selectedProspect.manager_name,
                  })
                }
                onSendVideoFollowup={() =>
                  outreachMutation.mutate({
                    prospectId: selectedProspect.id,
                    step: "video_followup",
                    recipientName: selectedProspect.owner_name || selectedProspect.manager_name,
                  })
                }
                onRunOutreachLab={(scenario) =>
                  outreachLabMutation.mutate({
                    prospectId: selectedProspect.id,
                    scenario,
                  })
                }
                onStatusChange={(status) => statusMutation.mutate({ prospectId: selectedProspect.id, status })}
                automationPending={automationMutation.isPending}
                outreachLabPending={outreachLabMutation.isPending}
              />
            ) : (
              <Card className="border-stone-200">
                <CardContent className="p-8">
                  <EmptyState title="Selecione uma clinica" description="Os detalhes comerciais aparecem aqui." />
                </CardContent>
              </Card>
            )}
          </aside>
        </div>
          </>
        ) : null}
      </div>
    </main>
  );
}

function MetricCard({ icon, label, value }: { icon: React.ReactNode; label: string; value: number }) {
  return (
    <Card className="border-stone-200">
      <CardContent className="flex items-center justify-between gap-3 p-4">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-stone-500">{label}</p>
          <p className="mt-1 text-2xl font-black text-stone-950">{numberFormatter.format(value)}</p>
        </div>
        <div className="grid h-10 w-10 place-items-center rounded-lg bg-stone-100 text-stone-600">{icon}</div>
      </CardContent>
    </Card>
  );
}

function ProspectDetail({
  prospect,
  timeline,
  activity,
  lastDemoLink,
  onGenerateDemo,
  onIssueAccess,
  onRecordContact,
  onStartAutomation,
  onSendReceptionOutreach,
  onSendDecisionMakerPitch,
  onSendVideoFollowup,
  onRunOutreachLab,
  onStatusChange,
  automationPending,
  outreachLabPending,
}: {
  prospect: Prospect;
  timeline: TimelineEvent[];
  activity: ActivityEvent[];
  lastDemoLink: string;
  onGenerateDemo: () => void;
  onIssueAccess: () => void;
  onRecordContact: () => void;
  onStartAutomation: () => void;
  onSendReceptionOutreach: () => void;
  onSendDecisionMakerPitch: () => void;
  onSendVideoFollowup: () => void;
  onRunOutreachLab: (scenario: string) => void;
  onStatusChange: (status: string) => void;
  automationPending: boolean;
  outreachLabPending: boolean;
}) {
  const checklistValues = Object.values(prospect.demo_checklist || {});
  const checklistDone = checklistValues.filter(Boolean).length;
  const checklistTotal = checklistValues.length || 12;
  const proposal = buildProposalText(prospect);
  const outreach = getOutreachSnapshot(prospect);
  const outreachLab = getOutreachLabSnapshot(prospect);
  const lastLabRun = outreachLab.last_run && typeof outreachLab.last_run === "object" ? outreachLab.last_run : null;
  const automationLabel = outreachAutomationLabel(outreach);
  const [labScenario, setLabScenario] = useState<string>("manager_interested");

  useEffect(() => {
    const fallbackScenario = typeof lastLabRun?.scenario === "string" ? lastLabRun.scenario : "manager_interested";
    setLabScenario(fallbackScenario);
  }, [prospect.id, lastLabRun?.scenario]);

  return (
    <>
      <Card className="border-stone-200">
        <CardHeader>
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <CardTitle className="truncate text-xl">{prospect.clinic_name}</CardTitle>
              <p className="mt-1 text-sm text-stone-600">{[prospect.city, prospect.state].filter(Boolean).join(" - ") || "Cidade nao informada"}</p>
            </div>
            <Badge className={temperatureClass(prospect.temperature)}>{humanize(prospect.temperature)}</Badge>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-3 gap-3 text-sm">
            <Info label="Score" value={String(prospect.score)} icon={<BarChart3 size={16} />} />
            <Info label="Status" value={humanize(prospect.status)} icon={<Activity size={16} />} />
            <Info label="Demo" value={prospect.demo_tenant_id ? humanize(prospect.demo_status) : "Nao criada"} icon={<ShieldCheck size={16} />} />
          </div>

          <div className="grid gap-2 text-sm">
            <p className="flex items-center gap-2 text-stone-700">
              <PhoneCall size={16} />
              {prospect.whatsapp_phone || prospect.phone || "Telefone nao informado"}
            </p>
            <p className="flex items-center gap-2 text-stone-700">
              <UserRound size={16} />
              {prospect.owner_name || prospect.manager_name || "Decisor ainda nao identificado"}
            </p>
            <p className="flex items-center gap-2 text-stone-700">
              <MessageSquareText size={16} />
              {prospect.main_pain || "Dor principal ainda nao preenchida"}
            </p>
          </div>

          <div className="grid gap-2 sm:grid-cols-2">
            <Button onClick={onGenerateDemo}>
              <ShieldCheck size={16} />
              Gerar demo
            </Button>
            <Button variant="outline" onClick={onIssueAccess} disabled={!prospect.demo_tenant_id}>
              <Send size={16} />
              Copiar acesso
            </Button>
            <Button variant="outline" onClick={onRecordContact}>
              <PhoneCall size={16} />
              Registrar contato
            </Button>
            <select
              className="h-10 rounded-lg border border-stone-200 bg-white px-3 text-sm"
              value={prospect.status}
              onChange={(event) => onStatusChange(event.target.value)}
            >
              {STATUS_OPTIONS.map((status) => (
                <option key={status} value={status}>
                  {humanize(status)}
                </option>
              ))}
            </select>
          </div>

          <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-4 text-sm text-emerald-950">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
              <div>
                <p className="font-semibold">Automacao comercial transparente</p>
                <p className="mt-1 max-w-xl leading-6">
                  Um clique inicia o contato da {BRAND_SALES_TEAM} no WhatsApp. Quando a clinica responder, o sistema registra a resposta, envia o pitch curto com demo e depois o video automaticamente.
                </p>
              </div>
              <Badge className="bg-white text-emerald-800">{automationLabel}</Badge>
            </div>

            <div className="mt-3 grid gap-2 text-xs text-emerald-900/80 sm:grid-cols-2">
              <span>Etapa atual: {outreach.last_step ? humanize(outreach.last_step) : "Ainda nao iniciada"}</span>
              <span>Ultima resposta: {outreach.last_reply_at ? formatDateTimeBR(outreach.last_reply_at) : "Aguardando contato"}</span>
            </div>

            {outreach.last_reply_preview ? (
              <p className="mt-2 rounded-lg border border-emerald-200 bg-white/80 px-3 py-2 text-xs leading-5 text-emerald-900/85">
                Ultima resposta registrada: {outreach.last_reply_preview}
              </p>
            ) : null}

            <Button className="mt-4 w-full bg-emerald-600 text-white hover:bg-emerald-500" onClick={onStartAutomation} disabled={automationPending || outreach.automation_active}>
              <MessageSquareText size={16} />
              {outreach.automation_active ? "Automacao ativa no WhatsApp" : automationPending ? "Iniciando automacao..." : "Iniciar automacao comercial"}
            </Button>
          </div>

          <div className="rounded-lg border border-blue-200 bg-blue-50 p-3 text-sm text-blue-900">
            <p className="font-semibold">Outreach transparente</p>
            <p className="mt-1 leading-6">
              Este fluxo comercial se apresenta como {BRAND_SALES_TEAM}, pede o decisor de forma honesta, envia demo rastreavel e depois o video. Nao usa personificacao de paciente ou urgencia falsa.
            </p>
          </div>

          <div className="grid gap-2 sm:grid-cols-3">
            <Button variant="outline" onClick={onSendReceptionOutreach}>
              <MessageSquareText size={16} />
              Chamar recepção
            </Button>
            <Button variant="outline" onClick={onSendDecisionMakerPitch}>
              <ArrowRight size={16} />
              Enviar pitch + demo
            </Button>
            <Button variant="outline" onClick={onSendVideoFollowup}>
              <Send size={16} />
              Enviar vídeo
            </Button>
          </div>

          <div className="rounded-xl border border-cyan-200 bg-cyan-50 p-4 text-sm text-cyan-950">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
              <div>
                <p className="font-semibold">IA Lab comercial</p>
                <p className="mt-1 max-w-xl leading-6">
                  Simule a conversa entre a clinica prospectada e o nosso sistema sem WhatsApp real. A ultima rodada fica salva no historico comercial da clinica.
                </p>
              </div>
              <Badge className={lastLabRun?.converted ? "bg-emerald-100 text-emerald-700" : "bg-white text-cyan-800"}>
                {lastLabRun?.converted ? "Fluxo converteu no lab" : "Sem simulacao convertida"}
              </Badge>
            </div>

            <div className="mt-3 grid gap-2 sm:grid-cols-[1fr_auto]">
              <select
                className="h-10 rounded-lg border border-cyan-200 bg-white px-3 text-sm"
                value={labScenario}
                onChange={(event) => setLabScenario(event.target.value)}
                disabled={outreachLabPending}
              >
                {OUTREACH_LAB_SCENARIOS.map((scenario) => (
                  <option key={scenario.value} value={scenario.value}>
                    {scenario.label}
                  </option>
                ))}
              </select>
              <Button
                className="bg-cyan-700 text-white hover:bg-cyan-600"
                onClick={() => onRunOutreachLab(labScenario)}
                disabled={outreachLabPending}
              >
                <MessageSquareText size={16} />
                {outreachLabPending ? "Rodando simulacao..." : "Rodar IA Lab"}
              </Button>
            </div>

            <div className="mt-3 grid gap-2 text-xs text-cyan-950/85 sm:grid-cols-2">
              <span>Ultimo cenario: {lastLabRun?.scenario_label || "Nenhum"}</span>
              <span>Ultimo resultado: {lastLabRun?.outcome ? humanize(lastLabRun.outcome) : "Sem rodada ainda"}</span>
              <span>Rodadas neste cenario: {Number(outreachLab.scenario_stats?.[labScenario]?.runs || 0)}</span>
              <span>Conversoes neste cenario: {Number(outreachLab.scenario_stats?.[labScenario]?.conversions || 0)}</span>
            </div>

            {lastLabRun?.recommendation ? (
              <p className="mt-3 rounded-lg border border-cyan-200 bg-white/80 px-3 py-2 text-xs leading-5 text-cyan-950/85">
                Recomendacao do lab: {lastLabRun.recommendation}
              </p>
            ) : null}

            {lastLabRun?.transcript?.length ? (
              <div className="mt-3 space-y-2 rounded-xl border border-cyan-100 bg-white/85 p-3">
                <p className="text-xs font-bold uppercase tracking-wide text-cyan-800">Transcricao simulada</p>
                <div className="max-h-[320px] space-y-2 overflow-y-auto pr-1">
                  {lastLabRun.transcript.map((turn) => {
                    const isOdontoFlux = turn.role === "odontoflux";
                    const isClinic = turn.role === "clinic_virtual";
                    return (
                      <div
                        key={turn.id}
                        className={cn(
                          "flex",
                          isOdontoFlux ? "justify-end" : isClinic ? "justify-start" : "justify-center",
                        )}
                      >
                        <div
                          className={cn(
                            "max-w-[88%] rounded-2xl px-3 py-2 text-sm shadow-sm",
                            isOdontoFlux
                              ? "border border-emerald-100 bg-emerald-600 text-white"
                              : isClinic
                                ? "border border-blue-100 bg-blue-50 text-blue-950"
                                : "border border-stone-200 bg-stone-100 text-stone-700",
                          )}
                        >
                          <div className="mb-1 text-[11px] font-bold uppercase tracking-wide opacity-80">{turn.label}</div>
                          <p className="whitespace-pre-wrap leading-relaxed">{turn.text}</p>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            ) : null}
          </div>

          {lastDemoLink ? (
            <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-900">
              <div className="flex items-center justify-between gap-2">
                <span className="truncate">{lastDemoLink}</span>
                <Button className="h-8 px-2" variant="outline" onClick={() => navigator.clipboard?.writeText(lastDemoLink)}>
                  <Clipboard size={14} />
                </Button>
              </div>
            </div>
          ) : null}
        </CardContent>
      </Card>

      <Card className="border-stone-200">
        <CardHeader>
          <CardTitle className="text-base">Checklist da demo</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="mb-3 flex items-center justify-between text-sm">
            <span className="font-medium">{checklistDone}/{checklistTotal} itens prontos</span>
            <span className="text-stone-500">{Math.round((checklistDone / checklistTotal) * 100)}%</span>
          </div>
          <div className="h-2 overflow-hidden rounded-full bg-stone-200">
            <div className="h-full bg-emerald-600" style={{ width: `${Math.round((checklistDone / checklistTotal) * 100)}%` }} />
          </div>
        </CardContent>
      </Card>

      <Card className="border-stone-200">
        <CardHeader>
          <CardTitle className="text-base">Servicos e unidades</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3 text-sm">
          <div>
            <p className="mb-2 font-semibold text-stone-700">Servicos</p>
            <div className="flex flex-wrap gap-2">
              {prospect.services.map((service) => (
                <Badge key={service.id} className="bg-stone-100 text-stone-700">{service.service_name}</Badge>
              ))}
            </div>
          </div>
          <div>
            <p className="mb-2 font-semibold text-stone-700">Unidades</p>
            <div className="space-y-2">
              {prospect.units.map((unit) => (
                <div key={unit.id} className="rounded-lg border border-stone-200 p-3">
                  <strong>{unit.unit_name}</strong>
                  <p className="text-xs text-stone-500">{unit.address || "Sem endereco"}</p>
                </div>
              ))}
            </div>
          </div>
        </CardContent>
      </Card>

      <Card className="border-stone-200">
        <CardHeader>
          <CardTitle className="text-base">Playbook comercial</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {PLAYBOOKS.map((playbook) => (
            <div key={playbook.title} className="rounded-lg border border-stone-200 p-3">
              <div className="mb-2 flex items-center justify-between gap-2">
                <strong className="text-sm">{playbook.title}</strong>
                <Button className="h-8 px-2" variant="outline" onClick={() => navigator.clipboard?.writeText(playbook.text)}>
                  <Clipboard size={14} />
                </Button>
              </div>
              <p className="text-sm leading-6 text-stone-600">{playbook.text}</p>
            </div>
          ))}
        </CardContent>
      </Card>

      <Card className="border-stone-200">
        <CardHeader>
          <CardTitle className="text-base">Proposta e ROI rapido</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="rounded-lg border border-stone-200 bg-stone-50 p-3 text-sm leading-6 text-stone-700">
            <pre className="whitespace-pre-wrap font-sans">{proposal}</pre>
          </div>
          <Button className="mt-3" variant="outline" onClick={() => navigator.clipboard?.writeText(proposal)}>
            <FileText size={16} />
            Copiar proposta
          </Button>
        </CardContent>
      </Card>

      <Card className="border-stone-200">
        <CardHeader>
          <CardTitle className="text-base">Atividade da demo</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {activity.length ? (
            activity.slice(0, 8).map((event) => (
              <div key={event.id} className="rounded-lg border border-stone-200 p-3 text-sm">
                <div className="flex items-center justify-between gap-2">
                  <strong>{humanize(event.event_name)}</strong>
                  <span className="text-xs text-stone-500">{formatDateTimeBR(event.occurred_at)}</span>
                </div>
                <p className="mt-1 text-xs text-stone-500">{event.page_path || "Sem pagina"}</p>
              </div>
            ))
          ) : (
            <p className="text-sm text-stone-500">Nenhuma atividade registrada ainda.</p>
          )}
        </CardContent>
      </Card>

      <Card className="border-stone-200">
        <CardHeader>
          <CardTitle className="text-base">Timeline comercial</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {timeline.slice(0, 10).map((event) => (
            <div key={event.id} className="border-l-2 border-stone-200 pl-3 text-sm">
              <strong>{event.event_label}</strong>
              <p className="text-xs text-stone-500">{formatDateTimeBR(event.created_at)}</p>
            </div>
          ))}
        </CardContent>
      </Card>
    </>
  );
}

function Info({ label, value, icon }: { label: string; value: string; icon: React.ReactNode }) {
  return (
    <div className="rounded-lg border border-stone-200 p-3">
      <div className="mb-2 text-stone-500">{icon}</div>
      <p className="text-xs font-semibold uppercase tracking-wide text-stone-500">{label}</p>
      <p className="mt-1 truncate font-bold text-stone-950">{value}</p>
    </div>
  );
}

function buildProposalText(prospect: Prospect) {
  const volume = Number(prospect.estimated_volume || 120);
  const lostRate = 0.18;
  const ticket = 350;
  const estimatedLoss = Math.round(volume * lostRate * ticket);
  return `Proposta inicial ${BRAND_NAME} para ${prospect.clinic_name}

Plano recomendado: Piloto Assistido
Duracao: 30 dias
Implantacao: a partir de R$ 2.500
Mensalidade: a partir de R$ 997

Escopo:
- Configuracao da clinica, servicos, unidades e equipe
- Demo personalizada com fluxo de WhatsApp, agenda e retorno
- Treinamento inicial da recepcao
- Acompanhamento comercial e operacional do piloto

Argumento de ROI:
Com ${volume} oportunidades por mes, uma perda estimada de 18% e ticket medio de R$ ${ticket}, a clinica pode estar deixando perto de R$ ${numberFormatter.format(estimatedLoss)} em oportunidades sem acompanhamento claro.

Proximo passo:
Validar a demo personalizada e marcar reuniao de implantacao.`;
}

"use client";

import Link from "next/link";
import type { ReactNode } from "react";
import { useEffect, useState } from "react";
import {
  ArrowLeft,
  BarChart3,
  CheckCircle2,
  Flame,
  MessageSquareText,
  MousePointerClick,
  RefreshCw,
  ShieldAlert,
  Stethoscope,
} from "lucide-react";

import { useAdmSession } from "@/hooks/use-adm-session";
import { canAccessAdmPage } from "@/lib/adm-page-access";
import { getAdminAccessToken } from "@/lib/auth";
import { Badge, Button, Card, CardContent, CardHeader, CardTitle, Input } from "@odontoflux/ui";

type Microconversions = {
  asked_price?: boolean;
  demo_clicked?: boolean;
  whatsapp_tested?: boolean;
  meeting_booked?: boolean;
  proposal_sent?: boolean;
  closed_sale?: boolean;
  lost?: boolean;
};

type ConversationReview = {
  lead_id: string;
  clinic_name: string;
  source: string;
  website_quality: string;
  offer_lane: string;
  lead_temperature: string;
  cold_outreach_message_count?: number;
  message_variant: string;
  clinic_replied: boolean;
  auto_reply_received?: boolean;
  human_reply_received?: boolean;
  first_human_message_received?: boolean;
  outside_24h_window?: boolean;
  template_required?: boolean;
  template_used?: boolean;
  stop_contact_required?: boolean;
  do_not_follow_up?: boolean;
  opt_in_status?: string;
  do_not_contact?: boolean;
  max_remaining_cold_messages?: number;
  analysis_mode?: "economico" | "profissional" | "elite_300";
  token_efficiency_mode?: "economico" | "profissional" | "elite_300";
  token_budget_level?: "low" | "medium" | "high";
  should_use_elite_mode?: boolean;
  elite_mode_reason?: string;
  estimated_token_cost_level?: "low" | "medium" | "high" | "very_high";
  data_loading_strategy?: string;
  large_context_allowed?: boolean;
  reply_type: string;
  objection_type: string;
  stage_reached: string;
  demo_clicked: boolean;
  whatsapp_tested: boolean;
  meeting_booked: boolean;
  proposal_sent: boolean;
  closed_sale: boolean;
  conversation_score: number;
  message_quality_score: number;
  commercial_risk_score: number;
  burn_risk: string;
  next_best_action: string;
  next_best_message: string;
  tags?: string[];
  microconversions?: Microconversions;
  created_at: string;
};

const SAMPLE_JSONL = `{"lead_id":"lead-demo-001","clinic_name":"Clinica Aurora Ficticia","source":"google_places","website_quality":"none","offer_lane":"website_seo","lead_temperature":"warm","cold_outreach_message_count":1,"message_variant":"google_no_website_v1","clinic_replied":true,"auto_reply_received":false,"human_reply_received":true,"first_human_message_received":false,"outside_24h_window":false,"template_required":false,"template_used":false,"stop_contact_required":false,"do_not_follow_up":false,"opt_in_status":"human_replied","do_not_contact":false,"max_remaining_cold_messages":2,"analysis_mode":"profissional","token_efficiency_mode":"profissional","token_budget_level":"medium","should_use_elite_mode":false,"elite_mode_reason":"","estimated_token_cost_level":"medium","data_loading_strategy":"recent_events_only","large_context_allowed":false,"reply_type":"asked_source","objection_type":"source","stage_reached":"replied","demo_clicked":false,"whatsapp_tested":false,"meeting_booked":false,"proposal_sent":false,"closed_sale":false,"conversation_score":82,"message_quality_score":91,"commercial_risk_score":18,"burn_risk":"low","next_best_action":"reply_contextually","next_best_message":"Responder a fonte e pedir o responsavel por WhatsApp/agendamentos.","tags":["sample","fictional"],"microconversions":{"asked_price":false,"demo_clicked":false,"whatsapp_tested":false,"meeting_booked":false,"proposal_sent":false,"closed_sale":false,"lost":false},"created_at":"2026-05-29T12:00:00Z"}
{"lead_id":"lead-demo-002","clinic_name":"Clinica Janela Ficticia","source":"public_website","website_quality":"weak","offer_lane":"audit","lead_temperature":"cold","cold_outreach_message_count":1,"message_variant":"outside_24h_template_gate_v1","clinic_replied":false,"auto_reply_received":false,"human_reply_received":false,"first_human_message_received":false,"outside_24h_window":true,"template_required":true,"template_used":false,"stop_contact_required":true,"do_not_follow_up":true,"opt_in_status":"public_business_contact","do_not_contact":false,"max_remaining_cold_messages":0,"analysis_mode":"economico","token_efficiency_mode":"economico","token_budget_level":"low","should_use_elite_mode":false,"elite_mode_reason":"elite_blocked_for_cold_lead_without_human_reply","estimated_token_cost_level":"low","data_loading_strategy":"minimal","large_context_allowed":false,"reply_type":"none","objection_type":"none","stage_reached":"first_message","demo_clicked":false,"whatsapp_tested":false,"meeting_booked":false,"proposal_sent":false,"closed_sale":false,"conversation_score":30,"message_quality_score":0,"commercial_risk_score":88,"burn_risk":"critical","next_best_action":"stop_contact_or_use_approved_template_only","next_best_message":"","tags":["sample","fictional"],"microconversions":{"asked_price":false,"demo_clicked":false,"whatsapp_tested":false,"meeting_booked":false,"proposal_sent":false,"closed_sale":false,"lost":false},"created_at":"2026-05-29T17:05:00Z"}`;

function humanize(value?: string | null) {
  if (!value) return "-";
  return value
    .replace(/_/g, " ")
    .split(" ")
    .filter(Boolean)
    .map((part) => part[0].toUpperCase() + part.slice(1))
    .join(" ");
}

function parseJsonl(value: string) {
  const records: ConversationReview[] = [];
  const errors: string[] = [];
  value.split(/\r?\n/).forEach((rawLine, index) => {
    const line = rawLine.trim();
    if (!line) return;
    try {
      const parsed = JSON.parse(line) as ConversationReview;
      if (!parsed.lead_id || !parsed.clinic_name) {
        errors.push(`Linha ${index + 1}: lead_id e clinic_name sao obrigatorios.`);
        return;
      }
      records.push(parsed);
    } catch (error) {
      errors.push(`Linha ${index + 1}: JSON invalido.`);
    }
  });
  return { records, errors };
}

function percent(value: number) {
  return `${Math.round(value * 100)}%`;
}

function rate(records: ConversationReview[], predicate: (record: ConversationReview) => boolean) {
  if (!records.length) return 0;
  return records.filter(predicate).length / records.length;
}

function isHotLead(record: ConversationReview) {
  return ["hot", "very_hot"].includes(record.lead_temperature) || Number(record.conversation_score || 0) >= 80;
}

function askedPrice(record: ConversationReview) {
  return record.reply_type === "asked_price" || record.microconversions?.asked_price === true;
}

function isStalled(record: ConversationReview) {
  if (record.closed_sale || record.microconversions?.lost) return false;
  if (!record.clinic_replied) return true;
  return ["wait", "follow_up"].includes(record.next_best_action);
}

function groupMessageVariants(records: ConversationReview[]) {
  const grouped = new Map<string, ConversationReview[]>();
  records.forEach((record) => {
    const key = record.message_variant || "unknown";
    grouped.set(key, [...(grouped.get(key) || []), record]);
  });
  return Array.from(grouped.entries())
    .map(([variant, items]) => ({
      variant,
      count: items.length,
      replyRate: rate(items, (item) => item.clinic_replied),
      averageQuality:
        items.reduce((sum, item) => sum + Number(item.message_quality_score || 0), 0) / Math.max(items.length, 1),
    }))
    .sort((first, second) => second.replyRate - first.replyRate || second.averageQuality - first.averageQuality);
}

function groupNextActions(records: ConversationReview[]) {
  const counts = new Map<string, number>();
  records.forEach((record) => {
    const key = record.next_best_action || "unknown";
    counts.set(key, (counts.get(key) || 0) + 1);
  });
  return Array.from(counts.entries()).sort((first, second) => second[1] - first[1]);
}

function groupByValue(records: ConversationReview[], getValue: (record: ConversationReview) => string | undefined) {
  const counts = new Map<string, number>();
  records.forEach((record) => {
    const key = getValue(record) || "unknown";
    counts.set(key, (counts.get(key) || 0) + 1);
  });
  return Array.from(counts.entries()).sort((first, second) => second[1] - first[1] || first[0].localeCompare(second[0]));
}

function isCold(record: ConversationReview) {
  return record.lead_temperature === "cold" || record.opt_in_status === "public_business_contact";
}

function isHighRisk(record: ConversationReview) {
  return ["high", "critical"].includes(record.burn_risk) || Number(record.commercial_risk_score || 0) >= 75;
}

function isBlocked(record: ConversationReview) {
  return record.stop_contact_required === true || record.next_best_action === "stop_contact" || record.next_best_action === "stop_contact_or_use_approved_template_only";
}

function eliteBlocked(record: ConversationReview) {
  return record.should_use_elite_mode === false && Boolean(record.elite_mode_reason?.includes("blocked"));
}

function riskClass(risk?: string | null) {
  if (risk === "critical" || risk === "high") return "bg-rose-100 text-rose-800";
  if (risk === "medium") return "bg-amber-100 text-amber-800";
  return "bg-emerald-100 text-emerald-800";
}

export default function OutreachIntelligencePage() {
  const [hasToken, setHasToken] = useState(false);
  const [jsonl, setJsonl] = useState(SAMPLE_JSONL);
  const [query, setQuery] = useState("");

  useEffect(() => {
    setHasToken(Boolean(getAdminAccessToken()));
  }, []);

  const admSessionQuery = useAdmSession(hasToken);
  const admPermissions = admSessionQuery.data?.resolved_adm_page_permissions;
  const canViewPage = canAccessAdmPage(admPermissions, "adm_outreach_automation", "view");
  const parsed = parseJsonl(jsonl);
  const normalizedQuery = query.trim().toLowerCase();
  const records = parsed.records.filter((record) => {
    if (!normalizedQuery) return true;
    return `${record.clinic_name} ${record.lead_id} ${record.offer_lane} ${record.next_best_action} ${record.message_variant}`
      .toLowerCase()
      .includes(normalizedQuery);
  });
  const variants = groupMessageVariants(records);
  const bestVariant = variants[0];
  const worstVariant = variants[variants.length - 1];
  const actions = groupNextActions(records);
  const objections = groupByValue(records.filter((record) => record.objection_type && record.objection_type !== "none"), (record) => record.objection_type);
  const analysisModes = groupByValue(records, (record) => record.analysis_mode);
  const costLevels = groupByValue(records, (record) => record.estimated_token_cost_level);
  const eliteReasons = groupByValue(records.filter((record) => record.should_use_elite_mode), (record) => record.elite_mode_reason);

  if (!hasToken) {
    return (
      <main className="min-h-screen overflow-x-hidden bg-slate-950 p-6 text-white">
        <Card className="mx-auto mt-20 max-w-xl border-slate-800 bg-slate-900 text-white">
          <CardContent className="space-y-4 p-6">
            <div className="grid h-12 w-12 place-items-center rounded-2xl bg-cyan-400 text-sm font-black text-slate-950">CF</div>
            <div>
              <p className="text-xs font-bold uppercase tracking-[0.2em] text-cyan-200">Inteligencia comercial</p>
              <h1 className="mt-1 text-2xl font-black">Entre no /adm primeiro</h1>
              <p className="mt-2 text-sm leading-6 text-slate-300">Esta visao usa o mesmo login administrativo do CRM comercial.</p>
            </div>
            <Link href="/adm" className="inline-flex h-10 items-center justify-center gap-2 rounded-xl bg-cyan-300 px-4 text-sm font-bold text-slate-950">
              Abrir login do /adm
              <ArrowLeft className="h-4 w-4 rotate-180" />
            </Link>
          </CardContent>
        </Card>
      </main>
    );
  }

  if (admSessionQuery.isLoading) {
    return (
      <main className="grid min-h-screen place-items-center bg-slate-950 px-4 text-white">
        <Card className="w-full max-w-md border-slate-800 bg-slate-900 text-white">
          <CardContent className="p-8 text-center text-sm text-slate-300">Carregando permissoes...</CardContent>
        </Card>
      </main>
    );
  }

  if (!canViewPage) {
    return (
      <main className="grid min-h-screen place-items-center bg-slate-950 px-4 text-white">
        <Card className="w-full max-w-xl border-slate-800 bg-slate-900 text-white">
          <CardContent className="space-y-3 p-8 text-center">
            <h1 className="text-2xl font-black">Sem acesso a inteligencia comercial</h1>
            <p className="text-sm leading-6 text-slate-300">Seu usuario precisa da permissao de automacao comercial para abrir esta visao.</p>
            <Link href="/adm" className="inline-flex h-10 items-center justify-center rounded-xl bg-cyan-300 px-4 text-sm font-bold text-slate-950">
              Voltar ao CRM
            </Link>
          </CardContent>
        </Card>
      </main>
    );
  }

  return (
    <main className="min-h-screen overflow-x-hidden bg-[radial-gradient(circle_at_top_left,#164e63,transparent_36%),linear-gradient(135deg,#020617,#0f172a_55%,#111827)] p-4 text-white md:p-6">
      <div className="mx-auto max-w-7xl space-y-5">
        <Card className="border-white/10 bg-white/10 text-white shadow-2xl backdrop-blur">
          <CardContent className="space-y-5 p-5">
            <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
              <div>
                <p className="text-xs font-black uppercase tracking-[0.24em] text-cyan-200">ClinicFlux AI</p>
                <h1 className="mt-2 text-3xl font-black md:text-5xl">Inteligencia comercial</h1>
                <p className="mt-3 max-w-3xl text-sm leading-6 text-slate-200">
                  Analise local de reviews JSONL, microconversoes, mensagens vencedoras, riscos comerciais e proximas acoes.
                  Os dados colados aqui ficam no navegador; nenhum endpoint novo e criado.
                </p>
              </div>
              <div className="flex flex-wrap gap-2">
                <Link href="/adm/automacao-comercial" className="inline-flex h-10 items-center justify-center gap-2 rounded-xl border border-white/15 bg-white/10 px-4 text-sm font-bold text-white hover:bg-white/15">
                  <ArrowLeft className="h-4 w-4" />
                  Automacao
                </Link>
                <Button variant="outline" className="border-white/15 bg-white/10 text-white hover:bg-white/15" onClick={() => setJsonl(SAMPLE_JSONL)}>
                  <RefreshCw className="h-4 w-4" />
                  Restaurar amostra
                </Button>
              </div>
            </div>

            <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
              <Metric icon={<Stethoscope className="h-5 w-5" />} label="Leads analisados" value={String(records.length)} helper="Linhas JSONL validas" />
              <Metric icon={<MessageSquareText className="h-5 w-5" />} label="Leads frios" value={String(records.filter(isCold).length)} helper={percent(rate(records, isCold))} />
              <Metric icon={<RefreshCw className="h-5 w-5" />} label="Auto-respostas" value={String(records.filter((item) => item.auto_reply_received).length)} helper="Nao contam como humano" />
              <Metric icon={<CheckCircle2 className="h-5 w-5" />} label="Respostas humanas" value={String(records.filter((item) => item.human_reply_received).length)} helper={`${records.filter((item) => item.opt_in_status === "human_replied").length} human_replied`} />
              <Metric icon={<Flame className="h-5 w-5" />} label="Primeira humana" value={String(records.filter((item) => item.first_human_message_received).length)} helper="Vinda da clinica" />
            </div>

            <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
              <Metric icon={<ShieldAlert className="h-5 w-5" />} label="Parar contato" value={String(records.filter((item) => item.stop_contact_required || item.do_not_contact).length)} helper="Stop / do_not_contact" />
              <Metric icon={<ShieldAlert className="h-5 w-5" />} label="Risco alto" value={String(records.filter(isHighRisk).length)} helper="High ou critical" />
              <Metric icon={<MessageSquareText className="h-5 w-5" />} label="Bloqueadas" value={String(records.filter(isBlocked).length)} helper="Sem proxima mensagem livre" />
              <Metric icon={<RefreshCw className="h-5 w-5" />} label="Fora 24h" value={String(records.filter((item) => item.outside_24h_window).length)} helper={`${records.filter((item) => item.template_required).length} exigem template`} />
              <Metric icon={<MousePointerClick className="h-5 w-5" />} label="Elite bloqueado" value={String(records.filter(eliteBlocked).length)} helper="Economia de tokens" />
            </div>
          </CardContent>
        </Card>

        <section className="grid gap-5 xl:grid-cols-[420px_minmax(0,1fr)]">
          <Card className="border-white/10 bg-slate-950/70 text-white backdrop-blur">
            <CardHeader>
              <CardTitle className="text-xl">Fonte JSONL</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <p className="text-sm leading-6 text-slate-300">
                Cole o conteudo de `outreach-reviews/conversation-reviews.jsonl` para ver a leitura operacional.
                Cada linha precisa ser um JSON valido.
              </p>
              <textarea
                className="min-h-[320px] w-full rounded-2xl border border-white/10 bg-slate-900 p-3 font-mono text-xs leading-5 text-cyan-50 outline-none focus:border-cyan-300"
                value={jsonl}
                onChange={(event) => setJsonl(event.target.value)}
              />
              {parsed.errors.length ? (
                <div className="rounded-2xl border border-rose-400/40 bg-rose-500/10 p-3 text-sm text-rose-100">
                  {parsed.errors.map((error) => (
                    <p key={error}>{error}</p>
                  ))}
                </div>
              ) : (
                <div className="rounded-2xl border border-emerald-400/30 bg-emerald-400/10 p-3 text-sm text-emerald-100">
                  JSONL valido para esta visao.
                </div>
              )}
              <Input
                className="border-white/10 bg-white/10 text-white placeholder:text-slate-400"
                placeholder="Filtrar por clinica, acao, lane ou variante"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
              />
            </CardContent>
          </Card>

          <div className="space-y-5">
            <div className="grid gap-4 lg:grid-cols-2">
              <InsightCard title="Melhor mensagem" value={bestVariant?.variant || "-"} helper={bestVariant ? `${percent(bestVariant.replyRate)} reply rate / qualidade ${Math.round(bestVariant.averageQuality)}` : "Sem dados"} />
              <InsightCard title="Pior mensagem" value={worstVariant?.variant || "-"} helper={worstVariant ? `${percent(worstVariant.replyRate)} reply rate / qualidade ${Math.round(worstVariant.averageQuality)}` : "Sem dados"} />
            </div>

            <Card className="border-white/10 bg-white/10 text-white backdrop-blur">
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-xl">
                  <ShieldAlert className="h-5 w-5 text-cyan-200" />
                  Modos e custo
                </CardTitle>
              </CardHeader>
              <CardContent className="grid gap-4 lg:grid-cols-3">
                <CountBlock title="Modos de analise" items={analysisModes} empty="Sem modos registrados." />
                <CountBlock title="Custo estimado" items={costLevels} empty="Sem custo registrado." />
                <CountBlock title="Modo elite usado" items={eliteReasons} empty="Nenhum caso elite." />
              </CardContent>
            </Card>

            <Card className="border-white/10 bg-white/10 text-white backdrop-blur">
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-xl">
                  <BarChart3 className="h-5 w-5 text-cyan-200" />
                  Funil e proximas acoes
                </CardTitle>
              </CardHeader>
              <CardContent className="grid gap-4 lg:grid-cols-3">
                <ListBlock title="Perguntaram preco" records={records.filter(askedPrice)} empty="Nenhum pedido de preco." />
                <ListBlock title="Mensagens bloqueadas" records={records.filter(isBlocked)} empty="Nenhuma mensagem bloqueada." />
                <div className="rounded-2xl border border-white/10 bg-slate-950/60 p-4">
                  <p className="text-sm font-black uppercase tracking-[0.18em] text-cyan-200">Acoes recomendadas</p>
                  <div className="mt-3 space-y-2">
                    {actions.length ? (
                      actions.map(([action, count]) => (
                        <div key={action} className="flex items-center justify-between rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-sm">
                          <span>{humanize(action)}</span>
                          <Badge className="bg-cyan-200 text-slate-950">{count}</Badge>
                        </div>
                      ))
                    ) : (
                      <p className="text-sm text-slate-400">Sem acoes.</p>
                    )}
                  </div>
                </div>
              </CardContent>
            </Card>

            <Card className="border-white/10 bg-white/10 text-white backdrop-blur">
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-xl">
                  <BarChart3 className="h-5 w-5 text-cyan-200" />
                  Seguranca operacional
                </CardTitle>
              </CardHeader>
              <CardContent className="grid gap-4 lg:grid-cols-3">
                <ListBlock title="Do not follow-up" records={records.filter((item) => item.do_not_follow_up)} empty="Nenhum lead marcado." />
                <ListBlock title="Human replied" records={records.filter((item) => item.opt_in_status === "human_replied")} empty="Nenhum human_replied." />
                <CountBlock title="Top objecoes" items={objections} empty="Sem objecoes." />
              </CardContent>
            </Card>

            <Card className="border-white/10 bg-white/10 text-white backdrop-blur">
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-xl">
                  <ShieldAlert className="h-5 w-5 text-amber-200" />
                  Reviews analisadas
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                {records.map((record) => (
                  <div key={`${record.lead_id}-${record.created_at}`} className="rounded-2xl border border-white/10 bg-slate-950/60 p-4">
                    <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                      <div>
                        <p className="text-lg font-black">{record.clinic_name}</p>
                        <p className="mt-1 text-xs text-slate-400">{record.lead_id} / {humanize(record.source)} / {humanize(record.offer_lane)}</p>
                      </div>
                      <div className="flex flex-wrap gap-2">
                        <Badge className="bg-cyan-100 text-cyan-900">Score {record.conversation_score}</Badge>
                        <Badge className="bg-emerald-100 text-emerald-900">Msg {record.message_quality_score}</Badge>
                        <Badge className={riskClass(record.burn_risk)}>Risco {humanize(record.burn_risk)}</Badge>
                      </div>
                    </div>
                    <div className="mt-3 grid gap-3 md:grid-cols-4">
                      <Info label="Temperatura" value={humanize(record.lead_temperature)} />
                      <Info label="Estagio" value={humanize(record.stage_reached)} />
                      <Info label="Resposta" value={record.clinic_replied ? humanize(record.reply_type) : "Sem resposta"} />
                      <Info label="Proxima acao" value={humanize(record.next_best_action)} />
                      <Info label="Modo" value={humanize(record.analysis_mode)} />
                      <Info label="Custo" value={humanize(record.estimated_token_cost_level)} />
                      <Info label="Carregamento" value={humanize(record.data_loading_strategy)} />
                      <Info label="Elite" value={record.should_use_elite_mode ? humanize(record.elite_mode_reason) : "Nao"} />
                    </div>
                    <p className="mt-3 rounded-xl border border-white/10 bg-white/5 p-3 text-sm leading-6 text-slate-200">
                      {record.next_best_message || "Sem mensagem recomendada."}
                    </p>
                  </div>
                ))}
              </CardContent>
            </Card>
          </div>
        </section>
      </div>
    </main>
  );
}

function Metric({ icon, label, value, helper }: { icon: ReactNode; label: string; value: string; helper: string }) {
  return (
    <div className="rounded-2xl border border-white/10 bg-slate-950/60 p-4">
      <div className="text-cyan-200">{icon}</div>
      <p className="mt-3 text-xs font-black uppercase tracking-[0.18em] text-slate-400">{label}</p>
      <p className="mt-2 text-3xl font-black text-white">{value}</p>
      <p className="mt-1 text-xs text-slate-400">{helper}</p>
    </div>
  );
}

function InsightCard({ title, value, helper }: { title: string; value: string; helper: string }) {
  return (
    <Card className="border-white/10 bg-white/10 text-white backdrop-blur">
      <CardContent className="p-5">
        <p className="text-xs font-black uppercase tracking-[0.18em] text-cyan-200">{title}</p>
        <p className="mt-2 truncate text-2xl font-black">{value}</p>
        <p className="mt-2 text-sm text-slate-300">{helper}</p>
      </CardContent>
    </Card>
  );
}

function ListBlock({ title, records, empty }: { title: string; records: ConversationReview[]; empty: string }) {
  return (
    <div className="rounded-2xl border border-white/10 bg-slate-950/60 p-4">
      <p className="text-sm font-black uppercase tracking-[0.18em] text-cyan-200">{title}</p>
      <div className="mt-3 space-y-2">
        {records.length ? (
          records.slice(0, 8).map((record) => (
            <div key={`${title}-${record.lead_id}`} className="rounded-xl border border-white/10 bg-white/5 p-3">
              <p className="text-sm font-bold">{record.clinic_name}</p>
              <p className="mt-1 text-xs text-slate-400">{humanize(record.next_best_action)} / {humanize(record.offer_lane)}</p>
            </div>
          ))
        ) : (
          <p className="text-sm text-slate-400">{empty}</p>
        )}
      </div>
    </div>
  );
}

function CountBlock({ title, items, empty }: { title: string; items: [string, number][]; empty: string }) {
  return (
    <div className="rounded-2xl border border-white/10 bg-slate-950/60 p-4">
      <p className="text-sm font-black uppercase tracking-[0.18em] text-cyan-200">{title}</p>
      <div className="mt-3 space-y-2">
        {items.length ? (
          items.map(([name, count]) => (
            <div key={`${title}-${name}`} className="flex items-center justify-between rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-sm">
              <span>{humanize(name)}</span>
              <Badge className="bg-cyan-200 text-slate-950">{count}</Badge>
            </div>
          ))
        ) : (
          <p className="text-sm text-slate-400">{empty}</p>
        )}
      </div>
    </div>
  );
}

function Info({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-white/10 bg-white/5 p-3">
      <p className="text-[11px] font-black uppercase tracking-[0.16em] text-slate-400">{label}</p>
      <p className="mt-2 text-sm font-semibold text-white">{value}</p>
    </div>
  );
}

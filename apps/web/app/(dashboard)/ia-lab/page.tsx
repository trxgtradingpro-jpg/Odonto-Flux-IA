"use client";

import { useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Beaker, Bot, Eraser, Play, Save, Sparkles, Square, Trash2, UserRound } from "lucide-react";
import { toast } from "sonner";

import { PageHeader } from "@/components/premium";
import { ErrorState, LoadingState } from "@/components/page-state";
import { api } from "@/lib/api";
import { formatDateTimeBR } from "@/lib/formatters";
import { Badge, Button, Card, CardContent, CardHeader, CardTitle, Input } from "@odontoflux/ui";

type AILabHistoryItem = {
  id: string;
  created_at: string;
  updated_at?: string | null;
  input_text: string;
  context_text?: string;
  ai_reply_text?: string;
  ai_next_action?: string;
  ai_action_payload?: Record<string, unknown>;
  ai_confidence?: number | null;
  ai_raw_output?: string;
  contract_valid: boolean;
  edited_response_text?: string;
  note?: string;
  metadata?: Record<string, unknown>;
};

type AILabHistoryResponse = {
  data: AILabHistoryItem[];
  meta: { total: number; limit: number };
};

type InteractiveOption = {
  id: string;
  title: string;
  description?: string;
};

type InteractivePreview = {
  interactive_type?: string;
  source?: string;
  action?: string;
  header_text?: string;
  body_text?: string;
  footer_text?: string;
  button_title?: string;
  section_title?: string;
  rows?: InteractiveOption[];
  buttons?: InteractiveOption[];
};

type AILabFlowMode = "auto" | "legacy" | "structured";

type StructuredFlowSnapshot = {
  enabled?: boolean;
  schema_version?: string;
  no_dispatch?: boolean;
  no_persistence?: boolean;
  extractor?: {
    contract_valid?: boolean;
    error?: string | null;
    decision?: Record<string, unknown>;
    metadata?: Record<string, unknown>;
  };
  safe_persistence_plan?: Record<string, unknown>;
  system_action_result?: Record<string, unknown>;
  patient_reply?: Record<string, unknown>;
  context_preview?: Record<string, unknown>;
};

type AILabSimulateResponse = {
  status: string;
  flow_mode?: "legacy" | "structured";
  no_dispatch: boolean;
  no_persistence?: boolean;
  contract_valid: boolean;
  contract_retried: boolean;
  input_text: string;
  context_text: string;
  intent: {
    intent?: string | null;
    confidence?: number | null;
  };
  response: {
    reply_text: string;
    next_action: string;
    action_payload: Record<string, unknown>;
    confidence?: number | null;
  };
  raw_output: string;
  metadata?: Record<string, unknown>;
  interactive_preview?: InteractivePreview | null;
  structured_flow?: StructuredFlowSnapshot | null;
  training_examples_used?: boolean;
  custom_prompt_used?: boolean;
  knowledge_context_used?: boolean;
  history_entry?: AILabHistoryItem | null;
  lab_conversation_id?: string | null;
  lab_inbound_message_id?: string | null;
  lab_outbound_message_id?: string | null;
};

type AutoTranscriptItem = {
  id: string;
  role: "patient" | "clinic" | "system";
  text: string;
  meta?: string;
  createdAt: string;
};

const GOLDEN_SCENARIOS = [
  "Oi, quero agendar uma avaliação para esta semana.",
  "Quanto custa esse procedimento?",
  "Preciso remarcar minha consulta de amanhã.",
  "Estou com dor forte e sangramento, é urgente.",
  "Quero falar com um atendente humano.",
];

const AUTO_CONVERSATION_STARTER = "Oi, quero agendar uma avaliacao e entender como funciona.";

function wait(ms: number) {
  return new Promise((resolve) => {
    window.setTimeout(resolve, ms);
  });
}

function makeTranscriptId() {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function makeTranscriptItem(
  role: AutoTranscriptItem["role"],
  text: string,
  meta?: string,
): AutoTranscriptItem {
  return {
    id: makeTranscriptId(),
    role,
    text,
    meta,
    createdAt: new Date().toISOString(),
  };
}

function normalizeText(value?: string | null) {
  return String(value || "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase();
}

function prettyJson(value: unknown) {
  if (value === undefined || value === null || value === "") return "(vazio)";
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

function asRecord(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  return value as Record<string, unknown>;
}

function buildAutomaticContext(
  transcript: AutoTranscriptItem[],
  extraContext?: string,
  directionText?: string,
  goalConclusion = false,
) {
  const recentLines = transcript.slice(-10).map((item) => {
    const speaker = item.role === "patient" ? "Paciente virtual" : item.role === "clinic" ? "Clinica IA" : "Sistema";
    return `${speaker}: ${item.text}`;
  });
  return [
    "[LAB] Conversa automatica sem WhatsApp real.",
    "Continue a simulacao considerando o historico abaixo.",
    goalConclusion ? "Objetivo desta simulacao: conduzir ate uma conclusao clara da conversa." : "",
    directionText ? `Rumo desejado pelo operador: ${directionText}` : "",
    extraContext ? `Proximo comportamento do paciente virtual: ${extraContext}` : "",
    ...recentLines,
  ]
    .filter(Boolean)
    .join("\n");
}

function isConversationConclusion(result: AILabSimulateResponse, turnIndex: number) {
  if (turnIndex < 1) return false;
  const reply = normalizeText(result.response.reply_text);
  const nextAction = String(result.response.next_action || "none");
  const clearConclusionSignals = [
    "agendamento confirmado",
    "agendamento esta confirmado",
    "consulta confirmada",
    "consulta agendada",
    "ficou agendada",
    "esta agendado",
    "esta confirmada",
    "ficou confirmado",
    "ficou reservado",
    "remarcacao confirmada",
    "retorno agendado",
    "resumo final do agendamento",
    "endereco:",
    "documento com foto",
    "aguardamos voce",
    "conversa encerrada",
    "se precisar alterar",
    "encaminhei para",
    "um atendente vai",
    "protocolo registrado",
    "ate breve",
    "obrigado pelo contato",
  ];
  const hasConfirmedBooking = reply.includes("agendamento") && (reply.includes("confirmad") || reply.includes("reservad"));
  const hasVisitGuidance = reply.includes("endereco") || reply.includes("documento com foto") || reply.includes("aguardamos voce");
  return (
    clearConclusionSignals.some((signal) => reply.includes(signal))
    || (["finalize_booking_auto", "request_cpf_after_booking"].includes(nextAction) && hasConfirmedBooking && hasVisitGuidance)
    || (nextAction === "none" && reply.includes("qualquer duvida"))
  );
}

function directedPatientMessage(directionText: string, turnIndex: number) {
  const direction = normalizeText(directionText);
  if (!direction) return null;

  if (direction.includes("pix") || direction.includes("pagamento") || direction.includes("preco") || direction.includes("valor")) {
    const messages = [
      "Antes de agendar, quais sao as formas de pagamento aceitas?",
      "Entendi. E qual seria o valor aproximado para uma avaliacao?",
      "Se estiver tudo certo, quero tentar agendar no primeiro horario disponivel.",
    ];
    return messages[turnIndex] ?? null;
  }

  if (direction.includes("remarc") || direction.includes("reagend")) {
    const messages = [
      "Preciso remarcar minha consulta. Tem outro horario disponivel?",
      "Pode ser com qualquer profissional disponivel, nao precisa ser o mesmo.",
      "Se tiver, pode confirmar o melhor horario para mim.",
    ];
    return messages[turnIndex] ?? null;
  }

  if (direction.includes("retorno") || direction.includes("proxima consulta")) {
    const messages = [
      "Preciso marcar um retorno. Como voces fazem esse agendamento?",
      "Pode ser na proxima semana, de preferencia pela manha.",
      "Pode confirmar esse retorno para mim?",
    ];
    return messages[turnIndex] ?? null;
  }

  if (direction.includes("dor") || direction.includes("urgente") || direction.includes("emergencia")) {
    const messages = [
      "Estou com dor forte e queria saber se consigo atendimento urgente.",
      "A dor comecou hoje e esta incomodando bastante.",
      "Se tiver encaixe, quero confirmar agora.",
    ];
    return messages[turnIndex] ?? null;
  }

  if (direction.includes("humano") || direction.includes("atendente") || direction.includes("recepcao")) {
    const messages = [
      "Quero falar com uma pessoa da recepcao, por favor.",
      "Pode encaminhar meu contato para alguem me chamar?",
      "Tudo bem, vou aguardar o contato.",
    ];
    return messages[turnIndex] ?? null;
  }

  if (turnIndex === 0) {
    return `Quero seguir por esse caminho: ${directionText}`;
  }
  return null;
}

function deriveNextPatientMessage(
  result: AILabSimulateResponse,
  turnIndex: number,
  options?: { directionText?: string; goalConclusion?: boolean; maxTurns?: number },
) {
  const structuredActionResult = asRecord(result.structured_flow?.system_action_result);
  const structuredAction = String(structuredActionResult?.action || result.response.next_action || "none");
  const reply = normalizeText(result.response.reply_text);
  if (result.flow_mode === "structured" && structuredActionResult) {
    const slots = Array.isArray(structuredActionResult.slots) ? structuredActionResult.slots : [];
    const availableSlots = slots.map((slot) => asRecord(slot)).filter((slot): slot is Record<string, unknown> => Boolean(slot));
    const preferredSlot = availableSlots[turnIndex % Math.max(availableSlots.length, 1)];
    if (structuredAction === "query_availability" && preferredSlot) {
      const selectedLabel = String(preferredSlot.label || preferredSlot.starts_at || "o primeiro horario disponivel");
      const selectedSlotId = typeof preferredSlot.slot_id === "string" ? preferredSlot.slot_id : "";
      const selectedUnitName = typeof preferredSlot.unit_name === "string" ? preferredSlot.unit_name : "";
      return {
        text: selectedSlotId
          ? `Seleciono: ${selectedLabel}${selectedUnitName ? ` na ${selectedUnitName}` : ""} (${selectedSlotId})`
          : `Pode ser ${selectedLabel} para mim.`,
        reason: selectedSlotId
          ? "Paciente escolheu um horario retornado pela consulta real de disponibilidade com o slot_id para a proxima validacao."
          : "Paciente escolheu um horario retornado pela consulta real de disponibilidade.",
      };
    }
    if (["validate_slot", "validate_and_hold_slot"].includes(structuredAction)) {
      const status = String(structuredActionResult.status || "");
      if (["held", "available", "read_only_preview"].includes(status)) {
        const asksFullName = reply.includes("nome completo") || reply.includes("seu nome");
        const asksPhone = reply.includes("whatsapp") || reply.includes("telefone") || reply.includes("numero");
        if (asksFullName && asksPhone) {
          return {
            text: "Meu nome completo e Guilherme Gomes e esse WhatsApp e o melhor numero para confirmacao.",
            reason: "Paciente confirmou os dados solicitados depois da validacao do horario.",
          };
        }
        if (asksFullName) {
          return {
            text: "Meu nome completo e Guilherme Gomes.",
            reason: "Paciente informou o nome completo solicitado depois da validacao do horario.",
          };
        }
        if (asksPhone) {
          return {
            text: "Sim, esse WhatsApp e o melhor numero para confirmacao.",
            reason: "Paciente confirmou o telefone solicitado depois da validacao do horario.",
          };
        }
        if (reply.includes("mais alguma coisa") || reply.includes("preparo para a consulta")) {
          return null;
        }
        return {
          text: "Meu nome completo e Guilherme Gomes e esse WhatsApp e o melhor numero para confirmacao.",
          reason: "Paciente informou o dado faltante depois da validação do horário.",
        };
      }
      return {
        text: turnIndex % 2 === 0
          ? "Tudo bem, me mande outras opções reais de horário disponíveis."
          : "Pode verificar outro horário disponível, de preferência no mesmo período?",
        reason: "Paciente pediu alternativas depois de o backend indicar que o horário escolhido não está disponível.",
      };
    }
    const units = Array.isArray(structuredActionResult.units) ? structuredActionResult.units : [];
    const firstUnit = asRecord(units[0]);
    if (structuredAction === "query_units" && firstUnit) {
      return {
        text: `Prefiro a unidade ${String(firstUnit.name || "principal")}.`,
        reason: "Paciente escolheu a primeira unidade ativa retornada pelo backend.",
      };
    }
    if (structuredAction === "query_service") {
      return {
        text: turnIndex % 2 === 0
          ? "Quero fazer uma avaliação inicial para entender o melhor tratamento."
          : "Pode verificar horários para uma avaliação desse tratamento?",
        reason: "Paciente informou o servico/procedimento depois da consulta estruturada.",
      };
    }
  }

  const rows = normalizeInteractiveOptions(result.interactive_preview?.rows);
  const buttons = normalizeInteractiveOptions(result.interactive_preview?.buttons);
  const selectedOption = rows[0] ?? buttons[0];
  if (selectedOption) {
    return {
      text: `Seleciono: ${selectedOption.title || selectedOption.id} (${selectedOption.id})`,
      reason: "Paciente escolheu a primeira opcao interativa apresentada pela IA.",
    };
  }

  const nextAction = String(result.response.next_action || "none");
  if (nextAction === "finalize_booking_auto") {
    return {
      text: "Perfeito. Pode me mandar o endereco, o que preciso levar e finalizar o atendimento?",
      reason: "Paciente pediu as orientacoes finais depois da confirmacao do agendamento.",
    };
  }
  if (nextAction === "request_cpf_after_booking") {
    return {
      text: "Meu nome e Ana Paula, CPF 529.982.247-25, nascimento 10/05/1990. Pode finalizar com endereco e orientacoes?",
      reason: "Paciente informou os dados finais e pediu o resumo para encerrar.",
    };
  }
  const directedMessage = directedPatientMessage(options?.directionText || "", turnIndex);
  if (directedMessage) {
    return {
      text: directedMessage,
      reason: "Paciente seguiu o rumo informado pelo operador do IA Lab.",
    };
  }
  if (reply.includes("cpf") || reply.includes("data de nascimento")) {
    return {
      text: "Meu nome e Ana Paula, CPF 529.982.247-25, nascimento 10/05/1990. Pode finalizar com endereco e orientacoes?",
      reason: "Paciente informou CPF e data de nascimento solicitados.",
    };
  }
  if (reply.includes("nome") || reply.includes("telefone") || reply.includes("contato")) {
    return {
      text: "Meu nome e Ana Paula e meu WhatsApp e (11) 99999-0000.",
      reason: "Paciente informou dados basicos solicitados.",
    };
  }
  if (reply.includes("unidade") || reply.includes("endereco") || reply.includes("bairro")) {
    return {
      text: "Pode ser na unidade principal, de preferencia no periodo da manha.",
      reason: "Paciente escolheu unidade e preferencia de periodo.",
    };
  }
  if (reply.includes("servico") || reply.includes("procedimento") || reply.includes("tratamento")) {
    return {
      text: "Quero uma avaliacao inicial para entender o melhor tratamento.",
      reason: "Paciente escolheu um servico inicial.",
    };
  }
  if (reply.includes("dia") || reply.includes("data") || reply.includes("semana")) {
    return {
      text: "Pode ser no proximo dia disponivel pela manha.",
      reason: "Paciente indicou preferencia de data.",
    };
  }
  if (reply.includes("horario") || reply.includes("manha") || reply.includes("tarde")) {
    if (reply.includes("nao esta disponivel") || reply.includes("não está disponível") || reply.includes("nao apareceu") || reply.includes("não apareceu")) {
      return {
        text: turnIndex % 2 === 0
          ? "Sem problema. Quais outros horários disponíveis você encontrou?"
          : "Pode me mandar outra opção disponível no mesmo período?",
        reason: "Paciente pediu nova opção porque o horário anterior não estava disponível.",
      };
    }
    return {
      text: turnIndex % 3 === 0
        ? "Pode ser o primeiro horário disponível que você encontrou."
        : turnIndex % 3 === 1
          ? "Prefiro o horário mais cedo que estiver disponível."
          : "Pode ser uma opção no fim da manhã, se tiver.",
      reason: "Paciente escolheu uma opção flexível sem repetir um horário indisponível.",
    };
  }
  if (reply.includes("confirm") || reply.includes("agend")) {
    return {
      text: "Sim, pode confirmar. Obrigada.",
      reason: "Paciente confirmou o encaminhamento.",
    };
  }
  if (nextAction !== "none") {
    return {
      text: "Pode seguir com essa opcao.",
      reason: `Paciente aceitou continuar a acao ${nextAction}.`,
    };
  }

  const maxTurns = Math.max(1, Number(options?.maxTurns || 6));
  const fallbackMessages = [
    "Entendi. Quais horarios voces tem disponiveis?",
    "Pode ser no periodo da manha. Qual unidade atende melhor?",
    "Quero entender tambem o tempo de atendimento e o que preciso levar.",
    "Se tiver horario livre, pode deixar encaminhado para confirmar.",
    "Perfeito. Pode me mandar um resumo do que ficou combinado?",
    "Obrigado. Se faltar alguma coisa para concluir, pode me orientar.",
  ];
  if (turnIndex < maxTurns - 1) {
    return {
      text: fallbackMessages[turnIndex % fallbackMessages.length],
      reason: options?.goalConclusion
        ? "Paciente manteve a conversa ate chegar em uma conclusao clara."
        : "Paciente pediu o proximo passo para manter a conversa fluindo.",
    };
  }
  return null;
}

function normalizeInteractiveOptions(value: unknown): InteractiveOption[] {
  if (!Array.isArray(value)) return [];
  return value
    .filter((item): item is InteractiveOption => {
      if (!item || typeof item !== "object") return false;
      const option = item as Record<string, unknown>;
      return typeof option.id === "string" && typeof option.title === "string";
    })
    .map((item) => ({
      id: item.id,
      title: item.title,
      description: typeof item.description === "string" ? item.description : undefined,
    }));
}

export default function IALabPage() {
  const queryClient = useQueryClient();

  const [message, setMessage] = useState("");
  const [contextText, setContextText] = useState("");
  const [includeKnowledge, setIncludeKnowledge] = useState(true);
  const [useTrainingExamples, setUseTrainingExamples] = useState(true);
  const [autoSaveHistory, setAutoSaveHistory] = useState(true);
  const [flowMode, setFlowMode] = useState<AILabFlowMode>("structured");

  const [selectedHistoryId, setSelectedHistoryId] = useState<string | null>(null);
  const [editedResponse, setEditedResponse] = useState("");
  const [note, setNote] = useState("");
  const [lastSimulation, setLastSimulation] = useState<AILabSimulateResponse | null>(null);
  const [autoConversationRunning, setAutoConversationRunning] = useState(false);
  const [autoConversationTurns, setAutoConversationTurns] = useState("6");
  const [autoConversationDirection, setAutoConversationDirection] = useState("");
  const [autoTranscript, setAutoTranscript] = useState<AutoTranscriptItem[]>([]);
  const [, setAutoConversationLabId] = useState<string | null>(null);
  const autoStopRequested = useRef(false);

  const historyQuery = useQuery<AILabHistoryResponse>({
    queryKey: ["ai-lab-history"],
    queryFn: async () => (await api.get("/settings/ai-lab/history", { params: { limit: 60 } })).data,
  });

  async function runSimulationRequest(
    inputMessage: string,
    inputContext: string,
    options?: {
      shouldSaveHistory?: boolean;
      persistConversation?: boolean;
      labConversationId?: string | null;
    },
  ) {
    return (
      await api.post<AILabSimulateResponse>("/settings/ai-lab/simulate", {
        message: inputMessage.trim(),
        context_text: inputContext.trim(),
        include_knowledge: includeKnowledge,
        use_training_examples: useTrainingExamples,
        auto_save_history: options?.shouldSaveHistory ?? autoSaveHistory,
        flow_mode: flowMode,
        persist_conversation: options?.persistConversation ?? false,
        lab_conversation_id: options?.labConversationId ?? null,
      })
    ).data;
  }

  const simulateMutation = useMutation({
    mutationFn: async () => runSimulationRequest(message.trim(), contextText.trim()),
    onSuccess: (result) => {
      setLastSimulation(result);
      setEditedResponse(result.response.reply_text || "");
      setNote("");
      setSelectedHistoryId(result.history_entry?.id ?? null);
      toast.success("Simulacao concluida sem envio no WhatsApp.");
      queryClient.invalidateQueries({ queryKey: ["ai-lab-history"] });
    },
    onError: (error: unknown) => {
      const apiMessage =
        typeof error === "object" &&
        error &&
        "response" in error &&
        typeof (error as { response?: { data?: { error?: { message?: string } } } }).response?.data?.error?.message === "string"
          ? (error as { response?: { data?: { error?: { message?: string } } } }).response?.data?.error?.message
          : null;
      toast.error(apiMessage || "Nao foi possivel simular a resposta da IA.");
    },
  });

  const saveEditMutation = useMutation({
    mutationFn: async () =>
      (
        await api.post<AILabHistoryItem>("/settings/ai-lab/history", {
          history_id: selectedHistoryId,
          input_text: lastSimulation?.input_text || message,
          edited_response_text: editedResponse,
          note: note.trim(),
        })
      ).data,
    onSuccess: (item) => {
      setSelectedHistoryId(item.id);
      toast.success("Edicao salva no historico de treino.");
      queryClient.invalidateQueries({ queryKey: ["ai-lab-history"] });
    },
    onError: (error: unknown) => {
      const apiMessage =
        typeof error === "object" &&
        error &&
        "response" in error &&
        typeof (error as { response?: { data?: { error?: { message?: string } } } }).response?.data?.error?.message === "string"
          ? (error as { response?: { data?: { error?: { message?: string } } } }).response?.data?.error?.message
          : null;
      toast.error(apiMessage || "Nao foi possivel salvar a edicao.");
    },
  });

  const clearHistoryMutation = useMutation({
    mutationFn: async () => (await api.delete<{ removed: number }>("/settings/ai-lab/history")).data,
    onSuccess: (result) => {
      toast.success(`Historico limpo (${result.removed} registro(s)).`);
      queryClient.invalidateQueries({ queryKey: ["ai-lab-history"] });
    },
    onError: () => toast.error("Nao foi possivel limpar o historico."),
  });

  const historyItems = historyQuery.data?.data ?? [];
  const currentContractStatus = lastSimulation?.contract_valid ? "Contrato valido" : "Contrato invalido";
  const canRunSimulation = message.trim().length > 0;
  const canSaveEdit = editedResponse.trim().length > 0;

  const lastModelName = useMemo(() => {
    const metadata = lastSimulation?.metadata;
    if (!metadata || typeof metadata !== "object") return "Nao informado";
    const provider = typeof metadata.provider === "string" ? metadata.provider : "desconhecido";
    const model = typeof metadata.model === "string" ? metadata.model : "desconhecido";
    return `${provider} / ${model}`;
  }, [lastSimulation?.metadata]);
  const lastProvider = useMemo(() => {
    const metadata = lastSimulation?.metadata;
    if (!metadata || typeof metadata !== "object") return "";
    return typeof metadata.provider === "string" ? metadata.provider : "";
  }, [lastSimulation?.metadata]);
  const isMockProvider = lastProvider === "mock";
  const interactivePreview = lastSimulation?.interactive_preview ?? null;
  const interactiveRows = normalizeInteractiveOptions(interactivePreview?.rows);
  const interactiveButtons = normalizeInteractiveOptions(interactivePreview?.buttons);
  const structuredFlow = lastSimulation?.structured_flow ?? null;
  const structuredDecision = asRecord(structuredFlow?.extractor?.decision);
  const structuredActionResult = asRecord(structuredFlow?.system_action_result);
  const structuredPlan = asRecord(structuredFlow?.safe_persistence_plan);
  const structuredReply = asRecord(structuredFlow?.patient_reply);

  async function handleStartAutoConversation() {
    const directionText = autoConversationDirection.trim();
    const goalConclusion = autoConversationTurns === "conclusion";
    const maxTurns = goalConclusion ? 20 : Math.max(1, Number(autoConversationTurns || 6));
    const initialMessage = message.trim() || (directionText ? `Oi, quero ajuda com isso: ${directionText}` : AUTO_CONVERSATION_STARTER);
    autoStopRequested.current = false;
    setAutoConversationRunning(true);
    setAutoTranscript([]);
    setAutoConversationLabId(null);

    const transcript: AutoTranscriptItem[] = [];
    const appendTranscript = (item: AutoTranscriptItem) => {
      transcript.push(item);
      setAutoTranscript([...transcript]);
    };

    let currentMessage = initialMessage;
    let currentLabConversationId: string | null = null;
    let currentContext =
      contextText.trim() ||
      "[LAB] Fluxo automatico iniciado no IA Lab. Simule cliente e clinica sem envio real.";
    if (directionText || goalConclusion) {
      currentContext = buildAutomaticContext([], currentContext, directionText, goalConclusion);
    }

    try {
      for (let turnIndex = 0; turnIndex < maxTurns; turnIndex += 1) {
        if (autoStopRequested.current) break;

        setMessage(currentMessage);
        setContextText(currentContext);
        appendTranscript(makeTranscriptItem("patient", currentMessage, `Turno ${turnIndex + 1}`));

        const result = await runSimulationRequest(currentMessage, currentContext, {
          persistConversation: true,
          labConversationId: currentLabConversationId,
        });
        currentLabConversationId = result.lab_conversation_id || currentLabConversationId;
        setAutoConversationLabId(currentLabConversationId);
        setLastSimulation(result);
        setEditedResponse(result.response.reply_text || "");
        setNote("");
        setSelectedHistoryId(result.history_entry?.id ?? null);
        appendTranscript(
          makeTranscriptItem(
            "clinic",
            result.response.reply_text || "A IA nao retornou texto.",
            result.response.next_action ? `Acao: ${result.response.next_action}` : undefined,
          ),
        );

        if (goalConclusion && isConversationConclusion(result, turnIndex)) {
          appendTranscript(
            makeTranscriptItem(
              "system",
              "Conclusao detectada: a conversa chegou em um fechamento claro antes do limite de 20 turnos.",
            ),
          );
          break;
        }

        const nextPatientMessage = deriveNextPatientMessage(result, turnIndex, {
          directionText,
          goalConclusion,
          maxTurns,
        });
        if (!nextPatientMessage) {
          appendTranscript(
            makeTranscriptItem(
              "system",
              "Fluxo automatico concluido: a resposta nao exigiu novo passo claro do paciente.",
            ),
          );
          break;
        }

        currentMessage = nextPatientMessage.text;
        currentContext = buildAutomaticContext(transcript, nextPatientMessage.reason, directionText, goalConclusion);
        await wait(850);
      }

      if (autoStopRequested.current) {
        appendTranscript(makeTranscriptItem("system", "Conversa automatica pausada pelo usuario."));
      }
      toast.success("Conversa automatica finalizada no IA Lab.");
      queryClient.invalidateQueries({ queryKey: ["ai-lab-history"] });
    } catch (error: unknown) {
      const apiMessage =
        typeof error === "object" &&
        error &&
        "response" in error &&
        typeof (error as { response?: { data?: { error?: { message?: string } } } }).response?.data?.error?.message === "string"
          ? (error as { response?: { data?: { error?: { message?: string } } } }).response?.data?.error?.message
          : null;
      appendTranscript(makeTranscriptItem("system", apiMessage || "Nao foi possivel continuar a conversa automatica."));
      toast.error(apiMessage || "Nao foi possivel continuar a conversa automatica.");
    } finally {
      autoStopRequested.current = false;
      setAutoConversationRunning(false);
    }
  }

  function handleStopAutoConversation() {
    autoStopRequested.current = true;
  }

  function handleInteractiveOptionAsNextMessage(option: InteractiveOption) {
    const selectedText = `Seleciono: ${option.title || option.id} (${option.id})`;
    const previousReply = lastSimulation?.response?.reply_text || editedResponse || "";
    const nextAction = lastSimulation?.response?.next_action || interactivePreview?.action || "none";
    setMessage(selectedText);
    setContextText(
      [
        "[LAB] Continuacao de uma simulacao anterior sem WhatsApp.",
        `Acao anterior: ${nextAction}.`,
        previousReply ? `Resposta anterior da IA: ${previousReply}` : "",
        `Opcao selecionada na lista: ${option.title} (${option.id}).`,
        option.description ? `Descricao da opcao: ${option.description}.` : "",
      ]
        .filter(Boolean)
        .join("\n")
    );
    toast.success("Opcao carregada como proxima mensagem da simulacao.");
  }

  if (historyQuery.isLoading) return <LoadingState message="Carregando laboratorio de IA..." />;
  if (historyQuery.isError) return <ErrorState message="Nao foi possivel carregar o IA Lab." />;

  return (
    <div className="space-y-4">
      <PageHeader
        eyebrow="Laboratorio"
        title="IA Lab (Sem WhatsApp)"
        description="Teste, ajuste e treine respostas da IA sem disparar envio real. As edicoes aprovadas entram como exemplos no prompt de producao."
        meta={
          <Badge className="bg-emerald-100 text-emerald-700">
            no_dispatch ativo
          </Badge>
        }
      />

      <Card className="border-blue-200 bg-blue-50">
        <CardContent className="space-y-2 p-3 text-sm text-blue-900">
          <p className="font-semibold">Impacto em producao</p>
          <p className="text-xs">
            Simular aqui nunca envia WhatsApp. Quando voce salva uma resposta editada, ela vira exemplo aprovado para orientar o auto-responder real.
          </p>
          <div className="flex flex-wrap gap-2">
            {GOLDEN_SCENARIOS.map((scenario) => (
              <Button
                key={scenario}
                variant="outline"
                className="h-8 border-blue-200 bg-white px-3 text-xs text-blue-800"
                onClick={() => setMessage(scenario)}
              >
                {scenario}
              </Button>
            ))}
          </div>
        </CardContent>
      </Card>

      <Card className="overflow-hidden border-emerald-200 bg-gradient-to-br from-emerald-50 via-white to-cyan-50 shadow-sm">
        <CardContent className="space-y-4 p-4">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="max-w-2xl">
              <div className="inline-flex items-center gap-2 rounded-full bg-emerald-100 px-3 py-1 text-xs font-bold uppercase tracking-wide text-emerald-800">
                <Bot size={14} />
                Conversa automatica
              </div>
              <h2 className="mt-2 text-xl font-black text-stone-950">Simular cliente e clinica em fluxo continuo</h2>
              <p className="mt-1 text-sm text-stone-600">
                Ligue o modo automatico para o paciente virtual responder sozinho. A IA da clinica continua usando as informacoes salvas e nada e enviado no WhatsApp real.
              </p>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <select
                className="h-10 rounded-xl border border-emerald-200 bg-white px-3 text-sm font-semibold text-emerald-900 outline-none transition focus:border-emerald-500 focus:ring-2 focus:ring-emerald-200"
                value={autoConversationTurns}
                disabled={autoConversationRunning}
                onChange={(event) => setAutoConversationTurns(event.target.value)}
                aria-label="Quantidade de turnos automaticos"
              >
                <option value={4}>4 turnos</option>
                <option value={6}>6 turnos</option>
                <option value={8}>8 turnos</option>
                <option value={10}>10 turnos</option>
                <option value={15}>15 turnos</option>
                <option value={20}>20 turnos</option>
                <option value="conclusion">Ate concluir</option>
              </select>
              <Button
                type="button"
                className="gap-2 bg-emerald-700 text-white hover:bg-emerald-800"
                onClick={autoConversationRunning ? handleStopAutoConversation : handleStartAutoConversation}
                disabled={simulateMutation.isPending}
              >
                {autoConversationRunning ? <Square size={14} /> : <Play size={14} />}
                {autoConversationRunning ? "Desligar fluxo" : "Ligar conversa"}
              </Button>
            </div>
          </div>

          <div className="grid gap-3 lg:grid-cols-[1.2fr_0.8fr]">
            <label className="space-y-1">
              <span className="text-xs font-bold uppercase tracking-wide text-emerald-800">
                Rumo da conversa
              </span>
              <textarea
                className="min-h-[86px] w-full rounded-2xl border border-emerald-200 bg-white/90 px-3 py-2 text-sm text-stone-800 outline-none transition placeholder:text-stone-400 focus:border-emerald-500 focus:ring-2 focus:ring-emerald-200"
                placeholder="Ex.: paciente pergunta formas de pagamento, insiste que aceita apenas Pix, depois tenta agendar para amanha de manha."
                value={autoConversationDirection}
                disabled={autoConversationRunning}
                onChange={(event) => setAutoConversationDirection(event.target.value)}
              />
            </label>
            <div className="rounded-2xl border border-emerald-100 bg-white/75 p-3 text-xs leading-relaxed text-stone-600">
              <p className="font-bold uppercase tracking-wide text-emerald-800">Como funciona</p>
              <p className="mt-1">
                Em turnos fixos, o fluxo tenta seguir ate a quantidade escolhida. Em Ate concluir, ele roda no maximo 20 turnos e para quando detectar agendamento, encaminhamento ou fechamento claro.
              </p>
            </div>
          </div>

          {autoTranscript.length > 0 ? (
            <div className="rounded-2xl border border-emerald-100 bg-white/85 p-3">
              <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                <p className="text-xs font-bold uppercase tracking-wide text-stone-500">Transcricao automatica</p>
                <Badge className={autoConversationRunning ? "bg-emerald-100 text-emerald-700" : "bg-stone-200 text-stone-700"}>
                  {autoConversationRunning ? "rodando agora" : "fluxo pausado"}
                </Badge>
              </div>
              <div className="whatsapp-chat-surface max-h-[360px] space-y-2 overflow-y-auto rounded-[22px] border border-emerald-100/70 p-3 pr-2">
                {autoTranscript.map((item) => {
                  const isPatient = item.role === "patient";
                  const isClinic = item.role === "clinic";
                  return (
                    <div
                      key={item.id}
                      className={`flex ${isPatient ? "justify-start" : isClinic ? "justify-end" : "justify-center"}`}
                    >
                      <div
                        className={`max-w-[86%] rounded-2xl px-3 py-2 text-sm shadow-sm ${
                          isPatient
                            ? "border border-blue-100 bg-blue-50 text-blue-950"
                            : isClinic
                              ? "border border-emerald-100 bg-emerald-600 text-white"
                              : "border border-stone-200 bg-stone-100 text-stone-600"
                        }`}
                      >
                        <div className="mb-1 flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wide opacity-80">
                          {isPatient ? <UserRound size={12} /> : isClinic ? <Bot size={12} /> : <Sparkles size={12} />}
                          {isPatient ? "Paciente virtual" : isClinic ? "Clinica IA" : "Sistema"}
                          {item.meta ? <span className="font-medium normal-case tracking-normal">- {item.meta}</span> : null}
                        </div>
                        <p className="whitespace-pre-wrap leading-relaxed">{item.text}</p>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          ) : (
            <p className="rounded-xl border border-dashed border-emerald-200 bg-white/70 p-3 text-sm text-stone-600">
              Dica: escreva uma primeira mensagem no campo Mensagem do paciente ou deixe vazio para usar um cenario padrao de agendamento.
            </p>
          )}
        </CardContent>
      </Card>

      <div className="grid gap-4 xl:grid-cols-2">
        <Card className="border-stone-200">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Beaker size={16} />
              Simulacao de Mensagem
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="space-y-1">
              <label className="text-xs font-semibold uppercase tracking-wide text-stone-500">
                Mensagem do paciente
              </label>
              <textarea
                className="min-h-[120px] w-full rounded-md border border-stone-300 bg-white px-3 py-2 text-sm outline-none transition focus:border-primary focus:ring-2 focus:ring-primary/20"
                placeholder="Ex.: Oi, quero agendar uma avaliacao para esta semana."
                value={message}
                onChange={(event) => setMessage(event.target.value)}
              />
            </div>

            <div className="space-y-1">
              <label className="text-xs font-semibold uppercase tracking-wide text-stone-500">
                Contexto extra (opcional)
              </label>
              <textarea
                className="min-h-[82px] w-full rounded-md border border-stone-300 bg-white px-3 py-2 text-sm outline-none transition focus:border-primary focus:ring-2 focus:ring-primary/20"
                placeholder="Ex.: paciente ja perguntou sobre clareamento e quer horario de manha."
                value={contextText}
                onChange={(event) => setContextText(event.target.value)}
              />
            </div>

            <div className="grid gap-2 sm:grid-cols-2">
              <label className="space-y-1 rounded-md border border-emerald-200 bg-emerald-50/70 px-2 py-2 text-xs text-emerald-900 sm:col-span-2">
                <span className="block font-semibold uppercase tracking-wide">
                  Fluxo da conversa
                </span>
                <select
                  className="mt-1 h-9 w-full rounded-md border border-emerald-200 bg-white px-2 text-sm font-semibold text-emerald-950 outline-none transition focus:border-emerald-500 focus:ring-2 focus:ring-emerald-200"
                  value={flowMode}
                  onChange={(event) => setFlowMode(event.target.value as AILabFlowMode)}
                  disabled={autoConversationRunning || simulateMutation.isPending}
                >
                  <option value="structured">Novo fluxo estruturado (recomendado)</option>
                  <option value="auto">Automatico pela configuracao do sistema</option>
                  <option value="legacy">Fluxo antigo</option>
                </select>
                <span className="block text-[11px] leading-relaxed text-emerald-800">
                  Use o estruturado para testar o fluxo novo. O automatico apenas segue a configuracao global atual e pode cair no antigo se a flag estiver desligada.
                </span>
              </label>
              <label className="inline-flex items-center gap-2 rounded-md border border-stone-200 px-2 py-2 text-xs text-stone-700">
                <input
                  type="checkbox"
                  checked={includeKnowledge}
                  onChange={(event) => setIncludeKnowledge(event.target.checked)}
                />
                Usar base de conhecimento
              </label>
              <label className="inline-flex items-center gap-2 rounded-md border border-stone-200 px-2 py-2 text-xs text-stone-700">
                <input
                  type="checkbox"
                  checked={useTrainingExamples}
                  onChange={(event) => setUseTrainingExamples(event.target.checked)}
                />
                Usar exemplos editados
              </label>
              <label className="inline-flex items-center gap-2 rounded-md border border-stone-200 px-2 py-2 text-xs text-stone-700 sm:col-span-2">
                <input
                  type="checkbox"
                  checked={autoSaveHistory}
                  onChange={(event) => setAutoSaveHistory(event.target.checked)}
                />
                Salvar simulacao automaticamente no historico
              </label>
            </div>

            <div className="flex flex-wrap gap-2">
              <Button
                onClick={() => simulateMutation.mutate()}
                disabled={!canRunSimulation || simulateMutation.isPending || autoConversationRunning}
                className="gap-1.5"
              >
                <Sparkles size={14} />
                {simulateMutation.isPending ? "Simulando..." : "Simular resposta IA"}
              </Button>
              <Button
                variant="outline"
                onClick={() => {
                  setMessage("");
                  setContextText("");
                  setLastSimulation(null);
                  setEditedResponse("");
                  setSelectedHistoryId(null);
                  setNote("");
                }}
                disabled={autoConversationRunning}
                className="gap-1.5"
              >
                <Eraser size={14} />
                Limpar editor
              </Button>
            </div>
          </CardContent>
        </Card>

        <Card className="border-stone-200">
          <CardHeader>
            <CardTitle>Resposta da IA (Editavel)</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="flex flex-wrap items-center gap-2">
              <Badge className={lastSimulation?.contract_valid ? "bg-emerald-100 text-emerald-700" : "bg-amber-100 text-amber-800"}>
                {currentContractStatus}
              </Badge>
              {lastSimulation?.contract_retried ? (
                <Badge className="bg-stone-200 text-stone-700">tentativa extra aplicada</Badge>
              ) : null}
              <Badge className="bg-stone-200 text-stone-700">modelo: {lastModelName}</Badge>
              <Badge className={lastSimulation?.flow_mode === "structured" ? "bg-emerald-100 text-emerald-700" : "bg-stone-200 text-stone-700"}>
                fluxo: {lastSimulation?.flow_mode === "structured" ? "estruturado" : "antigo"}
              </Badge>
              <Badge className="bg-blue-100 text-blue-700">no_dispatch: sim</Badge>
              {lastSimulation?.no_persistence ? (
                <Badge className="bg-blue-100 text-blue-700">sem persistencia operacional</Badge>
              ) : null}
              {lastSimulation?.training_examples_used ? (
                <Badge className="bg-emerald-100 text-emerald-700">treino aplicado</Badge>
              ) : null}
              {lastSimulation?.custom_prompt_used ? (
                <Badge className="bg-emerald-100 text-emerald-700">prompt editavel aplicado</Badge>
              ) : null}
              {lastSimulation?.knowledge_context_used ? (
                <Badge className="bg-blue-100 text-blue-700">base/unidades aplicadas</Badge>
              ) : null}
            </div>

            {lastSimulation && isMockProvider ? (
              <p className="rounded-md border border-blue-200 bg-blue-50 p-2 text-xs text-blue-800">
                Este resultado esta usando o provider mock. Ele serve para validar contrato e fluxo, mas nao tem criatividade de IA real. Para respostas realmente naturais, configure LLM_PROVIDER=openai e LLM_API_KEY.
              </p>
            ) : null}

            {lastSimulation && !lastSimulation.contract_valid ? (
              <p className="rounded-md border border-amber-200 bg-amber-50 p-2 text-xs text-amber-800">
                A resposta nao passou no contrato JSON. Ajuste a resposta aprovada e salve para treinar, ou revise o provider/prompt antes de usar em producao.
              </p>
            ) : null}

            <div className="grid gap-2 sm:grid-cols-3">
              <Input
                readOnly
                value={lastSimulation?.intent?.intent || "n/a"}
                placeholder="Intent"
              />
              <Input
                readOnly
                value={String(lastSimulation?.response?.next_action || "none")}
                placeholder="next_action"
              />
              <Input
                readOnly
                value={
                  typeof lastSimulation?.response?.confidence === "number"
                    ? String(lastSimulation.response.confidence)
                    : "n/a"
                }
                placeholder="confidence"
              />
            </div>

            {lastSimulation && structuredFlow ? (
              <div className="rounded-2xl border border-emerald-200 bg-gradient-to-br from-emerald-50 via-white to-cyan-50 p-3">
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div>
                    <p className="text-xs font-bold uppercase tracking-wide text-emerald-800">
                      Fluxo estruturado validado
                    </p>
                    <p className="mt-1 text-xs leading-relaxed text-stone-600">
                      O IA Lab mostra o que a IA extraiu, o que o backend permitiria salvar e qual acao seria consultada. Nesta tela nada e enviado nem gravado em paciente, conversa ou agenda.
                    </p>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <Badge className={structuredFlow.extractor?.contract_valid ? "bg-emerald-100 text-emerald-700" : "bg-amber-100 text-amber-800"}>
                      extracao: {structuredFlow.extractor?.contract_valid ? "valida" : "falhou"}
                    </Badge>
                    <Badge className="bg-white text-emerald-700">
                      schema {structuredFlow.schema_version || "1.0"}
                    </Badge>
                  </div>
                </div>

                <div className="mt-3 grid gap-3 lg:grid-cols-3">
                  <div className="rounded-xl border border-white bg-white/80 p-3 shadow-sm">
                    <p className="text-[11px] font-bold uppercase tracking-wide text-stone-500">Extracao</p>
                    <p className="mt-1 text-sm font-semibold text-stone-900">
                      Intent: {String(structuredDecision?.intent || "n/a")}
                    </p>
                    <p className="text-xs text-stone-600">
                      Confianca: {String(structuredDecision?.confidence ?? "n/a")}
                    </p>
                    <p className="text-xs text-stone-600">
                      Acao: {String(structuredActionResult?.action || lastSimulation.response.next_action || "none")}
                    </p>
                    {structuredFlow.extractor?.error ? (
                      <p className="mt-2 rounded-md border border-amber-200 bg-amber-50 p-2 text-xs text-amber-800">
                        {structuredFlow.extractor.error}
                      </p>
                    ) : null}
                  </div>

                  <div className="rounded-xl border border-white bg-white/80 p-3 shadow-sm">
                    <p className="text-[11px] font-bold uppercase tracking-wide text-stone-500">Plano seguro</p>
                    <p className="mt-1 text-sm font-semibold text-stone-900">
                      Updates: {Object.keys(asRecord(structuredPlan?.safe_updates) || {}).length}
                    </p>
                    <p className="text-xs text-stone-600">
                      Flags de risco: {Array.isArray(structuredPlan?.risk_flags) ? structuredPlan?.risk_flags.length : 0}
                    </p>
                    <p className="mt-2 text-xs leading-relaxed text-emerald-800">
                      Criado pelo backend. A IA apenas sugere; o banco nao e alterado durante a simulacao.
                    </p>
                  </div>

                  <div className="rounded-xl border border-white bg-white/80 p-3 shadow-sm">
                    <p className="text-[11px] font-bold uppercase tracking-wide text-stone-500">Resposta final</p>
                    <p className="mt-1 text-sm font-semibold text-stone-900">
                      Decisao: {String(structuredReply?.final_decision || "reply")}
                    </p>
                    <p className="text-xs text-stone-600">
                      Tipo: {String(structuredReply?.message_type || "text")}
                    </p>
                    <p className="mt-2 text-xs leading-relaxed text-stone-600">
                      Resultado gerado depois da validacao e da acao de sistema simulada.
                    </p>
                  </div>
                </div>

                <div className="mt-3 grid gap-2 lg:grid-cols-2">
                  <details className="rounded-xl border border-emerald-100 bg-white/80 p-2">
                    <summary className="cursor-pointer text-xs font-semibold uppercase tracking-wide text-emerald-800">
                      Ver AiDecisionOutput
                    </summary>
                    <pre className="mt-2 max-h-72 overflow-auto whitespace-pre-wrap text-xs text-stone-700">
                      {prettyJson(structuredDecision)}
                    </pre>
                  </details>
                  <details className="rounded-xl border border-emerald-100 bg-white/80 p-2">
                    <summary className="cursor-pointer text-xs font-semibold uppercase tracking-wide text-emerald-800">
                      Ver SafePersistencePlan
                    </summary>
                    <pre className="mt-2 max-h-72 overflow-auto whitespace-pre-wrap text-xs text-stone-700">
                      {prettyJson(structuredPlan)}
                    </pre>
                  </details>
                  <details className="rounded-xl border border-emerald-100 bg-white/80 p-2">
                    <summary className="cursor-pointer text-xs font-semibold uppercase tracking-wide text-emerald-800">
                      Ver acao de sistema
                    </summary>
                    <pre className="mt-2 max-h-72 overflow-auto whitespace-pre-wrap text-xs text-stone-700">
                      {prettyJson(structuredActionResult)}
                    </pre>
                  </details>
                  <details className="rounded-xl border border-emerald-100 bg-white/80 p-2">
                    <summary className="cursor-pointer text-xs font-semibold uppercase tracking-wide text-emerald-800">
                      Ver contexto limpo
                    </summary>
                    <pre className="mt-2 max-h-72 overflow-auto whitespace-pre-wrap text-xs text-stone-700">
                      {prettyJson(structuredFlow.context_preview)}
                    </pre>
                  </details>
                </div>
              </div>
            ) : null}

            {lastSimulation && interactivePreview ? (
              <div className="rounded-xl border border-emerald-200 bg-emerald-50/70 p-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div>
                    <p className="text-xs font-semibold uppercase tracking-wide text-emerald-800">
                      Previa WhatsApp interativa
                    </p>
                    <p className="text-xs text-emerald-700">
                      Esta lista/botoes nao envia nada; serve para simular o menu completo.
                    </p>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <Badge className="bg-white text-emerald-700">
                      {interactivePreview.interactive_type === "buttons" ? "botoes" : "lista"}
                    </Badge>
                    {interactivePreview.action ? (
                      <Badge className="bg-white text-emerald-700">acao: {interactivePreview.action}</Badge>
                    ) : null}
                  </div>
                </div>

                <div className="mt-3 rounded-lg border border-emerald-100 bg-white p-3">
                  {interactivePreview.header_text ? (
                    <p className="text-xs font-semibold uppercase tracking-wide text-stone-500">
                      {interactivePreview.header_text}
                    </p>
                  ) : null}
                  {interactivePreview.body_text ? (
                    <p className="mt-1 whitespace-pre-wrap text-sm text-stone-800">
                      {interactivePreview.body_text}
                    </p>
                  ) : null}

                  {interactiveRows.length > 0 ? (
                    <div className="mt-3 space-y-2">
                      <div className="flex items-center justify-between gap-2">
                        <span className="text-xs font-semibold uppercase tracking-wide text-stone-500">
                          {interactivePreview.section_title || "Opcoes"}
                        </span>
                        <span className="rounded-full bg-emerald-100 px-2 py-1 text-[11px] font-semibold text-emerald-700">
                          Botao: {interactivePreview.button_title || "Opcoes"}
                        </span>
                      </div>
                      {interactiveRows.map((row, index) => (
                        <button
                          key={`${row.id}-${index}`}
                          type="button"
                          className="w-full rounded-lg border border-stone-200 bg-stone-50 px-3 py-2 text-left transition hover:border-emerald-300 hover:bg-emerald-50"
                          onClick={() => handleInteractiveOptionAsNextMessage(row)}
                        >
                          <span className="block text-sm font-semibold text-stone-800">
                            {index + 1}. {row.title}
                          </span>
                          {row.description ? (
                            <span className="mt-0.5 block text-xs text-stone-600">{row.description}</span>
                          ) : null}
                          <span className="mt-1 block text-[11px] text-stone-400">id: {row.id}</span>
                        </button>
                      ))}
                    </div>
                  ) : null}

                  {interactiveButtons.length > 0 ? (
                    <div className="mt-3 flex flex-wrap gap-2">
                      {interactiveButtons.map((button, index) => (
                        <Button
                          key={`${button.id}-${index}`}
                          type="button"
                          variant="outline"
                          className="h-9 border-emerald-200 bg-emerald-50 text-xs text-emerald-800"
                          onClick={() => handleInteractiveOptionAsNextMessage(button)}
                        >
                          {button.title}
                        </Button>
                      ))}
                    </div>
                  ) : null}

                  {interactivePreview.footer_text ? (
                    <p className="mt-3 text-xs text-stone-500">{interactivePreview.footer_text}</p>
                  ) : null}
                </div>
              </div>
            ) : lastSimulation ? (
              <p className="rounded-md border border-stone-200 bg-stone-50 p-2 text-xs text-stone-600">
                Esta resposta nao gerou lista/botoes. No fluxo antigo isso depende de acoes como show_clinics, show_services, show_plans ou open_booking. No fluxo estruturado, depende de PatientReplyOutput com message_type interactive.
              </p>
            ) : null}

            <div className="space-y-1">
              <label className="text-xs font-semibold uppercase tracking-wide text-stone-500">
                Resposta editada para treino
              </label>
              <textarea
                className="min-h-[140px] w-full rounded-md border border-stone-300 bg-white px-3 py-2 text-sm outline-none transition focus:border-primary focus:ring-2 focus:ring-primary/20"
                placeholder="Ajuste aqui a resposta final que voce aprova para este tipo de mensagem."
                value={editedResponse}
                onChange={(event) => setEditedResponse(event.target.value)}
              />
            </div>

            <div className="space-y-1">
              <label className="text-xs font-semibold uppercase tracking-wide text-stone-500">
                Nota opcional de treino
              </label>
              <Input
                placeholder="Ex.: usar tom mais consultivo e convidar para proximo passo."
                value={note}
                onChange={(event) => setNote(event.target.value)}
              />
            </div>

            <div className="flex flex-wrap gap-2">
              <Button
                onClick={() => saveEditMutation.mutate()}
                disabled={!canSaveEdit || saveEditMutation.isPending}
                className="gap-1.5"
              >
                <Save size={14} />
                {saveEditMutation.isPending ? "Salvando..." : "Salvar edicao"}
              </Button>
              <Button
                variant="outline"
                onClick={() => clearHistoryMutation.mutate()}
                disabled={clearHistoryMutation.isPending || historyItems.length === 0}
                className="gap-1.5"
              >
                <Trash2 size={14} />
                Limpar historico
              </Button>
            </div>

            {lastSimulation ? (
              <details className="rounded-md border border-stone-200 bg-stone-50 p-2">
                <summary className="cursor-pointer text-xs font-semibold uppercase tracking-wide text-stone-600">
                  Ver saida bruta da IA
                </summary>
                <pre className="mt-2 overflow-x-auto whitespace-pre-wrap text-xs text-stone-700">
                  {lastSimulation.raw_output || "(vazio)"}
                </pre>
              </details>
            ) : (
              <p className="text-xs text-stone-500">
                Rode uma simulacao para visualizar e editar a resposta da IA.
              </p>
            )}
          </CardContent>
        </Card>
      </div>

      <Card className="border-stone-200">
        <CardHeader>
          <CardTitle>Historico de treino</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {historyItems.length === 0 ? (
            <p className="text-sm text-stone-500">Sem registros ainda. Execute uma simulacao para iniciar.</p>
          ) : (
            historyItems.map((item) => (
              <div key={item.id} className="rounded-md border border-stone-200 bg-stone-50 p-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge className={item.contract_valid ? "bg-emerald-100 text-emerald-700" : "bg-amber-100 text-amber-800"}>
                      {item.contract_valid ? "Contrato valido" : "Contrato invalido"}
                    </Badge>
                    <Badge className={item.metadata?.flow_mode === "structured" ? "bg-emerald-100 text-emerald-700" : "bg-stone-200 text-stone-700"}>
                      fluxo: {item.metadata?.flow_mode === "structured" ? "estruturado" : "antigo"}
                    </Badge>
                    <Badge className="bg-stone-200 text-stone-700">acao: {item.ai_next_action || "none"}</Badge>
                  </div>
                  <span className="text-xs text-stone-500">{formatDateTimeBR(item.created_at)}</span>
                </div>

                <p className="mt-2 text-xs font-semibold uppercase tracking-wide text-stone-500">Entrada</p>
                <p className="text-sm text-stone-700">{item.input_text}</p>

                {item.ai_reply_text ? (
                  <>
                    <p className="mt-2 text-xs font-semibold uppercase tracking-wide text-stone-500">Resposta IA</p>
                    <p className="text-sm text-stone-700">{item.ai_reply_text}</p>
                  </>
                ) : null}

                {item.edited_response_text ? (
                  <>
                    <p className="mt-2 text-xs font-semibold uppercase tracking-wide text-stone-500">Resposta aprovada</p>
                    <p className="text-sm text-stone-800">{item.edited_response_text}</p>
                  </>
                ) : null}

                {item.note ? (
                  <p className="mt-2 text-xs text-stone-600">Nota: {item.note}</p>
                ) : null}

                <div className="mt-2">
                  <Button
                    variant="outline"
                    className="h-8 px-3 text-xs"
                    onClick={() => {
                      setMessage(item.input_text || "");
                      setContextText(item.context_text || "");
                      setEditedResponse(item.edited_response_text || item.ai_reply_text || "");
                      setNote(item.note || "");
                      setSelectedHistoryId(item.id);
                      setLastSimulation(null);
                      toast.success("Registro carregado no editor.");
                    }}
                  >
                    Usar no editor
                  </Button>
                </div>
              </div>
            ))
          )}
        </CardContent>
      </Card>
    </div>
  );
}

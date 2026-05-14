from __future__ import annotations

import re
import time
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.integrations.llm.provider_factory import LLMProviderFactory
from app.models import (
    Appointment,
    Conversation,
    LLMInteraction,
    Lead,
    Patient,
    Professional,
    Setting,
    Tenant,
    Unit,
)


SUPPORT_KNOWLEDGE_VERSION = "odontoflux-support-2026-04-27.2"


@dataclass(frozen=True)
class SupportChunk:
    id: str
    title: str
    body: str
    keywords: tuple[str, ...] = ()


SYSTEM_SUPPORT_CHUNKS: tuple[SupportChunk, ...] = (
    SupportChunk(
        "agenda.operacional",
        "Agenda operacional",
        (
            "A página Agenda mostra a grade semanal por dia, profissional e unidade. Permite criar consulta ao clicar "
            "em horário disponível, editar consulta ocupada, confirmar, reagendar, excluir, registrar comparecimento, "
            "registrar o que aconteceu na consulta e marcar se precisa de retorno. O reagendamento inteligente deve "
            "mostrar horários realmente livres considerando serviço, duração, unidade e todos os profissionais aptos, "
            "não apenas o profissional original. Em tela cheia, a agenda tem navegação discreta e botões flutuantes."
        ),
        ("agenda", "agendamento", "consulta", "reagendar", "retorno", "compareceu", "horario", "tela cheia"),
    ),
    SupportChunk(
        "conversas.whatsapp",
        "Inbox de WhatsApp",
        (
            "A pagina WhatsApp centraliza atendimento, mensagens abertas/finalizadas/nao respondidas, filtros "
            "por unidade, responsável e prioridade. A sugestão IA pode usar apenas a conversa ou usar um texto digitado "
            "como instrução extra. A sugestão gerada pode preencher a caixa de mensagem. O envio de mensagem usa o ícone "
            "compacto para deixar a caixa de texto maior."
        ),
        ("conversa", "whatsapp", "mensagem", "sugestao ia", "inbox", "anexo", "nota interna"),
    ),
    SupportChunk(
        "ia.autoresponder",
        "IA Auto-Responder",
        (
            "A IA Auto-Responder usa o conhecimento cadastrado em Configurações > Conhecimento IA, catálogo oficial de "
            "serviços, unidades, profissionais, regras de agenda e políticas operacionais. Deve responder dúvidas, "
            "agendar, reagendar, identificar intenção e encaminhar para humano quando faltar confiança ou envolver tema "
            "clínico/sensível. A IA não deve inventar endereço, preço, telefone, disponibilidade ou regra não cadastrada."
        ),
        ("ia", "auto responder", "autoresponder", "openai", "intencao", "faq", "conhecimento"),
    ),
    SupportChunk(
        "configuracoes.tema",
        "Tema e Marca",
        (
            "Configurações > Tema e Marca controla cores principais, fundo geral, fundo sutil, cards, textos, bordas, "
            "logo da clínica e cores do modo tela cheia. A alteração deve refletir no topo, sidebar, cards, botões, "
            "superfícies e telas em fullscreen."
        ),
        ("tema", "marca", "cor", "logo", "fullscreen", "tela cheia", "visual"),
    ),
    SupportChunk(
        "configuracoes.servicos",
        "Serviços da clínica",
        (
            "Serviços organiza o catálogo oficial em cards. Cada serviço deve ter nome, duração, faixa "
            "de preço, status e descrição. Criar e editar abrem drawer/card próprio; remover/excluir controla o catálogo. "
            "O catálogo alimenta Agenda, Equipe médica e IA."
        ),
        ("servico", "catalogo", "procedimento", "preco", "duracao", "descricao"),
    ),
    SupportChunk(
        "equipe.medica",
        "Equipe médica e profissionais",
        (
            "Equipe médica lista profissionais por unidade com expediente, dias de atendimento, especialidade, CRO e "
            "serviços atendidos. Deve ter botões para editar e excluir profissional e botão para cadastrar novo "
            "profissional abrindo o mesmo formulário em modo criação."
        ),
        ("profissional", "medico", "dentista", "equipe", "cro", "expediente", "dias"),
    ),
    SupportChunk(
        "pacientes.prontuario",
        "Pacientes e histórico",
        (
            "Pacientes concentra dados cadastrais, status, conversas, documentos, agendamentos e histórico operacional. "
            "Ao abrir uma consulta é possível acessar o resumo do paciente, registrar observações e acompanhar retornos."
        ),
        ("paciente", "historico", "prontuario", "documento", "cpf", "telefone"),
    ),
    SupportChunk(
        "leads.crm",
        "Leads",
        (
            "Leads organiza oportunidades com busca, etapa, score, temperatura, responsável, ações de conversa, follow-up "
            "e conversão. A organização deve priorizar leitura em cards/tabela sem colunas quebradas."
        ),
        ("lead", "funil", "temperatura", "score", "follow-up", "converter"),
    ),
    SupportChunk(
        "adm.prospeccao",
        "Admin /adm e demos comerciais",
        (
            "A área /adm é interna e separada do cliente. Funciona como CRM comercial, cadastro de clínicas prospectadas, "
            "pipeline, geração de demo personalizada, tenant isolado por clínica, magic link/senha temporária, tracking "
            "de atividade, score comercial, playbook, proposta, ROI e revogação/expiração de acesso. O cliente demo só "
            "pode ver o próprio tenant."
        ),
        ("adm", "prospect", "demo", "tenant", "pipeline", "score comercial", "magic link", "comercial"),
    ),
    SupportChunk(
        "seguranca.lgpd",
        "Segurança, LGPD e permissões",
        (
            "Configurações > Segurança reúne timeout, MFA futura, sessão, auditoria e exportações sensíveis. Dados e "
            "Privacidade reúne consentimento, retenção, permissões de comunicação, exportação, anonimização e solicitações "
            "LGPD. Usuários possuem permissões por página e podem ser restritos a modo tela cheia."
        ),
        ("seguranca", "lgpd", "privacidade", "mfa", "permissao", "usuario", "auditoria"),
    ),
    SupportChunk(
        "suporte.ia",
        "Suporte IA do OdontoFlux",
        (
            "O suporte IA deve responder dúvidas operacionais sobre o próprio OdontoFlux usando conhecimento versionado "
            "do produto, documentação do repositório quando disponível e dados do tenant logado. Quando não houver base "
            "suficiente, deve dizer que não encontrou a informação com segurança e indicar o caminho mais provável ou "
            "abrir incidente de suporte."
        ),
        ("suporte", "ajuda", "duvida", "sistema", "como usar", "erro"),
    ),
)


def _normalize(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    return "".join(char for char in normalized if not unicodedata.combining(char)).lower()


def _tokenize(value: str) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9_/-]{3,}", _normalize(value)) if len(token) >= 3}


def _clip(value: str, limit: int = 1200) -> str:
    text = re.sub(r"\s+", " ", (value or "").strip())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _read_setting_value(raw: object) -> object:
    if isinstance(raw, dict) and set(raw.keys()) == {"value"}:
        return raw.get("value")
    return raw


def _safe_count(db: Session, model: object, tenant_id: UUID) -> int:
    try:
        return int(db.scalar(select(func.count()).select_from(model).where(model.tenant_id == tenant_id)) or 0)
    except Exception:
        return 0


def _repo_root_candidates() -> list[Path]:
    here = Path(__file__).resolve()
    return [
        here.parents[4] if len(here.parents) > 4 else here.parent,
        here.parents[3] if len(here.parents) > 3 else here.parent,
        Path("/workspace"),
        Path.cwd(),
    ]


@lru_cache(maxsize=1)
def _load_doc_chunks() -> tuple[SupportChunk, ...]:
    docs: list[SupportChunk] = []
    wanted = {
        "README.md",
        "operations.md",
        "whatsapp-setup.md",
        "troubleshooting.md",
        "message-flow.md",
        "incidentes-e-sla.md",
        "adm-prospeccao-demos.md",
        "suporte-ia-odontoflux.md",
        "architecture.md",
        "data-model.md",
    }

    seen_paths: set[Path] = set()
    for root in _repo_root_candidates():
        docs_dir = root / "docs"
        if not docs_dir.exists():
            continue
        for path in docs_dir.glob("*.md"):
            if path.name not in wanted or path in seen_paths:
                continue
            seen_paths.add(path)
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            title = next((line.lstrip("# ").strip() for line in text.splitlines() if line.startswith("#")), path.stem)
            docs.append(
                SupportChunk(
                    id=f"doc.{path.stem}",
                    title=f"Doc: {title}",
                    body=_clip(text, 1600),
                    keywords=(path.stem.replace("-", " "),),
                )
            )
    return tuple(docs)


def _build_tenant_chunks(db: Session, tenant_id: UUID) -> list[SupportChunk]:
    tenant = db.scalar(select(Tenant).where(Tenant.id == tenant_id))
    units = db.execute(select(Unit).where(Unit.tenant_id == tenant_id).order_by(Unit.name).limit(20)).scalars().all()
    professionals = (
        db.execute(select(Professional).where(Professional.tenant_id == tenant_id).order_by(Professional.full_name).limit(30))
        .scalars()
        .all()
    )
    settings_rows = db.execute(select(Setting).where(Setting.tenant_id == tenant_id)).scalars().all()
    setting_map = {row.key: _read_setting_value(row.value) for row in settings_rows if not row.is_secret}

    service_config = setting_map.get("service-catalog/config")
    if not isinstance(service_config, dict):
        service_config = setting_map.get("service_catalog.global")
    service_items = service_config.get("items") if isinstance(service_config, dict) else []
    service_names = [
        str(item.get("name") or item.get("service_name"))
        for item in service_items
        if isinstance(item, dict) and (item.get("is_active", True) is not False) and (item.get("name") or item.get("service_name"))
    ][:20]

    ai_config = setting_map.get("ai-autoresponder/config")
    ai_knowledge = setting_map.get("ai-knowledge-base/config")
    clinic_profile = setting_map.get("clinic.profile")

    counts = {
        "pacientes": _safe_count(db, Patient, tenant_id),
        "conversas": _safe_count(db, Conversation, tenant_id),
        "agenda": _safe_count(db, Appointment, tenant_id),
        "leads": _safe_count(db, Lead, tenant_id),
    }

    units_summary = "; ".join(
        f"{unit.name} ({unit.code})" + (f" tel. {unit.phone}" if unit.phone else "") for unit in units
    )
    professional_summary = "; ".join(
        f"{item.full_name} - {item.specialty or 'sem especialidade'} - {item.shift_start}-{item.shift_end}"
        for item in professionals[:12]
    )

    profile_name = ""
    if isinstance(clinic_profile, dict):
        profile_name = str(
            clinic_profile.get("clinic_name")
            or clinic_profile.get("display_name")
            or clinic_profile.get("trade_name")
            or ""
        )

    chunks = [
        SupportChunk(
            "tenant.resumo",
            "Contexto real da clínica logada",
            (
                f"Tenant atual: {tenant.trade_name if tenant else profile_name or 'clínica atual'}. "
                f"Unidades: {units_summary or 'nenhuma unidade carregada no contexto'}. "
                f"Serviços oficiais ativos: {', '.join(service_names) or 'nenhum serviço oficial ativo encontrado'}. "
                f"Profissionais: {professional_summary or 'nenhum profissional carregado no contexto'}. "
                f"Contadores: {counts['pacientes']} pacientes, {counts['conversas']} conversas, "
                f"{counts['agenda']} consultas/agendamentos, {counts['leads']} leads."
            ),
            ("clinica", "unidade", "servicos", "profissionais", "contexto", "dados"),
        )
    ]

    if isinstance(ai_config, dict):
        chunks.append(
            SupportChunk(
                "tenant.ia.config",
                "Configuração atual da IA da clínica",
                _clip(f"Configuração IA Auto-Responder atual: {ai_config}", 1200),
                ("ia", "autoresponder", "configuracao"),
            )
        )
    if isinstance(ai_knowledge, dict):
        chunks.append(
            SupportChunk(
                "tenant.ia.conhecimento",
                "Conhecimento IA cadastrado pela clínica",
                _clip(f"Conhecimento IA atual: {ai_knowledge}", 1600),
                ("conhecimento", "faq", "politicas", "ia"),
            )
        )
    return chunks


def _select_chunks(question: str, tenant_chunks: list[SupportChunk], limit: int = 8) -> list[SupportChunk]:
    question_tokens = _tokenize(question)
    chunks = list(SYSTEM_SUPPORT_CHUNKS) + tenant_chunks + list(_load_doc_chunks())

    ranked: list[tuple[int, SupportChunk]] = []
    for chunk in chunks:
        haystack = f"{chunk.title} {chunk.body} {' '.join(chunk.keywords)}"
        tokens = _tokenize(haystack)
        overlap = len(question_tokens.intersection(tokens))
        keyword_hits = sum(1 for keyword in chunk.keywords if _normalize(keyword) in _normalize(question))
        title_hit = 3 if any(token in _normalize(chunk.title) for token in question_tokens) else 0
        ranked.append((overlap + keyword_hits * 4 + title_hit, chunk))

    ranked.sort(key=lambda item: item[0], reverse=True)
    selected = [chunk for score, chunk in ranked if score > 0][:limit]
    if not selected:
        selected = list(SYSTEM_SUPPORT_CHUNKS[:4]) + tenant_chunks[:1]
    return selected[:limit]


def _format_chunks(chunks: list[SupportChunk]) -> str:
    return "\n\n".join(f"[{chunk.id}] {chunk.title}\n{_clip(chunk.body, 1100)}" for chunk in chunks)


def _fallback_answer(question: str, chunks: list[SupportChunk]) -> str:
    first = chunks[0] if chunks else None
    if not first:
        return (
            "Não encontrei informação suficiente para responder com segurança. "
            "Abra a Central de Suporte ou registre um incidente para análise humana."
        )
    return (
        f"Pelo que existe na base do OdontoFlux, o caminho mais seguro é: {first.body} "
        "Se essa dúvida for sobre um comportamento diferente do que aparece na sua tela, registre um incidente em Suporte "
        "com o print e o módulo afetado para validarmos."
    )


def _build_prompt(question: str, chunks: list[SupportChunk], user_name: str, tenant_name: str) -> str:
    return f"""
Você é o Suporte IA interno do OdontoFlux.

Objetivo:
- Responder dúvidas operacionais sobre o sistema OdontoFlux com precisão.
- Usar SOMENTE o contexto abaixo e os dados reais da clínica.
- Não inventar telas, botões, políticas, integrações, preços, endpoints ou comportamentos.
- Se a informação não estiver no contexto, diga claramente: "não encontrei essa informação com segurança na base atual".
- Para dúvidas clínicas/odontológicas, não orientar diagnóstico ou tratamento; explique que o suporte é sobre o sistema.
- Responda em português do Brasil, direto, com passos práticos.
- Quando fizer sentido, cite o caminho exato da tela, por exemplo: Configurações > Tema e Marca.

Usuário: {user_name}
Clínica/Tenant: {tenant_name}
Versão da base de suporte: {SUPPORT_KNOWLEDGE_VERSION}

Contexto autorizado:
{_format_chunks(chunks)}

Pergunta do usuário:
{question}

Resposta:
""".strip()


def generate_system_support_answer(
    db: Session,
    *,
    tenant_id: UUID,
    user_id: UUID | None,
    user_name: str,
    tenant_name: str,
    question: str,
) -> dict:
    cleaned_question = question.strip()
    tenant_chunks = _build_tenant_chunks(db, tenant_id)
    chunks = _select_chunks(cleaned_question, tenant_chunks)
    prompt = _build_prompt(cleaned_question, chunks, user_name, tenant_name)
    started = time.perf_counter()

    answer = ""
    metadata: dict = {"provider": "fallback", "task": "system_support", "knowledge_version": SUPPORT_KNOWLEDGE_VERSION}
    used_llm = False

    provider_name = (settings.llm_provider or "mock").strip().lower()
    if provider_name != "mock" and settings.llm_api_key:
        try:
            result = LLMProviderFactory.create().complete(task="system_support", prompt=prompt)
            answer = str(result.get("output") or "").strip()
            metadata = dict(result.get("metadata") or {})
            metadata["knowledge_version"] = SUPPORT_KNOWLEDGE_VERSION
            used_llm = True
        except Exception as exc:  # pragma: no cover - fallback operacional
            metadata["llm_error"] = str(exc)[:400]

    if not answer:
        answer = _fallback_answer(cleaned_question, chunks)

    latency_ms = int((time.perf_counter() - started) * 1000)
    try:
        db.add(
            LLMInteraction(
                tenant_id=tenant_id,
                conversation_id=None,
                provider=str(metadata.get("provider") or provider_name or "fallback"),
                task="system_support",
                prompt=prompt,
                response=answer,
                metadata_json={
                    **metadata,
                    "used_llm": used_llm,
                    "source_ids": [chunk.id for chunk in chunks],
                    "user_id": str(user_id) if user_id else None,
                },
                latency_ms=latency_ms,
            )
        )
        db.commit()
    except Exception:
        db.rollback()

    return {
        "answer": answer,
        "confidence": 0.92 if used_llm else 0.72,
        "mode": "llm" if used_llm else "fallback",
        "knowledge_version": SUPPORT_KNOWLEDGE_VERSION,
        "sources": [{"id": chunk.id, "title": chunk.title} for chunk in chunks[:5]],
    }

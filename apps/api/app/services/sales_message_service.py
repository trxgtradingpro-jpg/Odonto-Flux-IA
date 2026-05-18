from __future__ import annotations

import re
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ProspectAccount, ProspectTimelineEvent
from app.services import sales_demo_service as sales

DEFAULT_TEMPLATE_KEY = "primeiro_contato"
MESSAGE_SOURCE = "adm_mensagens_para_clinicas"

SALES_MESSAGE_EVENT_LABELS = {
    "message_previewed": "Mensagem comercial gerada",
    "message_copied": "Mensagem comercial copiada",
    "demo_link_copied": "Link de demo copiado",
    "contact_registered": "Contato comercial registrado",
}

SALES_MESSAGE_TEMPLATES = [
    {
        "key": "primeiro_contato",
        "label": "Primeira mensagem",
        "description": "Abordagem curta para enviar a demo personalizada pela primeira vez.",
        "recommended_for": ["novo", "pesquisado", "contato_iniciado"],
        "body": (
            "Oi, {contact_name}! Tudo bem?\n\n"
            "Aqui e a {sender_name}. Eu preparei uma demo personalizada da {clinic_name}, "
            "pensando em {pain_sentence}.\n\n"
            "A ideia e voce ver em poucos minutos como a IA pode atender no WhatsApp, "
            "mostrar disponibilidade e ajudar a agenda sem baguncar a recepcao.\n\n"
            "Link oficial da demo da {clinic_name}:\n"
            "{demo_link}"
        ),
    },
    {
        "key": "demo_enviada",
        "label": "Reenvio da demo",
        "description": "Quando a demo ja foi enviada e voce quer facilitar o acesso.",
        "recommended_for": ["demo_enviada", "followup"],
        "body": (
            "Oi, {contact_name}! Passando rapidinho para deixar novamente a demo "
            "personalizada da {clinic_name}.\n\n"
            "Ela ja esta configurada com o contexto comercial da clinica, para voce "
            "testar WhatsApp, agenda e atendimento com IA de forma simples.\n\n"
            "Link oficial da demo da {clinic_name}:\n"
            "{demo_link}"
        ),
    },
    {
        "key": "demo_acessada",
        "label": "Depois que acessou",
        "description": "Follow-up para clinica que ja abriu a demo.",
        "recommended_for": ["demo_acessada", "testou_whatsapp", "visitou_agenda"],
        "body": (
            "Oi, {contact_name}! Vi que a demo da {clinic_name} ja foi acessada.\n\n"
            "O melhor teste agora e simular um paciente chamando no WhatsApp e tentar "
            "marcar uma consulta. Ali fica claro onde a recepcao ganha tempo.\n\n"
            "Para voltar na demo:\n"
            "{demo_link}"
        ),
    },
    {
        "key": "followup_quente",
        "label": "Follow-up quente",
        "description": "Mensagem mais direta para leads com boa temperatura comercial.",
        "recommended_for": ["respondeu", "decisor_identificado", "negociacao"],
        "body": (
            "Oi, {contact_name}! Pensei aqui no caso da {clinic_name}: {pain_sentence} "
            "e exatamente o tipo de gargalo que a ClinicFlux AI resolve melhor.\n\n"
            "Se voce testar a demo por 3 minutos, ja consegue ver o fluxo de atendimento, "
            "agenda e confirmacao funcionando junto.\n\n"
            "Link oficial da demo da {clinic_name}:\n"
            "{demo_link}"
        ),
    },
    {
        "key": "pedir_reuniao",
        "label": "Pedir reuniao",
        "description": "Convite para uma conversa curta depois da demo.",
        "recommended_for": ["demo_acessada", "testou_whatsapp", "reuniao_marcada"],
        "body": (
            "Oi, {contact_name}! Se fizer sentido para a {clinic_name}, eu consigo te "
            "mostrar a demo ao vivo em 7 minutos e ja explicar como ficaria no WhatsApp "
            "real da clinica.\n\n"
            "Pode ser ainda hoje ou amanha?\n\n"
            "Link oficial da demo da {clinic_name}:\n"
            "{demo_link}"
        ),
    },
    {
        "key": "reativar_parado",
        "label": "Reativar parado",
        "description": "Recuperacao de lead que esfriou ou ficou sem resposta.",
        "recommended_for": ["followup", "fechado_perdido"],
        "body": (
            "Oi, {contact_name}! Voltando no assunto da demo da {clinic_name}.\n\n"
            "A proposta nao e trocar tudo de uma vez. E mostrar um caminho simples para "
            "organizar WhatsApp, agenda e retorno de pacientes sem depender tanto da "
            "recepcao no manual.\n\n"
            "Link oficial da demo da {clinic_name}:\n"
            "{demo_link}"
        ),
    },
]


class _SafeVariables(dict):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def _clean_text(value: str | None) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def _first_name(value: str | None) -> str:
    text = _clean_text(value)
    return text.split(" ", 1)[0] if text else ""


def _base_url(value: str) -> str:
    return str(value or "http://localhost:3000").rstrip("/")


def list_sales_message_templates() -> list[dict]:
    return [dict(template) for template in SALES_MESSAGE_TEMPLATES]


def get_sales_message_template(template_key: str | None) -> dict:
    key = str(template_key or DEFAULT_TEMPLATE_KEY).strip() or DEFAULT_TEMPLATE_KEY
    for template in SALES_MESSAGE_TEMPLATES:
        if template["key"] == key:
            return dict(template)
    return dict(SALES_MESSAGE_TEMPLATES[0])


def suggest_sales_message_template_key(prospect: ProspectAccount) -> str:
    if prospect.do_not_contact:
        return "reativar_parado"
    status = str(prospect.status or "").strip()
    demo_status = str(prospect.demo_status or "").strip()
    if prospect.demo_first_login_at or status == "demo_acessada" or demo_status == "acessada":
        return "demo_acessada"
    if prospect.demo_sent_at or status == "demo_enviada" or demo_status == "enviada":
        return "demo_enviada"
    if status in {"respondeu", "decisor_identificado", "negociacao"}:
        return "followup_quente"
    if str(prospect.temperature or "").strip() in {"quente", "muito_quente"}:
        return "followup_quente"
    if status in {"testou_whatsapp", "visitou_agenda"}:
        return "pedir_reuniao"
    if status in {"followup", "fechado_perdido"}:
        return "reativar_parado"
    return DEFAULT_TEMPLATE_KEY


def resolve_sales_message_contact_name(prospect: ProspectAccount) -> str:
    return (
        _clean_text(prospect.owner_name)
        or _clean_text(prospect.manager_name)
        or _first_name(prospect.clinic_name)
        or "tudo bem"
    )


def resolve_sales_message_destination(prospect: ProspectAccount) -> str | None:
    return _clean_text(prospect.whatsapp_phone) or _clean_text(prospect.phone) or None


def _pain_sentence(prospect: ProspectAccount) -> str:
    pain = _clean_text(prospect.main_pain)
    if pain:
        return f"melhorar este ponto: {pain}"
    return "ganhar tempo no atendimento pelo WhatsApp e reduzir perda de pacientes"


def _sales_message_variables(
    prospect: ProspectAccount,
    *,
    demo_login_url: str | None,
) -> dict[str, str]:
    return {
        "clinic_name": _clean_text(prospect.clinic_name) or "sua clinica",
        "contact_name": resolve_sales_message_contact_name(prospect),
        "owner_name": _clean_text(prospect.owner_name),
        "manager_name": _clean_text(prospect.manager_name),
        "city": _clean_text(prospect.city),
        "state": _clean_text(prospect.state),
        "main_pain": _clean_text(prospect.main_pain),
        "pain_sentence": _pain_sentence(prospect),
        "whatsapp_phone": _clean_text(prospect.whatsapp_phone),
        "test_phone_number": _clean_text(prospect.test_phone_number),
        "website": _clean_text(prospect.website),
        "sender_name": _clean_text(sales.settings.sales_outreach_display_name) or "Equipe ClinicFlux AI",
        "demo_link": demo_login_url or "[gere a demo para inserir o link]",
    }


def _render_template(template: dict, variables: dict[str, str]) -> str:
    body = str(template.get("body") or "").strip()
    message = body.format_map(_SafeVariables(variables)).strip()
    demo_link = variables.get("demo_link") or ""
    if demo_link and demo_link not in message:
        message = f"{message.rstrip()}\n\n{demo_link}"
    return message


def issue_demo_link_if_possible(
    db: Session,
    prospect: ProspectAccount,
    *,
    actor_id: UUID | None,
    base_url: str,
    issue_demo_access: bool = True,
) -> tuple[str | None, list[str]]:
    warnings: list[str] = []
    if not prospect.demo_tenant_id or not prospect.demo_user_id:
        return None, ["Gere a demo desta clinica antes de montar a mensagem com link."]
    if not issue_demo_access:
        return None, ["Clique em gerar mensagem pronta para emitir um link temporario da demo."]

    raw_token = sales.issue_demo_access(db, prospect, actor_id=actor_id)
    return f"{_base_url(base_url)}/login?demo_token={raw_token}", warnings


def latest_sales_message_event(db: Session, prospect: ProspectAccount) -> ProspectTimelineEvent | None:
    return db.scalar(
        select(ProspectTimelineEvent)
        .where(
            ProspectTimelineEvent.prospect_account_id == prospect.id,
            ProspectTimelineEvent.event_type.like("sales_message.%"),
        )
        .order_by(ProspectTimelineEvent.created_at.desc())
        .limit(1)
    )


def serialize_sales_message_item(db: Session, prospect: ProspectAccount) -> dict:
    latest_event = latest_sales_message_event(db, prospect)
    latest_payload = latest_event.payload_json if latest_event else {}
    block_reason = "Clinica marcada como nao contactar." if prospect.do_not_contact else None
    return {
        "prospect": sales.serialize_prospect(db, prospect),
        "suggested_template_key": suggest_sales_message_template_key(prospect),
        "contact_name": resolve_sales_message_contact_name(prospect),
        "whatsapp_destination": resolve_sales_message_destination(prospect),
        "demo_ready": bool(prospect.demo_tenant_id and prospect.demo_user_id),
        "copy_blocked_reason": block_reason,
        "last_event_name": latest_event.event_type if latest_event else None,
        "last_event_at": latest_event.created_at if latest_event else None,
        "last_template_key": latest_payload.get("template_key") if isinstance(latest_payload, dict) else None,
    }


def build_sales_message_preview(
    db: Session,
    *,
    prospect: ProspectAccount,
    template_key: str | None,
    actor_id: UUID | None,
    base_url: str,
    issue_demo_access: bool = True,
) -> dict:
    selected_key = template_key or suggest_sales_message_template_key(prospect)
    template = get_sales_message_template(selected_key)
    if prospect.do_not_contact:
        demo_login_url = None
        warnings = ["Esta clinica esta marcada como nao contactar."]
    else:
        demo_login_url, warnings = issue_demo_link_if_possible(
            db,
            prospect,
            actor_id=actor_id,
            base_url=base_url,
            issue_demo_access=issue_demo_access,
        )
    variables = _sales_message_variables(prospect, demo_login_url=demo_login_url)
    message_text = _render_template(template, variables)
    missing_variables = [] if demo_login_url else ["demo_link"]
    if not resolve_sales_message_destination(prospect):
        warnings.append("Esta clinica nao tem WhatsApp principal cadastrado.")

    can_copy = bool(demo_login_url) and not prospect.do_not_contact
    add_sales_message_timeline_event(
        db,
        prospect=prospect,
        event_name="message_previewed",
        actor_id=actor_id,
        template_key=template["key"],
        message_snapshot=message_text,
        demo_login_url=demo_login_url,
        channel="whatsapp_manual",
        note=None,
        commit=True,
    )
    db.refresh(prospect)
    return {
        "prospect": sales.serialize_prospect(db, prospect),
        "template_key": template["key"],
        "template_label": template["label"],
        "message_text": message_text,
        "demo_login_url": demo_login_url,
        "can_copy": can_copy,
        "warnings": warnings,
        "missing_variables": missing_variables,
        "resolved_variables": variables,
        "suggested_template_key": suggest_sales_message_template_key(prospect),
    }


def add_sales_message_timeline_event(
    db: Session,
    *,
    prospect: ProspectAccount,
    event_name: str,
    actor_id: UUID | None,
    template_key: str | None,
    message_snapshot: str | None,
    demo_login_url: str | None,
    channel: str,
    note: str | None,
    commit: bool = False,
) -> ProspectTimelineEvent:
    if event_name not in SALES_MESSAGE_EVENT_LABELS:
        raise ValueError(f"Unsupported sales message event: {event_name}")
    payload = {
        "source": MESSAGE_SOURCE,
        "template_key": template_key,
        "message_snapshot": message_snapshot,
        "demo_login_url": demo_login_url,
        "channel": channel,
        "note": note,
    }
    event = sales.add_timeline(
        db,
        prospect,
        event_type=f"sales_message.{event_name}",
        event_label=SALES_MESSAGE_EVENT_LABELS[event_name],
        actor_id=actor_id,
        actor_type="admin",
        payload=payload,
    )
    prospect.last_activity_at = datetime.now(UTC)
    db.add(prospect)
    if commit:
        db.commit()
        db.refresh(event)
    return event


def record_sales_message_event(
    db: Session,
    *,
    prospect: ProspectAccount,
    event_name: str,
    actor_id: UUID | None,
    template_key: str | None,
    message_snapshot: str | None,
    demo_login_url: str | None,
    channel: str,
    note: str | None,
) -> ProspectTimelineEvent:
    if event_name == "contact_registered":
        prospect.first_contact_channel = prospect.first_contact_channel or channel
        prospect.first_contact_at = prospect.first_contact_at or datetime.now(UTC)
        if prospect.status in {"novo", "pesquisado"}:
            prospect.status = "contato_iniciado"
    event = add_sales_message_timeline_event(
        db,
        prospect=prospect,
        event_name=event_name,
        actor_id=actor_id,
        template_key=template_key,
        message_snapshot=message_snapshot,
        demo_login_url=demo_login_url,
        channel=channel,
        note=note,
        commit=False,
    )
    db.commit()
    db.refresh(prospect)
    db.refresh(event)
    return event

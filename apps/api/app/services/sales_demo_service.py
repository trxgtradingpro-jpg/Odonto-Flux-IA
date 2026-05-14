from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
import re
import secrets
import unicodedata
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
from uuid import UUID

from fastapi.encoders import jsonable_encoder
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import ApiError
from app.core.security import create_access_token, create_refresh_token, hash_password, verify_password
from app.models import (
    AIProvisioningRun,
    Appointment,
    Automation,
    AutomationRun,
    Conversation,
    DemoActivityEvent,
    Lead,
    Message,
    Patient,
    PatientContact,
    Professional,
    ProspectAccount,
    ProspectNote,
    ProspectService,
    ProspectTimelineEvent,
    ProspectUnit,
    Role,
    Setting,
    Tenant,
    TenantPlan,
    Unit,
    User,
    UserRole,
)
from app.models.enums import (
    AppointmentStatus,
    AutomationTriggerType,
    LeadStage,
    LeadTemperature,
    MessageDirection,
    MessageStatus,
    OutboxStatus,
    RunStatus,
)
from app.services.password_policy_service import validate_password_strength
from app.services.whatsapp_service import assert_whatsapp_account_ready_for_dispatch, queue_outbound_message
from app.utils.hash import sha256_text
from app.utils.phone import normalize_phone

PROSPECT_STATUSES = {
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
}

SCORE_RULES = {
    "demo_opened": 10,
    "login_completed": 10,
    "returned_next_day": 15,
    "visited_conversations": 10,
    "visited_agenda": 10,
    "visited_settings": 10,
    "tested_whatsapp_flow": 20,
    "edited_settings": 20,
    "changed_service": 20,
    "demo_guided_started": 5,
    "demo_guided_step_completed": 10,
    "demo_guided_completed": 20,
}

DEMO_CHECKLIST_KEYS = [
    "tenant_created",
    "user_created",
    "units_created",
    "services_created",
    "professionals_created",
    "agenda_seeded",
    "conversations_seeded",
    "ai_settings_seeded",
    "branding_applied",
    "test_phone_configured",
    "tracking_active",
    "demo_access_valid",
]

DEMO_GUIDE_VERSION = 1
DEMO_GUIDE_SETTING_KEY = "demo.guided_tour"
DEMO_OPERATIONAL_SHOWCASE_SPECS = [
    {
        "name": "Camila Rocha",
        "phone": "+55 11 90000-1001",
        "note": "Interessada em clareamento e avaliacao estetica",
        "time": "09:00",
    },
    {
        "name": "Joao Henrique Lima",
        "phone": "+55 11 90000-1002",
        "note": "Paciente pediu horarios para limpeza",
        "time": "10:30",
    },
    {
        "name": "Patricia Alves",
        "phone": "+55 11 90000-1003",
        "note": "Retorno de avaliacao agendado",
        "time": "11:45",
    },
    {
        "name": "Marcos Antonio Dias",
        "phone": "+55 11 90000-1004",
        "note": "Busca implante e quer encaixe na agenda da semana",
        "time": "14:00",
    },
    {
        "name": "Maria Luiza Nogueira",
        "phone": "+55 11 90000-1005",
        "note": "Quer agendar restauracao e avaliar retorno",
        "time": "16:15",
    },
]
DEMO_GUIDE_STEPS = [
    {
        "id": "value_outcome",
        "order": 1,
        "title": "Resultado que voce vai ganhar",
        "description": "Veja primeiro o ganho comercial da demo: menos no-show, atendimento mais rapido e operacao mais organizada.",
        "observe": [
            "Menos faltas e mais confirmacoes no fluxo da clinica.",
            "WhatsApp centralizado com respostas mais rapidas.",
            "Agenda, leads e pacientes conectados na mesma operacao.",
        ],
        "cta_label": "Ver painel geral",
        "page_path": "/dashboard",
        "page_label": "Dashboard",
    },
    {
        "id": "dashboard_overview",
        "order": 2,
        "title": "Dashboard operacional",
        "description": "Aqui o cliente entende o que esta acontecendo agora, sem precisar abrir varios modulos para ler a operacao.",
        "observe": [
            "KPIs principais para recepcao, confirmacao e cancelamento.",
            "Alertas e prioridades que pedem acao rapida.",
            "Leitura executiva da clinica em poucos segundos.",
        ],
        "cta_label": "Ver atendimento e WhatsApp",
        "page_path": "/dashboard",
        "page_label": "Dashboard",
    },
    {
        "id": "conversations_whatsapp",
        "order": 3,
        "title": "WhatsApp",
        "description": "A central do WhatsApp mostra contexto, responsavel e sinais operacionais para responder com mais velocidade.",
        "observe": [
            "Historico completo do paciente no mesmo lugar.",
            "Organizacao por responsavel, status e prioridade.",
            "Resumo de IA e contexto para reduzir tempo de atendimento.",
        ],
        "cta_label": "Ver agenda da clinica",
        "page_path": "/conversas",
        "page_label": "WhatsApp",
    },
    {
        "id": "agenda_control",
        "order": 4,
        "title": "Agenda da clinica",
        "description": "A agenda deixa o dia mais controlado com confirmacoes, remarcacoes e visao clara do que precisa de acao.",
        "observe": [
            "Consultas distribuidas por profissional e horario.",
            "Confirmacoes pendentes e remarcacoes visiveis.",
            "Menos risco de falta e mais previsibilidade para a recepcao.",
        ],
        "cta_label": "Ver leads e pacientes",
        "page_path": "/agenda",
        "page_label": "Agenda",
    },
    {
        "id": "leads_patients",
        "order": 5,
        "title": "Leads e pacientes",
        "description": "O sistema acompanha relacionamento e comercial, nao so agenda. Leads entram, evoluem e viram pacientes com historico.",
        "observe": [
            "Pipeline comercial com origem, interesse e temperatura.",
            "Pacientes conectados com agenda, conversas e equipe.",
            "Continuidade entre captacao, atendimento e retorno.",
        ],
        "cta_label": "Ver automacoes",
        "page_path": "/leads",
        "page_label": "Leads",
    },
    {
        "id": "automation_scale",
        "order": 6,
        "title": "Automacoes",
        "description": "Lembretes, follow-up e recuperacao de oportunidades escalam a operacao sem depender de trabalho manual o tempo todo.",
        "observe": [
            "Fluxos ativos para confirmacao, lembrete e reativacao.",
            "Execucoes recentes mostrando sucesso e excecoes.",
            "Automacao como apoio para ganhar escala com controle.",
        ],
        "cta_label": "Ver configuracoes finais",
        "page_path": "/automacoes",
        "page_label": "Automacoes",
    },
    {
        "id": "settings_next_steps",
        "order": 7,
        "title": "Configuracoes e proximos passos",
        "description": "No fim da demo, o cliente entende o minimo necessario para implantar: equipe, unidades, servicos, WhatsApp e ajustes basicos.",
        "observe": [
            "Equipe, unidades e servicos estruturam a operacao real.",
            "WhatsApp e ajustes basicos fecham a implantacao.",
            "O onboarding acelera a saida da demo para producao.",
        ],
        "cta_label": "Quero avancar com a implantacao",
        "page_path": "/configuracoes",
        "page_label": "Configuracoes",
    },
]
DEMO_GUIDE_STEP_LOOKUP = {step["id"]: step for step in DEMO_GUIDE_STEPS}

SALES_OUTREACH_STEPS = {
    "reception_intro": "Contato inicial com recepção",
    "decision_maker_pitch": "Apresentação curta com demo",
    "video_followup": "Follow-up com vídeo",
}
SALES_OUTREACH_OPT_OUT_PATTERNS = (
    "pare",
    "parar",
    "remova",
    "remover",
    "nao quero",
    "nao tenho interesse",
    "sem interesse",
    "nao enviar",
    "nao mande",
    "retire meu numero",
)
SALES_OUTREACH_LAB_SCENARIOS = {
    "manager_interested": "Recepcao encaminha e o gerente pede reuniao",
    "asks_price": "Gerente gosta da demo e pede preco",
    "already_has_system": "Gerente diz que ja tem sistema",
    "reception_blocks": "Recepcao segura o acesso ao decisor",
}


def _now() -> datetime:
    return datetime.now(UTC)


def _next_business_day_start(base: datetime, *, hour: int = 9, minute: int = 0) -> datetime:
    current = base.replace(hour=hour, minute=minute, second=0, microsecond=0)
    while current.weekday() >= 5:
        current += timedelta(days=1)
    return current


def _start_of_week_monday(base: datetime) -> datetime:
    current = base.replace(hour=0, minute=0, second=0, microsecond=0)
    return current - timedelta(days=current.weekday())


def _next_demo_showcase_week_start(base: datetime) -> datetime:
    return _start_of_week_monday(base) + timedelta(days=7)


def _combine_day_and_time(base: datetime, time_text: str) -> datetime:
    hour_text, minute_text = (time_text or "09:00").split(":")
    return base.replace(hour=int(hour_text), minute=int(minute_text), second=0, microsecond=0)


def _slugify(value: str) -> str:
    text = value.lower().strip()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-") or "clinica-demo"


def _demo_email(prospect: ProspectAccount) -> str:
    seed = prospect.tenant_seed_key or _slugify(prospect.clinic_name)
    return f"demo+{seed}@demo.odontoflux.app"


def _random_password() -> str:
    # Meets the local password policy while staying temporary and non-human-picked.
    return f"Demo.{secrets.token_urlsafe(16)}A1"


def ensure_sales_roles(db: Session) -> dict[str, Role]:
    roles = {
        "sales_admin": ["sales.prospects.manage", "sales.demos.manage", "sales.activity.read"],
        "sales_viewer": ["sales.prospects.read", "sales.activity.read"],
        "demo_client": ["dashboard.read"],
        "admin_platform": ["platform.admin", "tenants.manage", "plans.manage", "feature_flags.manage"],
        "owner": [
            "dashboard.read",
            "users.manage",
            "patients.manage",
            "leads.manage",
            "conversations.manage",
            "appointments.manage",
            "automations.manage",
            "campaigns.manage",
            "documents.manage",
            "audit.read",
            "settings.manage",
        ],
    }
    result: dict[str, Role] = {}
    for name, permissions in roles.items():
        role = db.scalar(select(Role).where(Role.name == name))
        if not role:
            role = Role(
                name=name,
                description=f"Role {name}",
                scope="platform" if name in {"admin_platform", "sales_admin", "sales_viewer"} else "tenant",
                permissions=permissions,
                is_system=True,
            )
            db.add(role)
            db.flush()
        else:
            role.permissions = sorted(set(role.permissions or []).union(permissions))
            db.add(role)
        result[name] = role
    return result


def ensure_admin_bootstrap(db: Session) -> None:
    if not settings.adm_bootstrap_email or not settings.adm_bootstrap_password:
        return

    email = settings.adm_bootstrap_email.lower().strip()
    existing = db.scalar(select(User).where(User.email == email))
    if existing:
        roles = ensure_sales_roles(db)
        current_role_ids = {row[0] for row in db.execute(select(UserRole.role_id).where(UserRole.user_id == existing.id)).all()}
        missing_role = False
        for role_name in ["admin_platform", "sales_admin"]:
            if roles[role_name].id not in current_role_ids:
                db.add(UserRole(tenant_id=None, user_id=existing.id, role_id=roles[role_name].id))
                missing_role = True
        if missing_role:
            validate_password_strength(settings.adm_bootstrap_password)
            permissions = dict(existing.page_permissions or {})
            permissions["adm_initial_password"] = True
            existing.page_permissions = permissions
            existing.hashed_password = hash_password(settings.adm_bootstrap_password)
            db.add(existing)
            db.commit()
        return

    validate_password_strength(settings.adm_bootstrap_password)
    roles = ensure_sales_roles(db)
    user = User(
        tenant_id=None,
        unit_id=None,
        email=email,
        full_name="Admin Comercial OdontoFlux",
        phone=None,
        hashed_password=hash_password(settings.adm_bootstrap_password),
        is_active=True,
        page_permissions={"adm_initial_password": True},
    )
    db.add(user)
    db.flush()
    for role_name in ["admin_platform", "sales_admin"]:
        db.add(UserRole(tenant_id=None, user_id=user.id, role_id=roles[role_name].id))
    db.commit()


def require_sales_principal(principal) -> None:
    if not {"admin_platform", "sales_admin", "sales_viewer"}.intersection(set(principal.roles)):
        raise ApiError(status_code=403, code="SALES_FORBIDDEN", message="Acesso restrito ao modulo comercial")
    if principal.user.page_permissions.get("adm_initial_password"):
        raise ApiError(status_code=403, code="ADM_PASSWORD_CHANGE_REQUIRED", message="Troque a senha inicial para continuar")


def require_sales_write(principal) -> None:
    require_sales_principal(principal)
    if not {"admin_platform", "sales_admin"}.intersection(set(principal.roles)):
        raise ApiError(status_code=403, code="SALES_WRITE_FORBIDDEN", message="Permissao comercial insuficiente")


def serialize_unit(unit: ProspectUnit) -> dict:
    return {
        "id": unit.id,
        "unit_name": unit.unit_name,
        "address": unit.address,
        "phone": unit.phone,
        "email": unit.email,
        "is_primary": unit.is_primary,
        "created_at": unit.created_at,
    }


def serialize_service(service: ProspectService) -> dict:
    return {
        "id": service.id,
        "service_name": service.service_name,
        "category": service.category,
        "duration_minutes": service.duration_minutes,
        "price_range": service.price_range,
        "description": service.description,
        "created_at": service.created_at,
    }


def serialize_prospect(db: Session, prospect: ProspectAccount, *, include_children: bool = True) -> dict:
    units: list[dict] = []
    services: list[dict] = []
    if include_children:
        units = [
            serialize_unit(item)
            for item in db.execute(
                select(ProspectUnit).where(ProspectUnit.prospect_account_id == prospect.id).order_by(ProspectUnit.is_primary.desc(), ProspectUnit.created_at)
            ).scalars()
        ]
        services = [
            serialize_service(item)
            for item in db.execute(
                select(ProspectService).where(ProspectService.prospect_account_id == prospect.id).order_by(ProspectService.service_name)
            ).scalars()
        ]

    return {
        "id": prospect.id,
        "clinic_name": prospect.clinic_name,
        "owner_name": prospect.owner_name,
        "manager_name": prospect.manager_name,
        "phone": prospect.phone,
        "whatsapp_phone": prospect.whatsapp_phone,
        "email": prospect.email,
        "website": prospect.website,
        "city": prospect.city,
        "state": prospect.state,
        "main_address": prospect.main_address,
        "notes": prospect.notes,
        "lead_source": prospect.lead_source,
        "first_contact_channel": prospect.first_contact_channel,
        "first_contact_at": prospect.first_contact_at,
        "uses_whatsapp_heavily": prospect.uses_whatsapp_heavily,
        "estimated_volume": prospect.estimated_volume,
        "main_pain": prospect.main_pain,
        "score": prospect.score,
        "temperature": prospect.temperature,
        "status": prospect.status,
        "tags": prospect.tags or [],
        "test_phone_number": prospect.test_phone_number,
        "do_not_contact": prospect.do_not_contact,
        "legal_basis": prospect.legal_basis,
        "demo_tenant_id": prospect.demo_tenant_id,
        "demo_user_id": prospect.demo_user_id,
        "demo_login_email": prospect.demo_login_email,
        "demo_sent_at": prospect.demo_sent_at,
        "demo_first_login_at": prospect.demo_first_login_at,
        "demo_last_login_at": prospect.demo_last_login_at,
        "demo_status": prospect.demo_status,
        "demo_expires_at": prospect.demo_expires_at,
        "demo_checklist": prospect.demo_checklist or {},
        "last_activity_at": prospect.last_activity_at,
        "score_explanation": prospect.score_explanation or {},
        "proposal_snapshot": prospect.proposal_snapshot or {},
        "roi_inputs": prospect.roi_inputs or {},
        "created_at": prospect.created_at,
        "updated_at": prospect.updated_at,
        "units": units,
        "services": services,
    }


def add_timeline(
    db: Session,
    prospect: ProspectAccount,
    *,
    event_type: str,
    event_label: str,
    actor_id: UUID | None = None,
    actor_type: str = "system",
    payload: dict | None = None,
) -> ProspectTimelineEvent:
    event = ProspectTimelineEvent(
        prospect_account_id=prospect.id,
        actor_type=actor_type,
        actor_id=actor_id,
        event_type=event_type,
        event_label=event_label,
        payload_json=jsonable_encoder(payload or {}),
    )
    db.add(event)
    return event


def _first_name(value: str | None) -> str:
    text = re.sub(r"\s+", " ", str(value or "").strip())
    return text.split(" ", 1)[0] if text else ""


def _sales_outreach_sender_tenant(db: Session) -> Tenant:
    slug = str(settings.sales_outreach_sender_tenant_slug or "").strip()
    if not slug:
        raise ApiError(
            status_code=400,
            code="SALES_OUTREACH_CONFIG_MISSING",
            message="Configure SALES_OUTREACH_SENDER_TENANT_SLUG para habilitar envios comerciais pelo WhatsApp.",
        )
    tenant = db.scalar(select(Tenant).where(Tenant.slug == slug, Tenant.is_active.is_(True)))
    if not tenant:
        raise ApiError(
            status_code=404,
            code="SALES_OUTREACH_SENDER_TENANT_NOT_FOUND",
            message="Tenant remetente do outreach comercial nao encontrado ou inativo.",
        )
    return tenant


def _prospect_outreach_destination(prospect: ProspectAccount) -> tuple[str, str]:
    if prospect.do_not_contact:
        raise ApiError(
            status_code=409,
            code="PROSPECT_DO_NOT_CONTACT",
            message="Este prospect esta marcado como nao contatar.",
        )
    raw_phone = str(prospect.whatsapp_phone or prospect.phone or "").strip()
    normalized = normalize_phone(raw_phone)
    if not normalized:
        raise ApiError(
            status_code=400,
            code="PROSPECT_PHONE_REQUIRED",
            message="Cadastre um telefone ou WhatsApp valido antes de iniciar o outreach.",
        )
    return raw_phone, normalized


def _prospect_outreach_tag(prospect_id: UUID) -> str:
    return f"prospect_id:{prospect_id}"


def _prospect_id_from_conversation_tags(tags: list[str] | None) -> UUID | None:
    for tag in tags or []:
        value = str(tag or "").strip()
        if not value.startswith("prospect_id:"):
            continue
        raw = value.split(":", 1)[1].strip()
        try:
            return UUID(raw)
        except ValueError:
            continue
    return None


def _update_outreach_snapshot(prospect: ProspectAccount, *, patch: dict) -> None:
    snapshot = dict(prospect.proposal_snapshot or {})
    outreach = snapshot.get("outreach") if isinstance(snapshot.get("outreach"), dict) else {}
    outreach.update(jsonable_encoder(patch))
    snapshot["outreach"] = outreach
    prospect.proposal_snapshot = snapshot


def _outreach_snapshot(prospect: ProspectAccount) -> dict:
    snapshot = dict(prospect.proposal_snapshot or {})
    outreach = snapshot.get("outreach")
    return dict(outreach) if isinstance(outreach, dict) else {}


def _normalized_lookup_text(value: str | None) -> str:
    normalized = unicodedata.normalize("NFKD", str(value or ""))
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", ascii_text.lower()).strip()


def _looks_like_outreach_opt_out(value: str | None) -> bool:
    lookup = _normalized_lookup_text(value)
    return any(pattern in lookup for pattern in SALES_OUTREACH_OPT_OUT_PATTERNS)


def _default_sales_outreach_base_url() -> str:
    candidate = ""
    if settings.api_cors_origins:
        candidate = str(settings.api_cors_origins[0] or "").strip()
    return candidate or "http://localhost:3000"


def _tracked_url(url: str, *, prospect: ProspectAccount, content: str) -> str:
    parsed = urlparse(url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query.update(
        {
            "utm_source": "whatsapp",
            "utm_medium": "outreach_b2b",
            "utm_campaign": prospect.tenant_seed_key or _slugify(prospect.clinic_name),
            "utm_content": content,
            "prospect_id": str(prospect.id),
        }
    )
    return urlunparse(parsed._replace(query=urlencode(query)))


def _ensure_outreach_demo_link(
    db: Session,
    *,
    prospect: ProspectAccount,
    actor_id: UUID | None,
    base_url: str,
) -> str:
    if prospect.demo_tenant_id:
        raw_token = issue_demo_access(db, prospect, actor_id=actor_id)
        return _tracked_url(
            f"{base_url}/login?demo_token={raw_token}",
            prospect=prospect,
            content="decision_maker_pitch",
        )

    generated = generate_demo(db, prospect, actor_id=actor_id, base_url=base_url)
    return _tracked_url(
        str(generated["demo_login_url"]),
        prospect=prospect,
        content="decision_maker_pitch",
    )


def _resolve_outreach_video_url(*, prospect: ProspectAccount, explicit_video_url: str | None) -> str:
    candidate = str(explicit_video_url or settings.sales_outreach_video_url or "").strip()
    if not candidate:
        raise ApiError(
            status_code=400,
            code="SALES_OUTREACH_VIDEO_REQUIRED",
            message="Configure SALES_OUTREACH_VIDEO_URL ou informe um link de video para enviar o follow-up.",
        )
    return _tracked_url(candidate, prospect=prospect, content="video_followup")


def _resolve_outreach_lab_video_url(*, prospect: ProspectAccount, base_url: str) -> tuple[str, str]:
    candidate = str(settings.sales_outreach_video_url or "").strip()
    source = "configured"
    if not candidate:
        candidate = f"{base_url.rstrip('/')}/demo-video-comercial"
        source = "lab_placeholder"
    return _tracked_url(candidate, prospect=prospect, content="video_followup"), source


def simulate_sales_outreach_lab(
    db: Session,
    *,
    prospect: ProspectAccount,
    actor_id: UUID | None,
    base_url: str,
    scenario: str = "manager_interested",
) -> dict:
    scenario_key = str(scenario or "manager_interested").strip() or "manager_interested"
    scenario_label = SALES_OUTREACH_LAB_SCENARIOS.get(scenario_key)
    if not scenario_label:
        raise ApiError(
            status_code=400,
            code="SALES_OUTREACH_LAB_SCENARIO_INVALID",
            message="Cenario do IA Lab comercial invalido.",
        )

    decision_maker_name = prospect.owner_name or prospect.manager_name or "Mariana"
    receptionist_name = "Recepcao virtual"
    generated_at = _now()

    transcript: list[dict] = []

    def add_turn(role: str, label: str, text: str, *, step: str | None = None, meta: dict | None = None) -> None:
        transcript.append(
            {
                "id": f"turn_{len(transcript) + 1}",
                "role": role,
                "label": label,
                "text": str(text or "").strip(),
                "step": step,
                "meta": jsonable_encoder(meta or {}),
            }
        )

    add_turn(
        "system",
        "IA Lab comercial",
        f"Simulacao sem WhatsApp real para o cenario: {scenario_label}.",
        step="lab_context",
        meta={"scenario": scenario_key},
    )

    reception_message = _build_outreach_message(prospect, step="reception_intro")
    add_turn(
        "odontoflux",
        "OdontoFlux - contato inicial",
        reception_message,
        step="reception_intro",
    )

    converted = False
    outcome = "blocked_by_reception"
    recommendation = "Pedir o melhor canal do decisor e reforcar prova social curta antes de insistir."
    demo_login_url: str | None = None
    video_url: str | None = None
    video_source: str | None = None
    reached_decision_maker = False

    if scenario_key == "reception_blocks":
        reception_reply = (
            f"Oi! Sou da recepcao da {prospect.clinic_name}. No momento eu nao consigo passar dono ou gerente por aqui. "
            "Se quiser, mande um resumo curto que eu registro internamente."
        )
        add_turn(
            "clinic_virtual",
            receptionist_name,
            reception_reply,
            step="reception_reply",
        )
        add_turn(
            "system",
            "Analise do IA Lab",
            "Fluxo travou antes do decisor. O melhor ajuste aqui e trocar o CTA para pedir o canal correto ou usar uma prova social mais curta.",
            step="lab_analysis",
        )
    else:
        if scenario_key == "asks_price":
            reception_reply = (
                f"Oi, aqui e a recepcao da {prospect.clinic_name}. Pode mandar para a gerente {decision_maker_name}. "
                "Ela costuma avaliar demo e custos antes de avancar."
            )
        elif scenario_key == "already_has_system":
            reception_reply = (
                f"Oi! Pode mandar para o gerente {decision_maker_name}. "
                "Ele sempre pergunta primeiro como isso entra no fluxo atual da clinica."
            )
        else:
            reception_reply = (
                f"Oi! Sou da recepcao da {prospect.clinic_name}. Pode falar por aqui mesmo. "
                f"A gerente {decision_maker_name} acompanha este numero e consegue ver uma demonstracao curta."
            )
        add_turn(
            "clinic_virtual",
            receptionist_name,
            reception_reply,
            step="reception_reply",
        )

        demo_login_url = _ensure_outreach_demo_link(
            db,
            prospect=prospect,
            actor_id=actor_id,
            base_url=base_url,
        )
        db.refresh(prospect)
        reached_decision_maker = True

        pitch_message = _build_outreach_message(
            prospect,
            step="decision_maker_pitch",
            demo_login_url=demo_login_url,
            recipient_name=decision_maker_name,
        )
        add_turn(
            "odontoflux",
            "OdontoFlux - pitch com demo",
            pitch_message,
            step="decision_maker_pitch",
            meta={"demo_login_url": demo_login_url},
        )

        if scenario_key == "asks_price":
            manager_reply = (
                f"Oi, aqui e {decision_maker_name}. Vi a demo e faz sentido. "
                "Quanto custa para implantar e qual costuma ser o prazo de ativacao?"
            )
            outcome = "pricing_requested"
            recommendation = "Responder com ROI rapido, faixa de investimento e sugerir reuniao curta para fechamento."
        elif scenario_key == "already_has_system":
            manager_reply = (
                f"Oi, aqui e {decision_maker_name}. Ja usamos sistema na clinica. "
                "O que voces resolvem alem da agenda e por que valeria testar?"
            )
            outcome = "existing_system_objection_but_open"
            recommendation = "Responder com o diferencial de fluxo completo e convidar para uma demo guiada."
        else:
            manager_reply = (
                f"Oi, aqui e {decision_maker_name}. Abri a demo e gostei da parte de WhatsApp, agenda e retorno. "
                "Como funciona para implantar isso na clinica?"
            )
            outcome = "meeting_requested"
            recommendation = "Enviar proposta curta e fechar uma reuniao de implantacao nesta semana."
        add_turn(
            "clinic_virtual",
            f"{decision_maker_name} - decisor virtual",
            manager_reply,
            step="decision_maker_reply",
        )

        video_url, video_source = _resolve_outreach_lab_video_url(prospect=prospect, base_url=base_url)
        video_message = _build_outreach_message(
            prospect,
            step="video_followup",
            video_url=video_url,
            recipient_name=decision_maker_name,
        )
        add_turn(
            "odontoflux",
            "OdontoFlux - video follow-up",
            video_message,
            step="video_followup",
            meta={"video_url": video_url, "video_source": video_source},
        )

        if scenario_key == "asks_price":
            final_reply = (
                "Se o piloto couber no nosso orcamento, podemos avancar para uma reuniao rapida e validar implantacao."
            )
        elif scenario_key == "already_has_system":
            final_reply = (
                "Entendi. Se der para complementar nosso fluxo atual sem atrapalhar a operacao, faz sentido marcar uma demonstracao."
            )
        else:
            final_reply = (
                "Perfeito. Se voce me mandar uma proposta curta, conseguimos marcar uma reuniao nesta semana."
            )
        add_turn(
            "clinic_virtual",
            f"{decision_maker_name} - decisor virtual",
            final_reply,
            step="final_reply",
        )
        converted = True

    steps_run = len([item for item in transcript if item["role"] == "odontoflux"])
    metrics = {
        "turns": len(transcript),
        "steps_run": steps_run,
        "reached_decision_maker": reached_decision_maker,
        "demo_link_prepared": bool(demo_login_url),
        "video_link_prepared": bool(video_url),
        "video_source": video_source,
        "converted": converted,
        "outcome": outcome,
    }

    snapshot = dict(prospect.proposal_snapshot or {})
    outreach_lab = snapshot.get("outreach_lab") if isinstance(snapshot.get("outreach_lab"), dict) else {}
    scenario_stats = outreach_lab.get("scenario_stats") if isinstance(outreach_lab.get("scenario_stats"), dict) else {}
    current_stats = scenario_stats.get(scenario_key) if isinstance(scenario_stats.get(scenario_key), dict) else {}
    runs = int(current_stats.get("runs") or 0) + 1
    conversions = int(current_stats.get("conversions") or 0) + (1 if converted else 0)
    scenario_stats[scenario_key] = {
        "runs": runs,
        "conversions": conversions,
        "last_outcome": outcome,
        "last_run_at": generated_at.isoformat(),
    }
    metrics["scenario_runs"] = runs
    metrics["scenario_conversions"] = conversions

    outreach_lab.update(
        {
            "last_run_at": generated_at.isoformat(),
            "last_scenario": scenario_key,
            "last_outcome": outcome,
            "last_converted": converted,
            "scenario_stats": scenario_stats,
            "last_run": {
                "scenario": scenario_key,
                "scenario_label": scenario_label,
                "generated_at": generated_at.isoformat(),
                "converted": converted,
                "outcome": outcome,
                "recommendation": recommendation,
                "demo_login_url": demo_login_url,
                "video_url": video_url,
                "metrics": metrics,
                "transcript": transcript,
            },
        }
    )
    snapshot["outreach_lab"] = outreach_lab
    prospect.proposal_snapshot = snapshot
    prospect.last_activity_at = generated_at

    add_timeline(
        db,
        prospect,
        event_type="prospect.outreach_lab.completed",
        event_label=f"IA Lab comercial executado: {scenario_label}",
        actor_id=actor_id,
        actor_type="admin",
        payload={
            "scenario": scenario_key,
            "converted": converted,
            "outcome": outcome,
            "turns": len(transcript),
            "steps_run": steps_run,
            "recommendation": recommendation,
        },
    )
    db.add(prospect)
    db.commit()
    db.refresh(prospect)

    return {
        "prospect": serialize_prospect(db, prospect),
        "scenario": scenario_key,
        "scenario_label": scenario_label,
        "status": "ok",
        "outcome": outcome,
        "converted": converted,
        "recommendation": recommendation,
        "demo_login_url": demo_login_url,
        "video_url": video_url,
        "transcript": transcript,
        "metrics": metrics,
    }


def _build_outreach_message(
    prospect: ProspectAccount,
    *,
    step: str,
    demo_login_url: str | None = None,
    video_url: str | None = None,
    recipient_name: str | None = None,
) -> str:
    sender_name = str(settings.sales_outreach_display_name or "Equipe OdontoFlux").strip() or "Equipe OdontoFlux"
    pain_hint = f" e reduzir {prospect.main_pain.lower()}" if prospect.main_pain else ""

    if step == "reception_intro":
        return (
            f"Olá! Aqui é {sender_name} da OdontoFlux.\n"
            f"Estou falando com a {prospect.clinic_name} de forma comercial e transparente porque acredito que a clínica pode organizar melhor WhatsApp, recepção, agenda e retorno de pacientes{pain_hint}.\n"
            "Você pode me indicar o dono(a) ou gerente responsável pela operação/recepção para eu enviar uma demonstração curta?"
        )

    if step == "decision_maker_pitch":
        addressee = _first_name(recipient_name or prospect.owner_name or prospect.manager_name)
        greeting = f"Olá, {addressee}!" if addressee else "Olá!"
        return (
            f"{greeting} Aqui é {sender_name} da OdontoFlux.\n"
            "O OdontoFlux organiza WhatsApp, recepção, agenda, confirmações e retorno do paciente em um fluxo único para reduzir retrabalho, dar mais previsibilidade e melhorar a conversão da clínica.\n"
            f"Demo rápida: {demo_login_url}"
        )

    if step == "video_followup":
        addressee = _first_name(recipient_name or prospect.owner_name or prospect.manager_name)
        greeting = f"Olá, {addressee}!" if addressee else "Olá!"
        return (
            f"{greeting} Separei um vídeo curto mostrando esse fluxo na prática:\n"
            f"{video_url}\n"
            "Se fizer sentido, eu também posso te orientar nos pontos que mais costumam destravar resultado: recepção no WhatsApp, agenda e retorno do paciente."
        )

    raise ApiError(status_code=400, code="SALES_OUTREACH_STEP_INVALID", message="Etapa comercial invalida")


def _ensure_outreach_conversation(
    db: Session,
    *,
    sender_tenant: Tenant,
    prospect: ProspectAccount,
) -> Conversation:
    account = assert_whatsapp_account_ready_for_dispatch(db, tenant_id=sender_tenant.id)
    raw_phone, normalized_phone = _prospect_outreach_destination(prospect)

    patient = db.scalar(
        select(Patient).where(
            Patient.tenant_id == sender_tenant.id,
            Patient.normalized_phone == normalized_phone,
        )
    )
    if not patient:
        patient = Patient(
            tenant_id=sender_tenant.id,
            unit_id=account.unit_id,
            full_name=f"Contato comercial - {prospect.clinic_name}",
            phone=raw_phone,
            normalized_phone=normalized_phone,
            operational_notes=f"Prospect comercial OdontoFlux vinculado ao prospect_account_id={prospect.id}",
            status="lead",
            origin="sales_outreach",
            lgpd_consent=False,
            marketing_opt_in=False,
            tags_cache=["prospect_outreach"],
        )
        db.add(patient)
        db.flush()
        db.add(
            PatientContact(
                tenant_id=sender_tenant.id,
                patient_id=patient.id,
                channel="whatsapp",
                value=raw_phone,
                normalized_value=normalized_phone,
                is_primary=True,
                is_verified=False,
            )
        )
    elif account.unit_id and not patient.unit_id:
        patient.unit_id = account.unit_id
        db.add(patient)

    conversation = db.scalar(
        select(Conversation)
        .where(
            Conversation.tenant_id == sender_tenant.id,
            Conversation.patient_id == patient.id,
            Conversation.channel == "whatsapp",
            Conversation.status.in_(["aberta", "aguardando"]),
        )
        .order_by(Conversation.last_message_at.desc())
        .limit(1)
    )
    if not conversation:
        conversation = Conversation(
            tenant_id=sender_tenant.id,
            unit_id=account.unit_id or patient.unit_id,
            patient_id=patient.id,
            channel="whatsapp",
            status="aberta",
            ai_autoresponder_enabled=False,
            tags=["prospect_outreach", _prospect_outreach_tag(prospect.id)],
            last_message_at=_now(),
        )
        db.add(conversation)
        db.flush()
    else:
        tags = set(conversation.tags or [])
        tags.add("prospect_outreach")
        tags.add(_prospect_outreach_tag(prospect.id))
        conversation.tags = sorted(tags)
        conversation.ai_autoresponder_enabled = False
        conversation.last_message_at = _now()
        db.add(conversation)
        db.flush()

    return conversation


def send_sales_outreach_step(
    db: Session,
    *,
    prospect: ProspectAccount,
    step: str,
    actor_id: UUID | None,
    base_url: str,
    recipient_name: str | None = None,
    explicit_video_url: str | None = None,
    commit: bool = True,
    immediate_dispatch: bool | None = None,
    extra_snapshot_patch: dict | None = None,
) -> dict:
    if step not in SALES_OUTREACH_STEPS:
        raise ApiError(status_code=400, code="SALES_OUTREACH_STEP_INVALID", message="Etapa comercial invalida")

    sender_tenant = _sales_outreach_sender_tenant(db)
    conversation = _ensure_outreach_conversation(db, sender_tenant=sender_tenant, prospect=prospect)
    raw_phone, _ = _prospect_outreach_destination(prospect)

    demo_login_url = None
    video_url = None
    if step == "decision_maker_pitch":
        demo_login_url = _ensure_outreach_demo_link(
            db,
            prospect=prospect,
            actor_id=actor_id,
            base_url=base_url,
        )
    elif step == "video_followup":
        video_url = _resolve_outreach_video_url(prospect=prospect, explicit_video_url=explicit_video_url)

    message_text = _build_outreach_message(
        prospect,
        step=step,
        demo_login_url=demo_login_url,
        video_url=video_url,
        recipient_name=recipient_name,
    )

    outbound_message = Message(
        tenant_id=sender_tenant.id,
        conversation_id=conversation.id,
        direction=MessageDirection.OUTBOUND.value,
        channel="whatsapp",
        sender_type="user",
        sender_user_id=actor_id,
        body=message_text,
        message_type="text",
        payload={
            "source": "sales_outreach",
            "prospect_account_id": str(prospect.id),
            "step": step,
            "demo_login_url": demo_login_url,
            "video_url": video_url,
        },
        status=MessageStatus.QUEUED.value,
    )
    db.add(outbound_message)
    db.flush()

    outbox = queue_outbound_message(
        db,
        tenant_id=sender_tenant.id,
        conversation_id=conversation.id,
        to=raw_phone,
        body=message_text,
        message_type="text",
        metadata={
            "source": "sales_outreach",
            "prospect_account_id": str(prospect.id),
            "step": step,
            "demo_login_url": demo_login_url,
            "video_url": video_url,
            "outbound_message_id": str(outbound_message.id),
        },
        immediate_dispatch=immediate_dispatch,
        commit=False,
    )

    if outbox.status in {OutboxStatus.FAILED.value, OutboxStatus.DEAD_LETTER.value}:
        failed_at = _now()
        prospect.last_activity_at = failed_at
        _update_outreach_snapshot(
            prospect,
            patch={
                "last_step": step,
                "last_attempted_at": failed_at.isoformat(),
                "last_dispatch_status": outbox.status,
                "last_dispatch_error": outbox.last_error,
                "last_outbox_id": str(outbox.id),
                "sender_tenant_id": str(sender_tenant.id),
                "conversation_id": str(conversation.id),
                "recipient_name": recipient_name or prospect.owner_name or prospect.manager_name,
            },
        )
        add_timeline(
            db,
            prospect,
            event_type=f"prospect.outreach.{step}_failed",
            event_label="Falha no envio comercial via WhatsApp",
            actor_id=actor_id,
            actor_type="admin",
            payload={
                "destination": raw_phone,
                "sender_tenant_id": str(sender_tenant.id),
                "conversation_id": str(conversation.id),
                "outbox_id": str(outbox.id),
                "dispatch_status": outbox.status,
                "dispatch_error": outbox.last_error,
                "step": step,
            },
        )
        db.add(prospect)
        db.commit()
        raise ApiError(
            status_code=400,
            code="SALES_OUTREACH_DISPATCH_FAILED",
            message=outbox.last_error or "Falha ao enviar mensagem comercial pelo WhatsApp.",
            details={
                "step": step,
                "outbox_id": str(outbox.id),
                "dispatch_status": outbox.status,
            },
        )

    outbound_message.payload = {
        **(outbound_message.payload if isinstance(outbound_message.payload, dict) else {}),
        "queued_outbox_id": str(outbox.id),
    }
    db.add(outbound_message)

    if not prospect.first_contact_at:
        prospect.first_contact_at = _now()
    if not prospect.first_contact_channel:
        prospect.first_contact_channel = "whatsapp_outreach_transparent"

    if step == "reception_intro" and prospect.status in {"novo", "pesquisado"}:
        prospect.status = "contato_iniciado"
    elif step == "video_followup" and prospect.status in {"demo_enviada", "demo_acessada", "respondeu"}:
        prospect.status = "followup"

    prospect.last_activity_at = _now()
    snapshot_patch = {
        "last_step": step,
        "last_sent_at": prospect.last_activity_at.isoformat(),
        "last_demo_login_url": demo_login_url,
        "last_video_url": video_url,
        "sender_tenant_id": str(sender_tenant.id),
        "conversation_id": str(conversation.id),
        "last_outbox_id": str(outbox.id),
        "last_dispatch_status": outbox.status,
        "recipient_name": recipient_name or prospect.owner_name or prospect.manager_name,
    }
    if extra_snapshot_patch:
        snapshot_patch.update(jsonable_encoder(extra_snapshot_patch))
    _update_outreach_snapshot(prospect, patch=snapshot_patch)
    add_timeline(
        db,
        prospect,
        event_type=f"prospect.outreach.{step}",
        event_label=f"{SALES_OUTREACH_STEPS[step]} enviada no WhatsApp",
        actor_id=actor_id,
        actor_type="admin",
        payload={
            "destination": raw_phone,
            "sender_tenant_id": str(sender_tenant.id),
            "conversation_id": str(conversation.id),
            "outbox_id": str(outbox.id),
            "message_text": message_text,
            "demo_login_url": demo_login_url,
            "video_url": video_url,
        },
    )
    db.add(prospect)
    db.flush()
    if commit:
        db.commit()
        db.refresh(prospect)
        db.refresh(outbound_message)

    return {
        "prospect": serialize_prospect(db, prospect),
        "step": step,
        "destination": raw_phone,
        "message_text": message_text,
        "demo_login_url": demo_login_url,
        "video_url": video_url,
        "sender_tenant_id": sender_tenant.id,
        "conversation_id": conversation.id,
        "outbound_message_id": outbound_message.id,
    }


def start_sales_outreach_automation(
    db: Session,
    *,
    prospect: ProspectAccount,
    actor_id: UUID | None,
    base_url: str,
) -> dict:
    outreach = _outreach_snapshot(prospect)
    if outreach.get("automation_active"):
        raise ApiError(
            status_code=409,
            code="SALES_OUTREACH_AUTOMATION_ACTIVE",
            message="A automacao comercial ja esta ativa para este prospect.",
        )

    started_at = _now().isoformat()
    add_timeline(
        db,
        prospect,
        event_type="prospect.outreach.automation_started",
        event_label="Automacao comercial iniciada",
        actor_id=actor_id,
        actor_type="admin",
        payload={"mode": "transparent_b2b"},
    )
    return send_sales_outreach_step(
        db,
        prospect=prospect,
        step="reception_intro",
        actor_id=actor_id,
        base_url=base_url,
        extra_snapshot_patch={
            "automation_active": True,
            "automation_mode": "transparent_b2b",
            "auto_progress": True,
            "auto_send_video_after_pitch": True,
            "automation_started_at": started_at,
            "automation_completed_at": None,
            "automation_stopped_at": None,
            "automation_stop_reason": None,
        },
    )


def sync_prospect_outreach_reply(
    db: Session,
    *,
    conversation: Conversation,
    message: Message,
) -> None:
    prospect_id = _prospect_id_from_conversation_tags(conversation.tags or [])
    if not prospect_id:
        return
    prospect = db.get(ProspectAccount, prospect_id)
    if not prospect:
        return

    body_preview = re.sub(r"\s+", " ", str(message.body or "").strip())[:500]
    prospect.last_activity_at = _now()
    if prospect.status in {"novo", "pesquisado", "contato_iniciado", "decisor_identificado", "demo_enviada", "followup"}:
        prospect.status = "respondeu"
    _update_outreach_snapshot(
        prospect,
        patch={
            "last_reply_at": prospect.last_activity_at.isoformat(),
            "last_reply_preview": body_preview,
            "conversation_id": str(conversation.id),
        },
    )
    add_timeline(
        db,
        prospect,
        event_type="prospect.outreach.reply_received",
        event_label="Resposta recebida no WhatsApp comercial",
        actor_type="system",
        payload={
            "conversation_id": str(conversation.id),
            "message_id": str(message.id),
            "body_preview": body_preview,
        },
    )
    if _looks_like_outreach_opt_out(body_preview):
        prospect.do_not_contact = True
        if not prospect.opt_out_at:
            prospect.opt_out_at = prospect.last_activity_at
        _update_outreach_snapshot(
            prospect,
            patch={
                "automation_active": False,
                "automation_stopped_at": prospect.last_activity_at.isoformat(),
                "automation_stop_reason": "opt_out",
            },
        )
        add_timeline(
            db,
            prospect,
            event_type="prospect.outreach.opt_out",
            event_label="Prospect pediu para parar o contato comercial",
            actor_type="system",
            payload={
                "conversation_id": str(conversation.id),
                "message_id": str(message.id),
                "body_preview": body_preview,
            },
        )
        db.add(prospect)
        return

    outreach = _outreach_snapshot(prospect)
    if bool(outreach.get("automation_active")) and str(outreach.get("last_step") or "").strip() == "reception_intro":
        send_sales_outreach_step(
            db,
            prospect=prospect,
            step="decision_maker_pitch",
            actor_id=None,
            base_url=_default_sales_outreach_base_url(),
            recipient_name=prospect.owner_name or prospect.manager_name,
            commit=False,
            immediate_dispatch=False,
            extra_snapshot_patch={"automation_active": True},
        )
        if str(settings.sales_outreach_video_url or "").strip():
            send_sales_outreach_step(
                db,
                prospect=prospect,
                step="video_followup",
                actor_id=None,
                base_url=_default_sales_outreach_base_url(),
                recipient_name=prospect.owner_name or prospect.manager_name,
                commit=False,
                immediate_dispatch=False,
                extra_snapshot_patch={"automation_active": True},
            )
            _update_outreach_snapshot(
                prospect,
                patch={
                    "automation_active": False,
                    "automation_completed_at": prospect.last_activity_at.isoformat(),
                    "automation_stop_reason": "sequence_completed",
                },
            )
            add_timeline(
                db,
                prospect,
                event_type="prospect.outreach.automation_completed",
                event_label="Automacao comercial concluiu o fluxo inicial",
                actor_type="system",
                payload={"conversation_id": str(conversation.id)},
            )
        else:
            _update_outreach_snapshot(
                prospect,
                patch={
                    "automation_active": False,
                    "automation_stopped_at": prospect.last_activity_at.isoformat(),
                    "automation_stop_reason": "video_url_missing",
                },
            )
            add_timeline(
                db,
                prospect,
                event_type="prospect.outreach.automation_paused",
                event_label="Automacao comercial pausada sem video configurado",
                actor_type="system",
                payload={"conversation_id": str(conversation.id)},
            )
    db.add(prospect)


def create_prospect(db: Session, payload, *, actor_id: UUID | None) -> ProspectAccount:
    duplicate_filter = []
    if payload.whatsapp_phone:
        duplicate_filter.append(ProspectAccount.whatsapp_phone == payload.whatsapp_phone)
    if payload.phone:
        duplicate_filter.append(ProspectAccount.phone == payload.phone)
    if payload.website:
        duplicate_filter.append(ProspectAccount.website == payload.website)
    if duplicate_filter:
        existing = db.scalar(select(ProspectAccount).where(or_(*duplicate_filter)))
        if existing:
            raise ApiError(status_code=409, code="PROSPECT_DUPLICATE", message="Clinica prospectada possivelmente duplicada")

    prospect = ProspectAccount(
        clinic_name=payload.clinic_name,
        owner_name=payload.owner_name,
        manager_name=payload.manager_name,
        phone=payload.phone,
        whatsapp_phone=payload.whatsapp_phone,
        email=str(payload.email) if payload.email else None,
        website=payload.website,
        city=payload.city,
        state=payload.state,
        main_address=payload.main_address,
        notes=payload.notes,
        lead_source=payload.lead_source,
        first_contact_channel=payload.first_contact_channel,
        first_contact_at=payload.first_contact_at,
        uses_whatsapp_heavily=payload.uses_whatsapp_heavily,
        estimated_volume=payload.estimated_volume,
        main_pain=payload.main_pain,
        tags=payload.tags,
        test_phone_number=payload.test_phone_number,
        created_by=actor_id,
        updated_by=actor_id,
        tenant_seed_key=f"{_slugify(payload.clinic_name)}-{secrets.token_hex(3)}",
    )
    db.add(prospect)
    db.flush()

    if payload.main_address:
        db.add(
            ProspectUnit(
                prospect_account_id=prospect.id,
                unit_name="Unidade principal",
                address=payload.main_address,
                phone=payload.phone,
                email=str(payload.email) if payload.email else None,
                is_primary=True,
            )
        )

    for unit in payload.units:
        db.add(
            ProspectUnit(
                prospect_account_id=prospect.id,
                unit_name=unit.unit_name,
                address=unit.address,
                phone=unit.phone,
                email=str(unit.email) if unit.email else None,
                is_primary=unit.is_primary,
            )
        )
    for service in payload.services:
        db.add(
            ProspectService(
                prospect_account_id=prospect.id,
                service_name=service.service_name,
                category=service.category,
                duration_minutes=service.duration_minutes,
                price_range=service.price_range,
                description=service.description,
            )
        )
    add_timeline(db, prospect, event_type="prospect.created", event_label="Clinica cadastrada no CRM comercial", actor_id=actor_id, actor_type="admin")
    db.commit()
    db.refresh(prospect)
    return prospect


def update_prospect(db: Session, prospect: ProspectAccount, payload, *, actor_id: UUID | None) -> ProspectAccount:
    data = payload.model_dump(exclude_unset=True)
    for key, value in data.items():
        if key == "email" and value is not None:
            value = str(value)
        setattr(prospect, key, value)
    prospect.updated_by = actor_id
    if prospect.do_not_contact and not prospect.opt_out_at:
        prospect.opt_out_at = _now()
    add_timeline(db, prospect, event_type="prospect.updated", event_label="Dados da clinica atualizados", actor_id=actor_id, actor_type="admin", payload=data)
    db.add(prospect)
    db.commit()
    db.refresh(prospect)
    return prospect


def recalculate_score(db: Session, prospect: ProspectAccount) -> ProspectAccount:
    events = db.execute(select(DemoActivityEvent).where(DemoActivityEvent.prospect_account_id == prospect.id)).scalars().all()
    counts: dict[str, int] = {}
    for event in events:
        counts[event.event_name] = counts.get(event.event_name, 0) + 1

    points: dict[str, int] = {}
    for event_name, weight in SCORE_RULES.items():
        if counts.get(event_name):
            points[event_name] = weight

    sessions = len({event.session_id for event in events if event.session_id})
    if sessions > 3:
        points["mais_de_3_sessoes"] = 15
    if prospect.demo_sent_at and not events and prospect.demo_sent_at < _now() - timedelta(days=3):
        points["sem_atividade_apos_envio"] = -10

    score = max(0, sum(points.values()))
    if score >= 75:
        temperature = "muito_quente"
    elif score >= 45:
        temperature = "quente"
    elif score >= 15:
        temperature = "morno"
    else:
        temperature = "frio"

    old_temperature = prospect.temperature
    prospect.score = score
    prospect.temperature = temperature
    prospect.score_explanation = {"points": points, "event_counts": counts, "sessions": sessions}
    if old_temperature != temperature:
        add_timeline(
            db,
            prospect,
            event_type="score.temperature_changed",
            event_label=f"Temperatura comercial atualizada para {temperature}",
            payload={"from": old_temperature, "to": temperature, "score": score},
        )
    db.add(prospect)
    db.commit()
    db.refresh(prospect)
    return prospect


def _ai_draft(db: Session, prospect: ProspectAccount, services: list[ProspectService]) -> dict:
    input_data = jsonable_encoder({
        "clinic_name": prospect.clinic_name,
        "city": prospect.city,
        "state": prospect.state,
        "main_address": prospect.main_address,
        "main_pain": prospect.main_pain,
        "services": [serialize_service(service) for service in services],
    })
    prompt = (
        "Gere um rascunho JSON para configurar uma demo de SaaS odontologico. "
        "Nao invente telefone, endereco ou dado sensivel. Marque inferencias em campos com inferred=true. "
        "Campos esperados: institutional_summary, voice_tone, scheduling_policy, faq, greeting, service_descriptions, ai_knowledge. "
        f"Dados: {json.dumps(jsonable_encoder(input_data), ensure_ascii=True)}"
    )
    run = AIProvisioningRun(prospect_account_id=prospect.id, status="running", input_json=input_data, model_name=settings.llm_model)
    db.add(run)
    db.flush()

    try:
        from app.services.llm_service import run_llm_task

        result = run_llm_task(db, tenant_id=None, conversation_id=None, task="sales_demo_provisioning", prompt=prompt)
        output_text = result.get("output", "")
        try:
            parsed = json.loads(output_text)
        except Exception:
            parsed = {"raw": output_text}
        run.status = "success"
        run.output_json = parsed
        run.completed_at = _now()
        db.add(run)
        db.commit()
        return parsed
    except Exception as exc:
        fallback = build_fallback_ai_draft(prospect, services)
        run.status = "failed"
        run.output_json = fallback
        run.error_message = str(exc)
        run.completed_at = _now()
        db.add(run)
        db.commit()
        return fallback


def build_fallback_ai_draft(prospect: ProspectAccount, services: list[ProspectService]) -> dict:
    service_names = [service.service_name for service in services] or ["Avaliacao odontologica", "Clareamento dental", "Limpeza odontologica"]
    return {
        "institutional_summary": f"{prospect.clinic_name} atende pacientes com foco em acolhimento, organizacao de agenda e acompanhamento de retorno.",
        "voice_tone": "Profissional, cordial, objetivo e consultivo.",
        "scheduling_policy": "Confirmar disponibilidade, oferecer horarios proximos e registrar necessidade de retorno apos o atendimento.",
        "greeting": f"Ola! Sou a assistente da {prospect.clinic_name}. Posso te ajudar com informacoes e agendamento.",
        "faq": [
            {"question": "Quais servicos voces realizam?", "answer": f"Atendemos principalmente: {', '.join(service_names)}."},
            {"question": "Como agendar?", "answer": "Posso verificar horarios disponiveis e direcionar para o melhor profissional."},
        ],
        "service_descriptions": [
            {"name": name, "description": f"Atendimento de {name} com orientacao e agendamento pela recepcao.", "inferred": True}
            for name in service_names
        ],
        "ai_knowledge": {
            "services": service_names,
            "main_pain": prospect.main_pain,
            "do_not_invent_sensitive_data": True,
        },
    }


def _ensure_plan(db: Session) -> TenantPlan:
    plan = db.scalar(select(TenantPlan).where(TenantPlan.code == "starter"))
    if plan:
        return plan
    plan = TenantPlan(
        code="starter",
        name="Starter",
        max_users=8,
        max_units=2,
        max_monthly_messages=4000,
        price_cents=39900,
        currency="BRL",
        features={"demo": True},
        is_active=True,
    )
    db.add(plan)
    db.flush()
    return plan


def _ensure_demo_services(db: Session, prospect: ProspectAccount) -> list[ProspectService]:
    services = db.execute(select(ProspectService).where(ProspectService.prospect_account_id == prospect.id)).scalars().all()
    if services:
        return services
    defaults = [
        ("Avaliacao odontologica", "Consulta", 45),
        ("Limpeza odontologica", "Preventivo", 60),
        ("Clareamento dental", "Estetica", 75),
    ]
    for name, category, duration in defaults:
        service = ProspectService(
            prospect_account_id=prospect.id,
            service_name=name,
            category=category,
            duration_minutes=duration,
            description=f"Servico demo de {name.lower()} para apresentacao comercial.",
        )
        db.add(service)
        services.append(service)
    db.flush()
    return services


def _ensure_demo_units(db: Session, prospect: ProspectAccount) -> list[ProspectUnit]:
    units = db.execute(select(ProspectUnit).where(ProspectUnit.prospect_account_id == prospect.id)).scalars().all()
    if units:
        return units
    unit = ProspectUnit(
        prospect_account_id=prospect.id,
        unit_name="Unidade principal",
        address=prospect.main_address or f"{prospect.city or 'Cidade'} - {prospect.state or 'BR'}",
        phone=prospect.phone,
        email=prospect.email,
        is_primary=True,
    )
    db.add(unit)
    db.flush()
    return [unit]


def _service_catalog_items_from_services(services: list[ProspectService]) -> list[dict]:
    return [
        {
            "id": _slugify(service.service_name),
            "name": service.service_name,
            "duration_minutes": service.duration_minutes,
            "price_note": service.price_range or "sob consulta",
            "description": service.description or service.service_name,
            "is_active": True,
        }
        for service in services
    ]


def _upsert_setting(db: Session, *, tenant_id: UUID, key: str, value: dict) -> None:
    item = db.scalar(select(Setting).where(Setting.tenant_id == tenant_id, Setting.key == key))
    if not item:
        item = Setting(tenant_id=tenant_id, key=key, value=jsonable_encoder(value), is_secret=False)
    else:
        item.value = jsonable_encoder(value)
        item.is_secret = False
    db.add(item)


def _sync_demo_service_catalog(
    db: Session,
    *,
    tenant_id: UUID,
    services: list[ProspectService],
    demo_units: list[Unit],
) -> None:
    catalog_items = _service_catalog_items_from_services(services)
    service_names = [item["name"] for item in catalog_items]

    _upsert_setting(db, tenant_id=tenant_id, key="service_catalog.global", value={"items": catalog_items})
    _upsert_setting(db, tenant_id=tenant_id, key="services.catalog", value={"services": catalog_items})

    for unit in demo_units:
        _upsert_setting(db, tenant_id=tenant_id, key=f"unit.services.{unit.id}", value={"services": service_names})

    professionals = db.execute(select(Professional).where(Professional.tenant_id == tenant_id)).scalars().all()
    for professional in professionals:
        professional.procedures = service_names
        db.add(professional)


def _create_settings(db: Session, *, tenant_id: UUID, prospect: ProspectAccount, ai_draft: dict, services: list[ProspectService]) -> None:
    catalog_items = _service_catalog_items_from_services(services)
    settings_payloads = {
        "clinic.profile": {
            "name": prospect.clinic_name,
            "trade_name": prospect.clinic_name,
            "main_phone": prospect.phone,
            "whatsapp_phone": prospect.whatsapp_phone,
            "email": prospect.email,
            "site": prospect.website,
            "city": prospect.city,
            "state": prospect.state,
            "address": prospect.main_address,
            "institutional_summary": ai_draft.get("institutional_summary"),
            "sales_origin": "adm_prospect_demo",
        },
        "clinic.timezone": {"value": "America/Sao_Paulo"},
        "ai_knowledge_base.global": {
            "clinic_profile": {
                "clinic_name": prospect.clinic_name,
                "city": prospect.city,
                "state": prospect.state,
                "institutional_summary": ai_draft.get("institutional_summary"),
                "welcome_greeting_example": ai_draft.get("greeting"),
            },
            "services": [
                {
                    "name": item["name"],
                    "description": item["description"],
                    "duration_note": f"{item['duration_minutes']} min" if item.get("duration_minutes") else "",
                    "price_note": item.get("price_note") or "",
                }
                for item in catalog_items
            ],
            "faq": ai_draft.get("faq", []),
        },
        "ai.knowledge": {
            "voice_tone": ai_draft.get("voice_tone"),
            "greeting": ai_draft.get("greeting"),
            "faq": ai_draft.get("faq", []),
            "knowledge": ai_draft.get("ai_knowledge", {}),
            "scheduling_policy": ai_draft.get("scheduling_policy"),
        },
        "demo.sales": {
            "prospect_account_id": str(prospect.id),
            "test_phone_number": prospect.test_phone_number,
            "tracking_enabled": True,
        },
    }
    for key, value in settings_payloads.items():
        _upsert_setting(db, tenant_id=tenant_id, key=key, value=value)


def _default_demo_guide_state() -> dict:
    return {
        "version": DEMO_GUIDE_VERSION,
        "enabled": False,
        "current_step_id": DEMO_GUIDE_STEPS[0]["id"],
        "completed_step_ids": [],
        "started_at": None,
        "completed_at": None,
        "dismissed_at": None,
    }


def _next_demo_guide_step_id(completed_step_ids: list[str]) -> str | None:
    completed = set(completed_step_ids)
    for step in DEMO_GUIDE_STEPS:
        if step["id"] not in completed:
            return step["id"]
    return None


def _coerce_demo_guide_state(value: dict | None) -> dict:
    if not isinstance(value, dict) or int(value.get("version") or 0) != DEMO_GUIDE_VERSION:
        return _default_demo_guide_state()

    completed_step_ids: list[str] = []
    for raw_step_id in value.get("completed_step_ids") or []:
        step_id = str(raw_step_id or "").strip()
        if step_id in DEMO_GUIDE_STEP_LOOKUP and step_id not in completed_step_ids:
            completed_step_ids.append(step_id)

    next_step_id = _next_demo_guide_step_id(completed_step_ids)
    current_step_id = str(value.get("current_step_id") or "").strip()
    if current_step_id not in DEMO_GUIDE_STEP_LOOKUP:
        current_step_id = next_step_id or DEMO_GUIDE_STEPS[-1]["id"]

    completed_at = value.get("completed_at") if not next_step_id else None

    return {
        "version": DEMO_GUIDE_VERSION,
        "enabled": bool(value.get("enabled", False)),
        "current_step_id": current_step_id,
        "completed_step_ids": completed_step_ids,
        "started_at": value.get("started_at"),
        "completed_at": completed_at,
        "dismissed_at": value.get("dismissed_at"),
    }


def _demo_guide_status(state: dict) -> str:
    if state.get("completed_at"):
        return "completed"
    if state.get("dismissed_at"):
        return "dismissed"
    if state.get("started_at"):
        return "active"
    return "not_started"


def ensure_demo_guide_state(db: Session, *, tenant_id: UUID) -> dict:
    existing = db.scalar(select(Setting).where(Setting.tenant_id == tenant_id, Setting.key == DEMO_GUIDE_SETTING_KEY))
    state = _coerce_demo_guide_state(existing.value if existing else None)
    if not existing or jsonable_encoder(existing.value or {}) != jsonable_encoder(state):
        _upsert_setting(db, tenant_id=tenant_id, key=DEMO_GUIDE_SETTING_KEY, value=state)
    return state


def _serialize_demo_guide_state(state: dict) -> dict:
    current_step = DEMO_GUIDE_STEP_LOOKUP[state["current_step_id"]]
    return {
        "version": DEMO_GUIDE_VERSION,
        "enabled": bool(state.get("enabled", False)),
        "status": _demo_guide_status(state),
        "current_step_id": state["current_step_id"],
        "current_step_order": current_step["order"],
        "completed_step_ids": list(state["completed_step_ids"]),
        "completed_count": len(state["completed_step_ids"]),
        "total_steps": len(DEMO_GUIDE_STEPS),
        "started_at": state.get("started_at"),
        "completed_at": state.get("completed_at"),
        "dismissed_at": state.get("dismissed_at"),
        "steps": DEMO_GUIDE_STEPS,
    }


def get_demo_guide_state(db: Session, *, tenant_id: UUID) -> dict:
    state = ensure_demo_guide_state(db, tenant_id=tenant_id)
    return _serialize_demo_guide_state(state)


def _seed_demo_automation_showcase(db: Session, *, tenant_id: UUID) -> None:
    existing = db.scalar(select(Automation.id).where(Automation.tenant_id == tenant_id))
    if existing:
        return

    now = _now()
    specs = [
        {
            "name": "Confirmacao 24h antes",
            "description": "Confirma consultas com antecedencia para reduzir faltas.",
            "trigger_type": AutomationTriggerType.TIME.value,
            "trigger_key": "consulta_24h",
            "is_active": True,
            "conditions": {"confirmation_status": "pendente"},
            "body": "Oi. Passando para confirmar sua consulta de amanha na clinica. Se precisar remarcar, responda por aqui.",
            "runs": [
                {"status": RunStatus.SUCCESS.value, "hours_ago": 26, "payload": {"patient": "Camila Rocha"}},
                {"status": RunStatus.SUCCESS.value, "hours_ago": 22, "payload": {"patient": "Joao Henrique Lima"}},
            ],
        },
        {
            "name": "Lembrete 2h antes",
            "description": "Reforca comparecimento no mesmo dia para organizar a cadeira.",
            "trigger_type": AutomationTriggerType.TIME.value,
            "trigger_key": "consulta_2h",
            "is_active": True,
            "conditions": {"confirmation_status": "confirmada"},
            "body": "Seu horario esta reservado para hoje. Se estiver a caminho, pode responder aqui para a recepcao acompanhar.",
            "runs": [
                {"status": RunStatus.SUCCESS.value, "hours_ago": 4, "payload": {"patient": "Patricia Alves"}},
            ],
        },
        {
            "name": "Recuperacao de faltas",
            "description": "Tenta recuperar pacientes que faltaram sem precisar ligar um a um.",
            "trigger_type": AutomationTriggerType.EVENT.value,
            "trigger_key": "paciente_faltou",
            "is_active": True,
            "conditions": {"attendance_status": "faltou"},
            "body": "Percebemos que voce nao conseguiu vir hoje. Posso te ajudar a remarcar para outro horario?",
            "runs": [
                {"status": RunStatus.SUCCESS.value, "hours_ago": 48, "payload": {"patient": "Lucas Demo"}},
                {
                    "status": RunStatus.FAILED.value,
                    "hours_ago": 36,
                    "payload": {"patient": "Mariana Demo"},
                    "error_message": "Numero sem WhatsApp ativo",
                },
            ],
        },
        {
            "name": "Follow-up de orcamento",
            "description": "Retoma propostas em aberto para recuperar oportunidades comerciais.",
            "trigger_type": AutomationTriggerType.EVENT.value,
            "trigger_key": "orcamento_pendente_2d",
            "is_active": False,
            "conditions": {"days_without_reply": 2},
            "body": "Fiquei com seu plano de tratamento em aberto. Quer que eu te mostre opcoes de agenda para seguir?",
            "runs": [
                {"status": RunStatus.SUCCESS.value, "hours_ago": 72, "payload": {"lead": "Camila Rocha"}},
            ],
        },
    ]

    for spec in specs:
        automation = Automation(
            tenant_id=tenant_id,
            name=spec["name"],
            description=spec["description"],
            trigger_type=spec["trigger_type"],
            trigger_key=spec["trigger_key"],
            conditions=spec["conditions"],
            actions=[{"type": "send_message", "params": {"body": spec["body"]}}],
            retry_policy={"max_attempts": 3},
            is_active=spec["is_active"],
            paused_at=None if spec["is_active"] else now - timedelta(days=1),
        )
        db.add(automation)
        db.flush()

        for run_spec in spec["runs"]:
            started_at = now - timedelta(hours=run_spec["hours_ago"])
            finished_at = started_at + timedelta(minutes=2)
            db.add(
                AutomationRun(
                    tenant_id=tenant_id,
                    automation_id=automation.id,
                    status=run_spec["status"],
                    trigger_payload=run_spec["payload"],
                    result_payload={"channel": "whatsapp", "delivered": run_spec["status"] == RunStatus.SUCCESS.value},
                    error_message=run_spec.get("error_message"),
                    started_at=started_at,
                    finished_at=finished_at,
                    retries=0 if run_spec["status"] == RunStatus.SUCCESS.value else 1,
                )
            )


def ensure_demo_showcase_state(db: Session, *, prospect: ProspectAccount) -> None:
    if not prospect.demo_tenant_id:
        return
    ensure_demo_guide_state(db, tenant_id=prospect.demo_tenant_id)
    _seed_demo_automation_showcase(db, tenant_id=prospect.demo_tenant_id)


def resume_demo_guide(
    db: Session,
    *,
    prospect: ProspectAccount,
    user_id: UUID | None,
    page_path: str | None,
    session_id: str | None,
    source: str | None,
) -> dict:
    ensure_demo_showcase_state(db, prospect=prospect)
    state = ensure_demo_guide_state(db, tenant_id=prospect.demo_tenant_id)
    if state.get("completed_at"):
        return _serialize_demo_guide_state(state)

    now = _now()
    if not state.get("started_at"):
        state["started_at"] = now
    state["dismissed_at"] = None
    state["current_step_id"] = _next_demo_guide_step_id(state["completed_step_ids"]) or DEMO_GUIDE_STEPS[-1]["id"]
    _upsert_setting(db, tenant_id=prospect.demo_tenant_id, key=DEMO_GUIDE_SETTING_KEY, value=state)
    record_demo_event(
        db,
        prospect=prospect,
        user_id=user_id,
        event_name="demo_guided_started",
        page_path=page_path,
        session_id=session_id,
        payload={
            "source": source or "resume",
            "step_id": state["current_step_id"],
            "step_order": DEMO_GUIDE_STEP_LOOKUP[state["current_step_id"]]["order"],
            "step_title": DEMO_GUIDE_STEP_LOOKUP[state["current_step_id"]]["title"],
        },
    )
    return get_demo_guide_state(db, tenant_id=prospect.demo_tenant_id)


def complete_demo_guide_step(
    db: Session,
    *,
    prospect: ProspectAccount,
    user_id: UUID | None,
    step_id: str,
    page_path: str | None,
    session_id: str | None,
    source: str | None,
) -> dict:
    ensure_demo_showcase_state(db, prospect=prospect)
    state = ensure_demo_guide_state(db, tenant_id=prospect.demo_tenant_id)
    if step_id not in DEMO_GUIDE_STEP_LOOKUP:
        raise ApiError(status_code=400, code="DEMO_GUIDE_STEP_INVALID", message="Etapa do guia invalida")

    if step_id not in state["completed_step_ids"]:
        state["completed_step_ids"].append(step_id)
        state["completed_step_ids"].sort(key=lambda item: DEMO_GUIDE_STEP_LOOKUP[item]["order"])

    if not state.get("started_at"):
        state["started_at"] = _now()
    state["dismissed_at"] = None
    next_step_id = _next_demo_guide_step_id(state["completed_step_ids"])
    state["current_step_id"] = next_step_id or DEMO_GUIDE_STEPS[-1]["id"]
    if next_step_id is None:
        state["completed_at"] = _now()

    _upsert_setting(db, tenant_id=prospect.demo_tenant_id, key=DEMO_GUIDE_SETTING_KEY, value=state)
    step = DEMO_GUIDE_STEP_LOOKUP[step_id]
    record_demo_event(
        db,
        prospect=prospect,
        user_id=user_id,
        event_name="demo_guided_step_completed",
        page_path=page_path,
        session_id=session_id,
        payload={
            "source": source or "cta",
            "step_id": step_id,
            "step_order": step["order"],
            "step_title": step["title"],
        },
    )
    if state.get("completed_at"):
        record_demo_event(
            db,
            prospect=prospect,
            user_id=user_id,
            event_name="demo_guided_completed",
            page_path=page_path,
            session_id=session_id,
            payload={
                "source": source or "cta",
                "step_id": step_id,
                "step_order": step["order"],
                "step_title": step["title"],
            },
    )
    return get_demo_guide_state(db, tenant_id=prospect.demo_tenant_id)


def go_back_demo_guide_step(
    db: Session,
    *,
    prospect: ProspectAccount,
    user_id: UUID | None,
    page_path: str | None,
    session_id: str | None,
    source: str | None,
) -> dict:
    ensure_demo_showcase_state(db, prospect=prospect)
    state = ensure_demo_guide_state(db, tenant_id=prospect.demo_tenant_id)

    current_step = DEMO_GUIDE_STEP_LOOKUP[state["current_step_id"]]
    previous_step = next((step for step in reversed(DEMO_GUIDE_STEPS) if step["order"] == current_step["order"] - 1), None)
    target_step = previous_step or DEMO_GUIDE_STEPS[0]

    if not state.get("started_at"):
        state["started_at"] = _now()
    state["dismissed_at"] = None
    state["completed_at"] = None
    state["current_step_id"] = target_step["id"]

    _upsert_setting(db, tenant_id=prospect.demo_tenant_id, key=DEMO_GUIDE_SETTING_KEY, value=state)
    record_demo_event(
        db,
        prospect=prospect,
        user_id=user_id,
        event_name="demo_guided_step_backtracked",
        page_path=page_path,
        session_id=session_id,
        payload={
            "source": source or "back",
            "from_step_id": current_step["id"],
            "from_step_order": current_step["order"],
            "from_step_title": current_step["title"],
            "step_id": target_step["id"],
            "step_order": target_step["order"],
            "step_title": target_step["title"],
        },
    )
    return get_demo_guide_state(db, tenant_id=prospect.demo_tenant_id)


def dismiss_demo_guide(
    db: Session,
    *,
    prospect: ProspectAccount,
    user_id: UUID | None,
    page_path: str | None,
    session_id: str | None,
    source: str | None,
) -> dict:
    ensure_demo_showcase_state(db, prospect=prospect)
    state = ensure_demo_guide_state(db, tenant_id=prospect.demo_tenant_id)
    if not state.get("started_at"):
        state["started_at"] = _now()
    state["dismissed_at"] = _now()
    _upsert_setting(db, tenant_id=prospect.demo_tenant_id, key=DEMO_GUIDE_SETTING_KEY, value=state)
    current_step = DEMO_GUIDE_STEP_LOOKUP[state["current_step_id"]]
    record_demo_event(
        db,
        prospect=prospect,
        user_id=user_id,
        event_name="demo_guided_dismissed",
        page_path=page_path,
        session_id=session_id,
        payload={
            "source": source or "dismiss",
            "step_id": current_step["id"],
            "step_order": current_step["order"],
            "step_title": current_step["title"],
        },
    )
    return get_demo_guide_state(db, tenant_id=prospect.demo_tenant_id)


def generate_demo(db: Session, prospect: ProspectAccount, *, actor_id: UUID | None, base_url: str) -> dict:
    if prospect.demo_tenant_id:
        services = _ensure_demo_services(db, prospect)
        demo_tenant = db.get(Tenant, prospect.demo_tenant_id)
        demo_units = db.execute(select(Unit).where(Unit.tenant_id == prospect.demo_tenant_id)).scalars().all()
        demo_user = db.get(User, prospect.demo_user_id) if prospect.demo_user_id else None
        professionals = db.execute(select(Professional).where(Professional.tenant_id == prospect.demo_tenant_id)).scalars().all()
        _sync_demo_service_catalog(db, tenant_id=prospect.demo_tenant_id, services=services, demo_units=demo_units)
        if demo_tenant and demo_units and demo_user:
            _seed_demo_operational_data(
                db,
                tenant=demo_tenant,
                unit=demo_units[0],
                user=demo_user,
                services=services,
                professionals=professionals,
            )
            checklist = {**(prospect.demo_checklist or {})}
            checklist["agenda_seeded"] = True
            checklist["conversations_seeded"] = True
            prospect.demo_checklist = checklist
            db.add(prospect)
        ensure_demo_showcase_state(db, prospect=prospect)
        add_timeline(
            db,
            prospect,
            event_type="demo.catalog_synced",
            event_label="Catalogo oficial de servicos sincronizado na demo",
            actor_id=actor_id,
            actor_type="admin",
        )
        db.commit()
        db.refresh(prospect)
        raw_token = issue_demo_access(db, prospect, actor_id=actor_id)
        return {
            "prospect": prospect,
            "access_token": raw_token,
            "demo_login_url": f"{base_url}/login?demo_token={raw_token}",
            "checklist": prospect.demo_checklist,
            "ai_draft": _latest_ai_output(db, prospect.id),
        }

    services = _ensure_demo_services(db, prospect)
    prospect_units = _ensure_demo_units(db, prospect)
    ai_draft = _ai_draft(db, prospect, services)
    roles = ensure_sales_roles(db)
    plan = _ensure_plan(db)
    slug_base = prospect.tenant_seed_key or f"{_slugify(prospect.clinic_name)}-{secrets.token_hex(3)}"
    slug = f"demo-{slug_base}"
    slug_candidate = slug
    index = 2
    while db.scalar(select(Tenant).where(Tenant.slug == slug_candidate)):
        slug_candidate = f"{slug}-{index}"
        index += 1

    tenant = Tenant(
        plan_id=plan.id,
        legal_name=prospect.clinic_name,
        trade_name=prospect.clinic_name,
        slug=slug_candidate,
        timezone="America/Sao_Paulo",
        locale="pt-BR",
        currency="BRL",
        subscription_status="trialing",
        trial_ends_at=_now() + timedelta(days=settings.demo_default_expire_days),
        is_active=True,
    )
    db.add(tenant)
    db.flush()

    demo_units: list[Unit] = []
    for idx, prospect_unit in enumerate(prospect_units, start=1):
        unit = Unit(
            tenant_id=tenant.id,
            name=prospect_unit.unit_name,
            code=f"DEMO-{idx}",
            phone=prospect_unit.phone or prospect.phone,
            email=prospect_unit.email or prospect.email,
            address={"raw": prospect_unit.address, "city": prospect.city, "state": prospect.state},
            working_hours={"monday_friday": "08:00-18:00"},
            is_active=True,
        )
        db.add(unit)
        db.flush()
        demo_units.append(unit)

    professional_names = [
        ("Dra. Ana Beatriz Moura", "Clinico geral"),
        ("Dr. Rafael Campos", "Reabilitacao oral"),
        ("Dra. Marina Lopes", "Estetica dental"),
    ]
    service_names = [service.service_name for service in services]
    professionals: list[Professional] = []
    for unit in demo_units:
        for name, specialty in professional_names:
            professional = Professional(
                tenant_id=tenant.id,
                unit_id=unit.id,
                full_name=name,
                cro_number=f"DEMO-{secrets.randbelow(90000) + 10000}",
                specialty=specialty,
                working_days=[1, 2, 3, 4, 5],
                shift_start="08:00",
                shift_end="18:00",
                procedures=service_names,
                is_active=True,
            )
            db.add(professional)
            professionals.append(professional)
    db.flush()

    demo_email = prospect.demo_login_email or _demo_email(prospect)
    password = _random_password()
    existing_user = db.scalar(select(User).where(User.email == demo_email))
    if existing_user:
        demo_email = f"demo+{slug_candidate}@demo.odontoflux.app"
    demo_user = User(
        tenant_id=tenant.id,
        unit_id=demo_units[0].id if demo_units else None,
        email=demo_email,
        full_name=prospect.owner_name or prospect.manager_name or f"Gestor {prospect.clinic_name}",
        phone=prospect.whatsapp_phone or prospect.phone,
        hashed_password=hash_password(password),
        is_active=True,
        page_permissions={
            "demo_client": {"enabled": True},
            "presentation_mode": {"enabled": True},
        },
        email_verified_at=_now(),
        force_fullscreen_mode=False,
    )
    db.add(demo_user)
    db.flush()
    for role_name in ["owner", "demo_client"]:
        db.add(UserRole(tenant_id=tenant.id, user_id=demo_user.id, role_id=roles[role_name].id))

    _create_settings(db, tenant_id=tenant.id, prospect=prospect, ai_draft=ai_draft, services=services)
    _sync_demo_service_catalog(db, tenant_id=tenant.id, services=services, demo_units=demo_units)
    _seed_demo_operational_data(db, tenant=tenant, unit=demo_units[0], user=demo_user, services=services, professionals=professionals)
    ensure_demo_guide_state(db, tenant_id=tenant.id)
    _seed_demo_automation_showcase(db, tenant_id=tenant.id)

    checklist = {key: True for key in DEMO_CHECKLIST_KEYS}
    checklist["test_phone_configured"] = bool(prospect.test_phone_number)
    prospect.demo_tenant_id = tenant.id
    prospect.demo_user_id = demo_user.id
    prospect.demo_login_email = demo_email
    prospect.demo_status = "pronta"
    prospect.demo_expires_at = _now() + timedelta(days=settings.demo_default_expire_days)
    prospect.demo_checklist = checklist
    prospect.status = "demo_criada"
    add_timeline(db, prospect, event_type="demo.created", event_label="Demo personalizada gerada", actor_id=actor_id, actor_type="admin", payload={"tenant_id": str(tenant.id)})
    db.add(prospect)
    db.commit()
    db.refresh(prospect)
    raw_token = issue_demo_access(db, prospect, actor_id=actor_id)
    return {
        "prospect": prospect,
        "access_token": raw_token,
        "demo_login_url": f"{base_url}/login?demo_token={raw_token}",
        "checklist": prospect.demo_checklist,
        "ai_draft": ai_draft,
    }


def _seed_demo_operational_data(
    db: Session,
    *,
    tenant: Tenant,
    unit: Unit,
    user: User,
    services: list[ProspectService],
    professionals: list[Professional],
) -> None:
    service_names = [service.service_name for service in services] or ["Avaliacao odontologica"]
    unit_professionals = [professional for professional in professionals if professional.unit_id == unit.id] or professionals
    showcase_week_start = _next_demo_showcase_week_start(_now())
    weekday_labels = [
        "segunda-feira",
        "terca-feira",
        "quarta-feira",
        "quinta-feira",
        "sexta-feira",
        "sabado",
        "domingo",
    ]

    for idx, spec in enumerate(DEMO_OPERATIONAL_SHOWCASE_SPECS):
        normalized_phone = re.sub(r"\D+", "", spec["phone"])
        service_name = service_names[idx % len(service_names)]
        professional = unit_professionals[idx % len(unit_professionals)] if unit_professionals else None
        showcase_day = showcase_week_start + timedelta(days=idx)
        starts_at = _combine_day_and_time(showcase_day, spec["time"])
        ends_at = starts_at + timedelta(minutes=60)
        weekday_label = weekday_labels[starts_at.weekday()]
        date_label = starts_at.strftime("%d/%m/%Y")
        time_label = starts_at.strftime("%H:%M")

        patient = db.scalar(
            select(Patient).where(Patient.tenant_id == tenant.id, Patient.normalized_phone == normalized_phone)
        )
        if not patient:
            patient = Patient(
                tenant_id=tenant.id,
                unit_id=unit.id,
                full_name=spec["name"],
                phone=spec["phone"],
                normalized_phone=normalized_phone,
                email=None,
                operational_notes=spec["note"],
                status="ativo",
                origin="demo_personalizada",
                lgpd_consent=True,
                marketing_opt_in=False,
                tags_cache=["demo", "agenda_semana_demo"],
            )
        else:
            patient.unit_id = unit.id
            patient.full_name = spec["name"]
            patient.phone = spec["phone"]
            patient.operational_notes = spec["note"]
            patient.status = "ativo"
            patient.origin = patient.origin or "demo_personalizada"
            patient.lgpd_consent = True
            patient.tags_cache = sorted(set((patient.tags_cache or []) + ["demo", "agenda_semana_demo"]))
        db.add(patient)
        db.flush()

        lead = db.scalar(select(Lead).where(Lead.tenant_id == tenant.id, Lead.patient_id == patient.id))
        if not lead:
            lead = Lead(
                tenant_id=tenant.id,
                patient_id=patient.id,
                owner_user_id=user.id,
                name=patient.full_name,
                phone=patient.phone,
                origin="whatsapp_demo",
                interest=service_name,
                stage=LeadStage.QUALIFIED.value,
                score=60 + idx * 5,
                temperature=LeadTemperature.HOT.value if idx >= 2 else LeadTemperature.WARM.value,
                status="ativo",
                notes="Lead demo criado para apresentacao comercial.",
            )
        else:
            lead.owner_user_id = user.id
            lead.name = patient.full_name
            lead.phone = patient.phone
            lead.origin = lead.origin or "whatsapp_demo"
            lead.interest = service_name
            lead.stage = LeadStage.QUALIFIED.value
            lead.score = max(lead.score or 0, 60 + idx * 5)
            lead.temperature = LeadTemperature.HOT.value if idx >= 2 else LeadTemperature.WARM.value
            lead.status = "ativo"
            lead.notes = "Lead demo criado para apresentacao comercial."
        db.add(lead)
        db.flush()

        external_thread_id = f"demo-agendamento-{normalized_phone}"
        conversation = db.scalar(
            select(Conversation).where(
                Conversation.tenant_id == tenant.id,
                Conversation.external_thread_id == external_thread_id,
            )
        )
        if not conversation:
            conversation = db.scalar(
                select(Conversation)
                .where(
                    Conversation.tenant_id == tenant.id,
                    Conversation.patient_id == patient.id,
                    Conversation.channel == "whatsapp",
                )
                .order_by(Conversation.created_at.asc())
            )
        if not conversation:
            conversation = Conversation(
                tenant_id=tenant.id,
                unit_id=unit.id,
                patient_id=patient.id,
                lead_id=lead.id,
                channel="whatsapp",
                external_thread_id=external_thread_id,
                assigned_user_id=user.id,
                status="aberta",
                ai_summary=(
                    f"{patient.full_name} pediu {service_name} pelo WhatsApp e saiu com consulta demo agendada para "
                    f"{weekday_label}, {date_label}, as {time_label}."
                ),
                ai_autoresponder_enabled=True,
                tags=["demo", "whatsapp", "demo_agendamento_origem"],
                last_message_at=_now(),
            )
        else:
            conversation.unit_id = unit.id
            conversation.patient_id = patient.id
            conversation.lead_id = lead.id
            conversation.external_thread_id = external_thread_id
            conversation.assigned_user_id = user.id
            conversation.status = "aberta"
            conversation.ai_summary = (
                f"{patient.full_name} pediu {service_name} pelo WhatsApp e saiu com consulta demo agendada para "
                f"{weekday_label}, {date_label}, as {time_label}."
            )
            conversation.ai_autoresponder_enabled = True
            conversation.tags = sorted(set((conversation.tags or []) + ["demo", "whatsapp", "demo_agendamento_origem"]))
        db.add(conversation)
        db.flush()

        conversation_message_specs = [
            {
                "direction": MessageDirection.INBOUND.value,
                "sender_type": "patient",
                "body": f"Ola, queria agendar {service_name}. Voces tem um horario na {weekday_label}?",
                "status": MessageStatus.RECEIVED.value,
                "sent_at": _now() - timedelta(hours=12 - idx),
            },
            {
                "direction": MessageDirection.OUTBOUND.value,
                "sender_type": "ai",
                "body": (
                    f"Tenho sim. Separei {weekday_label}, {date_label}, as {time_label}"
                    + (f" com {professional.full_name}." if professional else ".")
                    + " Posso seguir com o agendamento?"
                ),
                "status": MessageStatus.READ.value,
                "sent_at": _now() - timedelta(hours=11 - idx, minutes=40),
            },
            {
                "direction": MessageDirection.INBOUND.value,
                "sender_type": "patient",
                "body": "Pode confirmar esse horario para mim.",
                "status": MessageStatus.RECEIVED.value,
                "sent_at": _now() - timedelta(hours=11 - idx, minutes=15),
            },
            {
                "direction": MessageDirection.OUTBOUND.value,
                "sender_type": "ai",
                "body": (
                    f"Pronto. Seu horario de {service_name} ficou confirmado para {weekday_label}, {date_label}, "
                    f"as {time_label}."
                ),
                "status": MessageStatus.READ.value,
                "sent_at": _now() - timedelta(hours=10 - idx, minutes=45),
            },
        ]
        existing_bodies = {
            row[0]
            for row in db.execute(
                select(Message.body).where(
                    Message.tenant_id == tenant.id,
                    Message.conversation_id == conversation.id,
                )
            ).all()
        }
        for message_spec in conversation_message_specs:
            if message_spec["body"] in existing_bodies:
                continue
            message = Message(
                tenant_id=tenant.id,
                conversation_id=conversation.id,
                direction=message_spec["direction"],
                channel="whatsapp",
                sender_type=message_spec["sender_type"],
                sender_user_id=user.id if message_spec["direction"] == MessageDirection.OUTBOUND.value else None,
                body=message_spec["body"],
                status=message_spec["status"],
                sent_at=message_spec["sent_at"],
                delivered_at=message_spec["sent_at"] if message_spec["status"] == MessageStatus.READ.value else None,
                read_at=message_spec["sent_at"] if message_spec["status"] == MessageStatus.READ.value else None,
            )
            db.add(message)

        conversation.last_message_at = conversation_message_specs[-1]["sent_at"]
        db.add(conversation)

        appointment = db.scalar(
            select(Appointment).where(
                Appointment.tenant_id == tenant.id,
                Appointment.patient_id == patient.id,
                Appointment.starts_at == starts_at,
            )
        )
        if not appointment:
            appointment = db.scalar(
                select(Appointment)
                .where(
                    Appointment.tenant_id == tenant.id,
                    Appointment.patient_id == patient.id,
                    Appointment.origin == "demo_personalizada",
                )
                .order_by(Appointment.created_at.asc())
            )
        if not appointment:
            appointment = Appointment(
                tenant_id=tenant.id,
                patient_id=patient.id,
                unit_id=unit.id,
                professional_id=professional.id if professional else None,
                procedure_type=service_name,
                starts_at=starts_at,
                ends_at=ends_at,
                status=AppointmentStatus.CONFIRMED.value,
                origin="demo_personalizada",
                notes="Consulta demo gerada a partir da conversa comercial de WhatsApp.",
                confirmation_status="confirmada",
                confirmed_at=_now(),
            )
        else:
            appointment.unit_id = unit.id
            appointment.professional_id = professional.id if professional else None
            appointment.procedure_type = service_name
            appointment.starts_at = starts_at
            appointment.ends_at = ends_at
            appointment.status = AppointmentStatus.CONFIRMED.value
            appointment.origin = "demo_personalizada"
            appointment.notes = "Consulta demo gerada a partir da conversa comercial de WhatsApp."
            appointment.confirmation_status = "confirmada"
            appointment.confirmed_at = appointment.confirmed_at or _now()
        db.add(appointment)


def _latest_ai_output(db: Session, prospect_id: UUID) -> dict:
    run = db.scalar(
        select(AIProvisioningRun)
        .where(AIProvisioningRun.prospect_account_id == prospect_id)
        .order_by(AIProvisioningRun.created_at.desc())
    )
    return run.output_json if run else {}


def issue_demo_access(db: Session, prospect: ProspectAccount, *, actor_id: UUID | None) -> str:
    if not prospect.demo_tenant_id or not prospect.demo_user_id:
        raise ApiError(status_code=400, code="DEMO_NOT_CREATED", message="Gere a demo antes de emitir acesso")
    raw_token = secrets.token_urlsafe(36)
    prospect.demo_access_token_hash = sha256_text(raw_token)
    prospect.demo_access_token_expires_at = _now() + timedelta(hours=settings.demo_access_token_expire_hours)
    prospect.demo_access_revoked_at = None
    prospect.demo_sent_at = _now()
    if prospect.status in {"demo_criada", "decisor_identificado", "respondeu", "contato_iniciado", "novo"}:
        prospect.status = "demo_enviada"
    prospect.demo_status = "enviada"
    add_timeline(db, prospect, event_type="demo.access_issued", event_label="Acesso de demo emitido", actor_id=actor_id, actor_type="admin")
    db.add(prospect)
    db.commit()
    db.refresh(prospect)
    return raw_token


def _build_demo_whatsapp_link(phone: str | None) -> str | None:
    normalized = normalize_phone(phone)
    if len(normalized) < 12:
        return None
    return f"https://wa.me/{normalized}"


def redeem_demo_token(db: Session, *, token: str, session_id: str | None = None) -> dict:
    token_hash = sha256_text(token)
    prospect = db.scalar(select(ProspectAccount).where(ProspectAccount.demo_access_token_hash == token_hash))
    if not prospect or not prospect.demo_user_id or not prospect.demo_tenant_id:
        raise ApiError(status_code=401, code="DEMO_TOKEN_INVALID", message="Acesso de demo invalido")
    if prospect.demo_access_revoked_at:
        raise ApiError(status_code=401, code="DEMO_TOKEN_REVOKED", message="Acesso de demo revogado")
    if prospect.demo_access_token_expires_at and prospect.demo_access_token_expires_at < _now():
        prospect.demo_status = "expirada"
        db.add(prospect)
        db.commit()
        raise ApiError(status_code=401, code="DEMO_TOKEN_EXPIRED", message="Acesso de demo expirado")

    user = db.get(User, prospect.demo_user_id)
    if not user or not user.is_active:
        raise ApiError(status_code=401, code="DEMO_USER_INVALID", message="Usuario de demo invalido")
    roles = [row[0] for row in db.execute(select(Role.name).join(UserRole, UserRole.role_id == Role.id).where(UserRole.user_id == user.id)).all()]
    access_token = create_access_token(subject=str(user.id), tenant_id=user.tenant_id, roles=roles)
    refresh_token = create_refresh_token(subject=str(user.id), tenant_id=user.tenant_id, roles=roles)
    now = _now()
    if not prospect.demo_first_login_at:
        prospect.demo_first_login_at = now
    prospect.demo_last_login_at = now
    prospect.last_activity_at = now
    prospect.status = "demo_acessada"
    prospect.demo_status = "acessada"
    ensure_demo_showcase_state(db, prospect=prospect)
    event = DemoActivityEvent(
        prospect_account_id=prospect.id,
        demo_tenant_id=prospect.demo_tenant_id,
        demo_user_id=prospect.demo_user_id,
        session_id=session_id,
        event_name="login_completed",
        page_path="/login",
        payload_json={"source": "magic_link"},
        occurred_at=now,
    )
    db.add(event)
    add_timeline(db, prospect, event_type="demo.login_completed", event_label="Cliente acessou a demo", actor_type="demo_client")
    db.add(prospect)
    db.commit()
    recalculate_score(db, prospect)
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "expires_in": settings.api_access_token_expire_minutes * 60,
        "demo_test_phone_number": prospect.test_phone_number,
        "demo_whatsapp_link": _build_demo_whatsapp_link(prospect.test_phone_number),
        "demo_target_path": "/conversas",
    }


def record_demo_event(db: Session, *, prospect: ProspectAccount, user_id: UUID | None, event_name: str, page_path: str | None, session_id: str | None, payload: dict | None = None) -> DemoActivityEvent:
    now = _now()
    payload_json = jsonable_encoder(payload or {})
    event = DemoActivityEvent(
        prospect_account_id=prospect.id,
        demo_tenant_id=prospect.demo_tenant_id,
        demo_user_id=user_id or prospect.demo_user_id,
        session_id=session_id,
        event_name=event_name,
        page_path=page_path,
        payload_json=payload_json,
        occurred_at=now,
    )
    prospect.last_activity_at = now
    status_by_event = {
        "visited_agenda": "visitou_agenda",
        "visited_settings": "configurou_dados",
        "tested_whatsapp_flow": "testou_whatsapp",
    }
    if event_name in status_by_event:
        prospect.status = status_by_event[event_name]
    event_labels = {
        "login_completed": "Cliente acessou a demo",
        "visited_conversations": "Cliente visitou WhatsApp",
        "visited_agenda": "Cliente visitou Agenda",
        "visited_patients": "Cliente visitou Pacientes",
        "visited_settings": "Cliente visitou Configuracoes",
        "visited_team": "Cliente visitou Equipe medica",
        "visited_services": "Cliente visitou Servicos",
        "visited_units": "Cliente visitou Unidades",
        "visited_leads": "Cliente visitou Leads",
        "demo_guided_started": "Cliente iniciou o guia da demo",
        "demo_guided_step_viewed": "Cliente visualizou uma etapa do guia",
        "demo_guided_step_completed": "Cliente concluiu uma etapa do guia",
        "demo_guided_dismissed": "Cliente fechou o guia da demo",
        "demo_guided_completed": "Cliente concluiu o guia da demo",
    }
    db.add(event)
    add_timeline(
        db,
        prospect,
        event_type=f"demo.{event_name}",
        event_label=event_labels.get(event_name, f"Evento de demo: {event_name}"),
        actor_type="demo_client",
        payload={"page_path": page_path, **payload_json},
    )
    db.add(prospect)
    db.commit()
    db.refresh(event)
    recalculate_score(db, prospect)
    return event


def get_insights(db: Session, prospect: ProspectAccount) -> dict:
    events = db.execute(select(DemoActivityEvent).where(DemoActivityEvent.prospect_account_id == prospect.id)).scalars().all()
    modules: dict[str, int] = {}
    for event in events:
        key = (event.page_path or event.event_name or "").strip("/") or "geral"
        module = key.split("/")[0]
        modules[module] = modules.get(module, 0) + 1
    sessions = len({event.session_id for event in events if event.session_id})
    return {
        "score": prospect.score,
        "temperature": prospect.temperature,
        "explanation": prospect.score_explanation or {},
        "sessions": sessions,
        "modules": modules,
        "last_activity_at": prospect.last_activity_at,
    }


def admin_login(db: Session, *, email: str, password: str) -> dict:
    ensure_admin_bootstrap(db)
    user = db.scalar(select(User).where(User.email == email.lower().strip()))
    if not user or not verify_password(password, user.hashed_password):
        raise ApiError(status_code=401, code="AUTH_INVALID_CREDENTIALS", message="Credenciais invalidas")
    if not user.is_active:
        raise ApiError(status_code=403, code="AUTH_USER_DISABLED", message="Usuario inativo")
    roles = [row[0] for row in db.execute(select(Role.name).join(UserRole, UserRole.role_id == Role.id).where(UserRole.user_id == user.id)).all()]
    if not {"admin_platform", "sales_admin", "sales_viewer"}.intersection(set(roles)):
        raise ApiError(status_code=403, code="ADM_FORBIDDEN", message="Usuario sem permissao para /adm")
    access_token = create_access_token(subject=str(user.id), tenant_id=user.tenant_id, roles=roles)
    refresh_token = create_refresh_token(subject=str(user.id), tenant_id=user.tenant_id, roles=roles)
    user.last_login_at = _now()
    db.add(user)
    db.commit()
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "expires_in": settings.api_access_token_expire_minutes * 60,
        "force_password_change": bool(user.page_permissions.get("adm_initial_password")),
        "roles": roles,
    }


def change_initial_admin_password(db: Session, *, user: User, current_password: str, new_password: str) -> None:
    if not verify_password(current_password, user.hashed_password):
        raise ApiError(status_code=401, code="AUTH_INVALID_CREDENTIALS", message="Senha atual invalida")
    validate_password_strength(new_password)
    permissions = dict(user.page_permissions or {})
    permissions.pop("adm_initial_password", None)
    user.page_permissions = permissions
    user.hashed_password = hash_password(new_password)
    db.add(user)
    db.commit()


def overview(db: Session) -> dict:
    total = db.scalar(select(func.count(ProspectAccount.id))) or 0
    demos_created = db.scalar(select(func.count(ProspectAccount.id)).where(ProspectAccount.demo_tenant_id.is_not(None))) or 0
    demos_accessed = db.scalar(select(func.count(ProspectAccount.id)).where(ProspectAccount.demo_first_login_at.is_not(None))) or 0
    hot_leads = db.scalar(select(func.count(ProspectAccount.id)).where(ProspectAccount.temperature.in_(["quente", "muito_quente"]))) or 0
    meetings = db.scalar(select(func.count(ProspectAccount.id)).where(ProspectAccount.status == "reuniao_marcada")) or 0
    won = db.scalar(select(func.count(ProspectAccount.id)).where(ProspectAccount.status == "fechado_ganho")) or 0
    recent = db.execute(select(ProspectTimelineEvent).order_by(ProspectTimelineEvent.created_at.desc()).limit(12)).scalars().all()
    return {
        "total_prospects": total,
        "demos_created": demos_created,
        "demos_accessed": demos_accessed,
        "hot_leads": hot_leads,
        "meetings_scheduled": meetings,
        "won": won,
        "recent_activity": [
            {
                "id": item.id,
                "event_type": item.event_type,
                "event_label": item.event_label,
                "actor_type": item.actor_type,
                "actor_id": item.actor_id,
                "payload": item.payload_json or {},
                "created_at": item.created_at,
            }
            for item in recent
        ],
    }

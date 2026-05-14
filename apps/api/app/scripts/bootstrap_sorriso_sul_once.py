from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models import AuditLog, Professional, Setting, WhatsAppAccount, WhatsAppTemplate
from app.scripts.seed import (
    create_sample_data_for_tenant,
    create_tenant_if_missing,
    create_unit_if_missing,
    create_user_if_missing,
    upsert_plans,
    upsert_roles,
)

TENANT_SLUG = "sorriso-sul"
OWNER_EMAIL = os.getenv("SORRISO_SUL_OWNER_EMAIL", "owner@sorrisosul.com")
OWNER_PASSWORD = os.getenv("SORRISO_SUL_OWNER_PASSWORD", "Odonto@123")
OVERWRITE_SETTINGS = os.getenv("SORRISO_SUL_OVERWRITE_SETTINGS", "true").lower() in {
    "1",
    "true",
    "yes",
    "sim",
}

SERVICE_CATALOG_ITEMS: list[dict[str, Any]] = [
    {
        "id": "sorriso-sul-avaliacao-detalhada",
        "name": "Avaliacao detalhada",
        "description": (
            "Consulta inicial para entender objetivo estetico e funcional, levantar historico "
            "e montar plano personalizado."
        ),
        "duration_minutes": 60,
        "price_note": "a partir de R$ 190",
        "is_active": True,
    },
    {
        "id": "sorriso-sul-lentes-contato-dental",
        "name": "Lentes de contato dental",
        "description": "Planejamento e instalacao de lentes para melhorar forma, cor e harmonia do sorriso.",
        "duration_minutes": 120,
        "price_note": "valor sob avaliacao",
        "is_active": True,
    },
    {
        "id": "sorriso-sul-clareamento-dental",
        "name": "Clareamento dental",
        "description": (
            "Protocolos de clareamento supervisionado para ganho estetico com orientacoes "
            "operacionais de acompanhamento."
        ),
        "duration_minutes": 60,
        "price_note": "a partir de R$ 650",
        "is_active": True,
    },
    {
        "id": "sorriso-sul-reabilitacao-estetica",
        "name": "Reabilitacao estetica",
        "description": "Combinacao de procedimentos para recuperar estetica e funcao, conforme plano individual.",
        "duration_minutes": 120,
        "price_note": "valor sob avaliacao",
        "is_active": True,
    },
]

SERVICE_NAMES = [str(item["name"]) for item in SERVICE_CATALOG_ITEMS]

AI_KNOWLEDGE_BASE: dict[str, Any] = {
    "clinic_profile": {
        "clinic_name": "Clinica Sorriso Sul",
        "about": (
            "A Clinica Sorriso Sul atua com atendimentos clinicos e esteticos, com abordagem "
            "consultiva, acolhimento premium e foco em previsibilidade de resultado."
        ),
        "differentials": [
            "avaliacao detalhada com planejamento digital",
            "atendimento acolhedor e linguagem simples",
            "parcelamento facilitado",
            "acompanhamento proximo no pos-procedimento",
            "instalacao de lentes em fluxo rapido quando indicado",
        ],
        "target_audience": (
            "adultos que buscam harmonizacao do sorriso, reabilitacao estetica e solucao "
            "funcional com orientacao clara"
        ),
        "tone_preferences": "profissional, cordial, objetivo, comercial consultivo e sem jargao tecnico",
        "welcome_greeting_example": (
            "Oi! Que bom te ver por aqui.\n"
            "Sou a assistente virtual da Clinica Sorriso Sul e posso te ajudar com servicos, "
            "valores e agendamentos.\n"
            "Para comecar, escolha uma opcao no menu abaixo:"
        ),
    },
    "services": [
        {
            "name": str(item["name"]),
            "description": str(item["description"]),
            "duration_note": f"{item['duration_minutes']} min",
            "price_note": str(item["price_note"]),
        }
        for item in SERVICE_CATALOG_ITEMS
    ],
    "insurance": {
        "accepted_plans": ["Particular", "Reembolso"],
        "notes": "Atendimento principal em regime particular. Emitimos recibo para reembolso quando aplicavel.",
    },
    "operational_policies": {
        "booking_rules": (
            "Agendamentos por WhatsApp com confirmacao de disponibilidade em agenda. "
            "Recomendado solicitar 24h de antecedencia."
        ),
        "cancellation_policy": (
            "Cancelamentos com menos de 4 horas podem gerar taxa operacional conforme tipo de agenda reservada."
        ),
        "reschedule_policy": (
            "Remarcacao sem custo quando solicitada com antecedencia minima de 4 horas e mediante disponibilidade."
        ),
        "payment_policy": "Aceitamos PIX, debito e cartao de credito. Parcelamento disponivel conforme procedimento.",
        "documents_required": "Documento com foto, contatos atualizados e exames recentes quando houver.",
    },
    "faq": [
        {
            "question": "Quais servicos voces oferecem?",
            "answer": (
                "Oferecemos avaliacao detalhada, lentes de contato dental, clareamento e "
                "reabilitacao estetica. Posso te orientar no melhor proximo passo para avaliacao."
            ),
        },
        {
            "question": "Quanto custa?",
            "answer": (
                "Os valores variam por caso. A avaliacao inicial parte de R$ 190 e nela definimos "
                "o plano e os custos com transparencia."
            ),
        },
        {
            "question": "Voces parcelam?",
            "answer": "Sim, trabalhamos com parcelamento no cartao conforme o procedimento e as condicoes vigentes.",
        },
        {
            "question": "Em quanto tempo fica pronto?",
            "answer": (
                "Depende do caso. Em fluxos elegiveis de lentes, a instalacao pode ocorrer em 1 dia, "
                "apos avaliacao e validacao do plano."
            ),
        },
        {
            "question": "Como agendar?",
            "answer": "Posso iniciar seu agendamento agora. Me informe seu nome completo e melhor periodo.",
        },
    ],
    "commercial_playbook": {
        "value_proposition": (
            "Sorriso bonito, natural e funcional com planejamento individual e acompanhamento de perto."
        ),
        "objection_handling": (
            "Quando houver duvida de valor, reforcar qualidade, previsibilidade, planejamento e "
            "possibilidades de pagamento. Conduzir para avaliacao."
        ),
        "default_cta": "Posso confirmar seu melhor horario para avaliacao ainda esta semana?",
    },
    "escalation": {
        "human_handoff_topics": [
            "negociacao de desconto fora da politica",
            "reclamacao formal",
            "casos sensiveis com historico de conflito",
            "duvida clinica especifica que exija avaliacao profissional",
        ],
        "restricted_topics": ["diagnostico", "prescricao", "laudo", "dose de medicamento", "conduta clinica"],
        "custom_urgent_keywords": ["dor forte", "sangramento", "trauma", "inchaco", "urgente"],
        "fallback_message": "Vou encaminhar agora para nossa equipe humana te atender com prioridade.",
    },
}

CLINIC_PROFILE: dict[str, Any] = {
    "clinic_name": "Clinica Sorriso Sul",
    "legal_name": "Sorriso Sul Clinica Odontologica LTDA",
    "cnpj": "",
    "main_phone": "+55 11 3333-0001",
    "whatsapp_phone": "+55 11 98888-7766",
    "email": "contato@sorrisosul.com",
    "website": "https://sorrisosul.com.br",
    "timezone": "America/Sao_Paulo",
    "address_line": "Av. Paulista, 1000",
    "neighborhood": "Bela Vista",
    "city": "Sao Paulo",
    "state": "SP",
    "zip_code": "01310-100",
    "technical_manager_name": "Dra. Juliana Ramos",
    "technical_manager_cro": "CRO-SP 123456",
    "payment_methods": "PIX, debito e cartao de credito com parcelamento conforme procedimento.",
    "accepted_insurance": "Particular e reembolso.",
    "cancellation_policy": AI_KNOWLEDGE_BASE["operational_policies"]["cancellation_policy"],
    "reschedule_policy": AI_KNOWLEDGE_BASE["operational_policies"]["reschedule_policy"],
    "about": AI_KNOWLEDGE_BASE["clinic_profile"]["about"],
}

AI_AUTORESPONDER_CONFIG: dict[str, Any] = {
    "enabled": True,
    "structured_flow_enabled": True,
    "channels": {"whatsapp": True},
    "interactive_booking_options_enabled": True,
    "business_hours": {
        "timezone": "America/Sao_Paulo",
        "weekdays": [0, 1, 2, 3, 4],
        "start": "08:00",
        "end": "18:00",
    },
    "outside_business_hours_mode": "allow",
    "max_consecutive_auto_replies": 3,
    "confidence_threshold": 0.65,
    "human_queue_tag": "fila_humana_ia",
    "tone": "profissional, cordial, objetivo, consultivo e acolhedor",
    "fallback_user_id": None,
}

BRANDING_THEME: dict[str, Any] = {
    "primary_color": "#0f766e",
    "secondary_color": "#0ea5a4",
    "accent_color": "#f59e0b",
    "background_color": "#f2f4f7",
    "surface_color": "#eef2f6",
    "card_color": "#ffffff",
    "text_color": "#1c1917",
    "muted_text_color": "#475569",
    "border_color": "#d6d3d1",
    "fullscreen_background_color": "#0c0a09",
    "fullscreen_header_color": "#111111",
    "fullscreen_accent_color": "#10b981",
    "fullscreen_foreground_color": "#ffffff",
    "surface_style": "soft",
    "logo_data_url": None,
}


def _upsert_setting(
    db: Session,
    *,
    tenant_id: UUID,
    key: str,
    value: Any,
    is_secret: bool = False,
    overwrite: bool = True,
) -> Setting:
    item = db.scalar(select(Setting).where(Setting.tenant_id == tenant_id, Setting.key == key))
    if not item:
        item = Setting(tenant_id=tenant_id, key=key, value=value, is_secret=is_secret)
    elif overwrite:
        item.value = value
        item.is_secret = is_secret
    db.add(item)
    db.flush()
    return item


def _prepare_core_data(db: Session) -> dict[str, Any]:
    role_map = upsert_roles(db)
    plan_map = upsert_plans(db)

    tenant = create_tenant_if_missing(
        db,
        slug=TENANT_SLUG,
        legal_name="Sorriso Sul Clinica Odontologica LTDA",
        trade_name="Clinica Sorriso Sul",
        plan_id=plan_map["growth"].id,
    )
    tenant.legal_name = "Sorriso Sul Clinica Odontologica LTDA"
    tenant.trade_name = "Clinica Sorriso Sul"
    tenant.plan_id = plan_map["growth"].id
    tenant.subscription_status = "active"
    tenant.trial_ends_at = datetime.now(UTC) + timedelta(days=14)
    tenant.is_active = True
    db.add(tenant)
    db.flush()

    unit_centro = create_unit_if_missing(db, tenant.id, "SP-CENTRO", "Unidade Centro", "+55 11 3333-0001")
    unit_centro.email = "centro@sorrisosul.com"
    unit_centro.address = {
        "address_line": "Av. Paulista",
        "number": "1000",
        "neighborhood": "Bela Vista",
        "city": "Sao Paulo",
        "state": "SP",
        "zip_code": "01310-100",
        "reference_point": "Proximo ao metro Trianon-Masp",
        "parking_info": "Estacionamento conveniado no predio ao lado",
    }
    unit_centro.working_hours = {"weekdays": [0, 1, 2, 3, 4], "start": "08:00", "end": "18:00"}
    unit_centro.is_active = True
    db.add(unit_centro)

    unit_paulista = create_unit_if_missing(db, tenant.id, "SP-PAULISTA", "Unidade Paulista", "+55 11 3333-0002")
    unit_paulista.email = "paulista@sorrisosul.com"
    unit_paulista.address = {
        "address_line": "Rua Pamplona",
        "number": "450",
        "neighborhood": "Jardim Paulista",
        "city": "Sao Paulo",
        "state": "SP",
        "zip_code": "01405-000",
        "reference_point": "A duas quadras da Av. Paulista",
        "parking_info": "Valet sob consulta",
    }
    unit_paulista.working_hours = {"weekdays": [0, 1, 2, 3, 4], "start": "09:00", "end": "19:00"}
    unit_paulista.is_active = True
    db.add(unit_paulista)
    db.flush()

    owner = create_user_if_missing(
        db,
        tenant_id=tenant.id,
        email=OWNER_EMAIL,
        full_name="Juliana Ramos",
        role_names=["owner"],
        role_map=role_map,
        password=OWNER_PASSWORD,
    )
    owner.unit_id = unit_centro.id
    db.add(owner)

    reception = create_user_if_missing(
        db,
        tenant_id=tenant.id,
        email="reception@sorrisosul.com",
        full_name="Mariana Costa",
        role_names=["receptionist"],
        role_map=role_map,
        password=OWNER_PASSWORD,
    )
    reception.unit_id = unit_centro.id
    db.add(reception)

    analyst = create_user_if_missing(
        db,
        tenant_id=tenant.id,
        email="analyst@sorrisosul.com",
        full_name="Bruno Martins",
        role_names=["analyst"],
        role_map=role_map,
        password=OWNER_PASSWORD,
    )
    analyst.unit_id = unit_paulista.id
    db.add(analyst)
    db.flush()

    create_sample_data_for_tenant(db, tenant, unit_centro, unit_paulista, owner)
    return {
        "tenant": tenant,
        "unit_centro": unit_centro,
        "unit_paulista": unit_paulista,
        "owner": owner,
    }


def _upsert_professional(
    db: Session,
    *,
    tenant_id: UUID,
    unit_id: UUID,
    full_name: str,
    cro_number: str,
    specialty: str,
    procedures: list[str],
    shift_start: str,
    shift_end: str,
) -> Professional:
    professional = db.scalar(
        select(Professional).where(
            Professional.tenant_id == tenant_id,
            Professional.full_name == full_name,
        )
    )
    if not professional:
        professional = Professional(tenant_id=tenant_id, full_name=full_name)
    professional.unit_id = unit_id
    professional.cro_number = cro_number
    professional.specialty = specialty
    professional.procedures = procedures
    professional.working_days = [0, 1, 2, 3, 4]
    professional.shift_start = shift_start
    professional.shift_end = shift_end
    professional.is_active = True
    db.add(professional)
    db.flush()
    return professional


def _configure_professionals(db: Session, *, tenant_id: UUID, unit_centro_id: UUID, unit_paulista_id: UUID) -> None:
    _upsert_professional(
        db,
        tenant_id=tenant_id,
        unit_id=unit_centro_id,
        full_name="Dra. Juliana Ramos",
        cro_number="CRO-SP 123456",
        specialty="Dentistica estetica",
        procedures=["Avaliacao detalhada", "Lentes de contato dental", "Reabilitacao estetica"],
        shift_start="08:00",
        shift_end="17:00",
    )
    _upsert_professional(
        db,
        tenant_id=tenant_id,
        unit_id=unit_paulista_id,
        full_name="Dr. Rafael Teixeira",
        cro_number="CRO-SP 654321",
        specialty="Clareamento dental",
        procedures=["Avaliacao detalhada", "Clareamento dental"],
        shift_start="09:00",
        shift_end="18:00",
    )


def _configure_settings(db: Session, *, tenant_id: UUID, unit_centro_id: UUID, unit_paulista_id: UUID) -> None:
    setting_payloads: dict[str, Any] = {
        "clinic.profile": CLINIC_PROFILE,
        "clinic.timezone": {"value": "America/Sao_Paulo"},
        "service_catalog.global": {"items": SERVICE_CATALOG_ITEMS},
        "services.catalog": {"services": SERVICE_CATALOG_ITEMS},
        "ai_autoresponder.global": AI_AUTORESPONDER_CONFIG,
        "ai_knowledge_base.global": AI_KNOWLEDGE_BASE,
        "ai.knowledge": {
            "voice_tone": AI_AUTORESPONDER_CONFIG["tone"],
            "greeting": AI_KNOWLEDGE_BASE["clinic_profile"]["welcome_greeting_example"],
            "faq": AI_KNOWLEDGE_BASE["faq"],
            "knowledge": AI_KNOWLEDGE_BASE,
            "scheduling_policy": AI_KNOWLEDGE_BASE["operational_policies"]["booking_rules"],
        },
        "branding.theme": BRANDING_THEME,
        "branding.logo_data_url": None,
        "security.session_timeout": 30,
        "security.idle_lock_minutes": 10,
        "security.require_mfa": False,
        "security.enforce_single_session": False,
        "security.password_rotation_days": 90,
        "security.audit_log_retention_days": 365,
        "security.allowed_ip_ranges": "",
        "security.restrict_sensitive_exports": True,
        "security.notify_new_device_login": True,
        "privacy.retention_days": 365,
        "privacy.communication_allowed": {"marketing": True, "operacional": True},
        "privacy.terms_version": "v1.0",
        "privacy.policy_version": "v1.0",
        "privacy.contact": {
            "name": "Equipe Sorriso Sul",
            "email": "privacidade@sorrisosul.com",
            "phone": "+55 11 3333-0001",
        },
        "privacy.export_defaults": {"scope": "tenant", "requested_by_email": OWNER_EMAIL},
        "privacy.governance": {
            "anonymize_leads_after_days": 365,
            "consent_text": "Autorizo comunicacoes operacionais e lembretes de atendimento.",
            "data_sharing_notes": "Dados usados apenas para atendimento, operacao e melhoria da experiencia.",
        },
    }

    for key, value in setting_payloads.items():
        _upsert_setting(db, tenant_id=tenant_id, key=key, value=value, overwrite=OVERWRITE_SETTINGS)

    for unit_id in (unit_centro_id, unit_paulista_id):
        _upsert_setting(
            db,
            tenant_id=tenant_id,
            key=f"unit.services.{unit_id}",
            value={"services": SERVICE_NAMES},
            overwrite=OVERWRITE_SETTINGS,
        )


def _configure_whatsapp(db: Session, *, tenant_id: UUID, unit_id: UUID) -> None:
    account = db.scalar(
        select(WhatsAppAccount)
        .where(
            WhatsAppAccount.tenant_id == tenant_id,
            WhatsAppAccount.phone_number_id == f"phone_{TENANT_SLUG}",
        )
        .order_by(WhatsAppAccount.created_at.desc())
        .limit(1)
    )
    active_account = db.scalar(
        select(WhatsAppAccount)
        .where(
            WhatsAppAccount.tenant_id == tenant_id,
            WhatsAppAccount.is_active.is_(True),
        )
        .order_by(WhatsAppAccount.created_at.desc())
        .limit(1)
    )
    account = active_account or account
    if not account:
        account = WhatsAppAccount(
            tenant_id=tenant_id,
            unit_id=unit_id,
            provider_name="meta_cloud",
            phone_number_id=f"phone_{TENANT_SLUG}",
            business_account_id=f"biz_{TENANT_SLUG}",
            display_phone="+55 11 98888-7766",
            access_token_encrypted="mock_access_token",
            verify_token="verify-token-dev",
            webhook_secret="mock_secret",
            is_active=True,
        )
    elif account.phone_number_id == f"phone_{TENANT_SLUG}":
        account.unit_id = unit_id
        account.provider_name = "meta_cloud"
        account.business_account_id = f"biz_{TENANT_SLUG}"
        account.display_phone = "+55 11 98888-7766"
        account.access_token_encrypted = account.access_token_encrypted or "mock_access_token"
        account.verify_token = account.verify_token or "verify-token-dev"
        account.webhook_secret = account.webhook_secret or "mock_secret"
        account.is_active = True
    db.add(account)
    db.flush()

    template = db.scalar(
        select(WhatsAppTemplate).where(
            WhatsAppTemplate.tenant_id == tenant_id,
            WhatsAppTemplate.name == "lembrete_consulta_24h",
            WhatsAppTemplate.language == "pt_BR",
        )
    )
    if not template:
        template = WhatsAppTemplate(
            tenant_id=tenant_id,
            whatsapp_account_id=account.id,
            name="lembrete_consulta_24h",
            language="pt_BR",
        )
    template.whatsapp_account_id = account.id
    template.category = "UTILITY"
    template.content = {"body": "Lembrete de consulta para {{1}} em {{2}}."}
    template.status = "APPROVED"
    db.add(template)
    db.flush()


def _record_bootstrap_audit(db: Session, *, tenant_id: UUID, user_id: UUID) -> None:
    existing = db.scalar(
        select(AuditLog).where(
            AuditLog.tenant_id == tenant_id,
            AuditLog.action == "bootstrap.sorriso_sul",
        )
    )
    if existing:
        return
    db.add(
        AuditLog(
            tenant_id=tenant_id,
            user_id=user_id,
            action="bootstrap.sorriso_sul",
            entity_type="tenant",
            entity_id=str(tenant_id),
            metadata_json={
                "tenant_slug": TENANT_SLUG,
                "owner_email": OWNER_EMAIL,
                "settings_overwritten": OVERWRITE_SETTINGS,
            },
            ip_address="127.0.0.1",
            user_agent="bootstrap_sorriso_sul_once",
        )
    )
    db.flush()


def bootstrap_sorriso_sul(db: Session) -> dict[str, str]:
    data = _prepare_core_data(db)
    tenant = data["tenant"]
    unit_centro = data["unit_centro"]
    unit_paulista = data["unit_paulista"]
    owner = data["owner"]

    _configure_professionals(
        db,
        tenant_id=tenant.id,
        unit_centro_id=unit_centro.id,
        unit_paulista_id=unit_paulista.id,
    )
    _configure_settings(
        db,
        tenant_id=tenant.id,
        unit_centro_id=unit_centro.id,
        unit_paulista_id=unit_paulista.id,
    )
    _configure_whatsapp(db, tenant_id=tenant.id, unit_id=unit_centro.id)
    _record_bootstrap_audit(db, tenant_id=tenant.id, user_id=owner.id)

    return {
        "tenant_slug": tenant.slug,
        "owner_email": OWNER_EMAIL,
        "tenant_id": str(tenant.id),
    }


def run() -> None:
    db = SessionLocal()
    try:
        result = bootstrap_sorriso_sul(db)
        db.commit()
        print("Clinica Sorriso Sul preparada com sucesso.")
        print(f"Tenant: {result['tenant_slug']} ({result['tenant_id']})")
        print(f"Login owner: {result['owner_email']}")
        print("Senha owner configurada.")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    run()

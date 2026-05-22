from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import ApiError
from app.models import FeatureFlag

IMPLEMENTATION_CATALOG: list[dict[str, Any]] = [
    {
        "key": "implementation.public_booking_webchat",
        "label": "Agendamento publico via webchat",
        "category": "Agendamento",
        "description": "Fluxo do link oficial com servico, unidade, dia, horario e confirmacao pelo chat.",
        "delivery_status": "implemented",
        "default_enabled": True,
        "can_toggle": True,
        "notes": "Controla a disponibilidade do fluxo conversacional publico para testes e rollout.",
    },
    {
        "key": "implementation.public_booking_summary_sync",
        "label": "Resumo lateral sincronizado",
        "category": "Agendamento",
        "description": "Mantem o painel lateral alinhado com a etapa real da conversa e com o agendamento criado.",
        "delivery_status": "implemented",
        "default_enabled": True,
        "can_toggle": True,
        "notes": "Evita falso confirmado e reflete servico, unidade, data e horario ainda durante o wizard.",
    },
    {
        "key": "implementation.public_booking_natural_language_guardrails",
        "label": "Guardrails de linguagem natural",
        "category": "Agendamento",
        "description": "Segura o contexto do wizard quando o paciente responde fora da ordem ideal ou em texto livre.",
        "delivery_status": "implemented",
        "default_enabled": True,
        "can_toggle": True,
        "notes": "Protege respostas como amanha, sexta-feira e 0930 sem derrubar para um fluxo generico.",
    },
    {
        "key": "implementation.demo_intake_link_flow",
        "label": "Intake demo em link_flow",
        "category": "Demonstracao",
        "description": "Permite demos comerciais com configuracao de intake ligada ao fluxo publico.",
        "delivery_status": "implemented",
        "default_enabled": True,
        "can_toggle": True,
        "notes": "Base atual usada no /adm para demos e links de teste.",
    },
    {
        "key": "implementation.demo_intake_hybrid_mode",
        "label": "Intake demo hibrido",
        "category": "Demonstracao",
        "description": "Mistura captacao por API oficial e link_flow em demos que precisam cobrir ambos os caminhos.",
        "delivery_status": "partial",
        "default_enabled": False,
        "can_toggle": True,
        "notes": "Estrutura pronta para expansao, mas deve ser ativada com cuidado por tenant e cenario.",
    },
    {
        "key": "implementation.platform_whatsapp_sender",
        "label": "WhatsApp oficial da plataforma",
        "category": "Operacao",
        "description": "Centraliza o sender oficial usado por outreach, demos e operacao da plataforma.",
        "delivery_status": "implemented",
        "default_enabled": True,
        "can_toggle": True,
        "notes": "Depende de credenciais validas no Admin Plataforma.",
    },
    {
        "key": "implementation.sales_outreach_automation",
        "label": "Automacao comercial do /adm",
        "category": "Comercial",
        "description": "Fluxos de outreach, laboratorio de abordagem e automacoes para prospeccao comercial.",
        "delivery_status": "partial",
        "default_enabled": False,
        "can_toggle": True,
        "notes": "Mantido desligado por padrao para liberar ativacao controlada.",
    },
    {
        "key": "implementation.ai_lab_regression_suite",
        "label": "Suite de regressao da IA",
        "category": "Qualidade",
        "description": "Bateria automatizada para validar contexto, naturalidade e seguranca dos fluxos de IA.",
        "delivery_status": "implemented",
        "default_enabled": True,
        "can_toggle": True,
        "notes": "Serve como base operacional para ciclos longos de teste conversacional.",
    },
    {
        "key": "implementation.guided_demo_experience",
        "label": "Experiencia guiada da demo",
        "category": "Demonstracao",
        "description": "Tutoriais, spotlight e atalhos guiados para demos de venda e onboarding.",
        "delivery_status": "implemented",
        "default_enabled": True,
        "can_toggle": True,
        "notes": "Pode ser desativada quando a clinica quiser uma demo mais limpa.",
    },
    {
        "key": "implementation.adm_implementation_control_center",
        "label": "Central de implementacoes do /adm",
        "category": "Admin",
        "description": "Painel operacional para listar, acompanhar e ativar implementacoes da plataforma.",
        "delivery_status": "implemented",
        "default_enabled": True,
        "can_toggle": True,
        "notes": "Este proprio painel.",
    },
]


def _catalog_by_key() -> dict[str, dict[str, Any]]:
    return {str(item["key"]): item for item in IMPLEMENTATION_CATALOG}


def _platform_flag_rows(db: Session) -> list[FeatureFlag]:
    return (
        db.execute(
            select(FeatureFlag)
            .where(
                FeatureFlag.tenant_id.is_(None),
                FeatureFlag.key.in_([item["key"] for item in IMPLEMENTATION_CATALOG]),
            )
            .order_by(FeatureFlag.updated_at.desc(), FeatureFlag.created_at.desc())
        )
        .scalars()
        .all()
    )


def _serialize_definition(definition: dict[str, Any], row: FeatureFlag | None) -> dict[str, Any]:
    enabled = bool(row.enabled) if row else bool(definition.get("default_enabled"))
    return {
        "key": definition["key"],
        "label": definition["label"],
        "category": definition["category"],
        "description": definition["description"],
        "delivery_status": definition["delivery_status"],
        "enabled": enabled,
        "default_enabled": bool(definition.get("default_enabled")),
        "can_toggle": bool(definition.get("can_toggle", True)),
        "notes": definition.get("notes"),
        "updated_at": row.updated_at.isoformat() if row else None,
        "config": row.config if row else {},
    }


def list_platform_implementations(db: Session) -> dict[str, Any]:
    rows_by_key: dict[str, FeatureFlag] = {}
    for row in _platform_flag_rows(db):
        rows_by_key.setdefault(str(row.key), row)

    items = [_serialize_definition(item, rows_by_key.get(str(item["key"]))) for item in IMPLEMENTATION_CATALOG]

    implemented_count = sum(1 for item in items if item["delivery_status"] == "implemented")
    partial_count = sum(1 for item in items if item["delivery_status"] == "partial")
    planned_count = sum(1 for item in items if item["delivery_status"] == "planned")
    enabled_count = sum(1 for item in items if item["enabled"])

    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "summary": {
            "total": len(items),
            "enabled": enabled_count,
            "implemented": implemented_count,
            "partial": partial_count,
            "planned": planned_count,
        },
        "items": items,
    }


def set_platform_implementation_enabled(db: Session, *, key: str, enabled: bool) -> dict[str, Any]:
    catalog = _catalog_by_key()
    definition = catalog.get(str(key))
    if not definition:
        raise ApiError(
            status_code=404,
            code="ADMIN_IMPLEMENTATION_NOT_FOUND",
            message="Implementacao nao encontrada no catalogo do /adm.",
        )
    if not bool(definition.get("can_toggle", True)):
        raise ApiError(
            status_code=409,
            code="ADMIN_IMPLEMENTATION_TOGGLE_BLOCKED",
            message="Essa implementacao ainda nao pode ser ativada por este painel.",
        )

    rows = (
        db.execute(
            select(FeatureFlag)
            .where(
                FeatureFlag.tenant_id.is_(None),
                FeatureFlag.key == definition["key"],
            )
            .order_by(FeatureFlag.updated_at.desc(), FeatureFlag.created_at.desc())
        )
        .scalars()
        .all()
    )
    row = rows[0] if rows else None

    if row is None:
        row = FeatureFlag(
            tenant_id=None,
            key=definition["key"],
            description=str(definition.get("description") or "")[:255] or None,
            enabled=enabled,
            config={"scope": "platform_admin", "source": "adm_implementations"},
        )
        db.add(row)
    else:
        row.enabled = enabled
        row.description = str(definition.get("description") or "")[:255] or row.description
        row.config = {
            **(row.config or {}),
            "scope": "platform_admin",
            "source": "adm_implementations",
        }
        db.add(row)

    for duplicate in rows[1:]:
        duplicate.enabled = row.enabled
        duplicate.description = row.description
        duplicate.config = row.config
        db.add(duplicate)

    db.flush()
    return _serialize_definition(definition, row)

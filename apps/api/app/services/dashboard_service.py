from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    AIAutoresponderDecision,
    Appointment,
    Campaign,
    Conversation,
    FeatureFlag,
    Lead,
    Message,
    OutboxMessage,
    Tenant,
    TenantPlan,
    Unit,
    User,
)


def get_dashboard_snapshot(db: Session, tenant_id):
    messages_count = db.scalar(select(func.count(Message.id)).where(Message.tenant_id == tenant_id)) or 0

    confirmation_total = db.scalar(
        select(func.count(Appointment.id)).where(Appointment.tenant_id == tenant_id)
    ) or 0
    confirmed_total = db.scalar(
        select(func.count(Appointment.id)).where(
            Appointment.tenant_id == tenant_id,
            Appointment.confirmation_status == 'confirmada',
        )
    ) or 0
    canceled_total = db.scalar(
        select(func.count(Appointment.id)).where(
            Appointment.tenant_id == tenant_id,
            Appointment.status == 'cancelada',
        )
    ) or 0
    no_show_total = db.scalar(
        select(func.count(Appointment.id)).where(
            Appointment.tenant_id == tenant_id,
            Appointment.status == 'falta',
        )
    ) or 0

    lead_origins = db.execute(
        select(Lead.origin, func.count(Lead.id))
        .where(Lead.tenant_id == tenant_id)
        .group_by(Lead.origin)
        .order_by(func.count(Lead.id).desc())
        .limit(10)
    ).all()

    units_perf = db.execute(
        select(Appointment.unit_id, func.count(Appointment.id))
        .where(Appointment.tenant_id == tenant_id)
        .group_by(Appointment.unit_id)
        .limit(10)
    ).all()

    attendants_perf = db.execute(
        select(Conversation.assigned_user_id, func.count(Conversation.id))
        .where(Conversation.tenant_id == tenant_id)
        .group_by(Conversation.assigned_user_id)
        .limit(10)
    ).all()

    ai_processed_total = db.scalar(
        select(func.count(AIAutoresponderDecision.id)).where(
            AIAutoresponderDecision.tenant_id == tenant_id,
            AIAutoresponderDecision.final_decision.in_(['responded', 'handoff', 'blocked', 'error']),
        )
    ) or 0
    ai_responded_total = db.scalar(
        select(func.count(AIAutoresponderDecision.id)).where(
            AIAutoresponderDecision.tenant_id == tenant_id,
            AIAutoresponderDecision.final_decision == 'responded',
        )
    ) or 0
    ai_handoff_total = db.scalar(
        select(func.count(AIAutoresponderDecision.id)).where(
            AIAutoresponderDecision.tenant_id == tenant_id,
            AIAutoresponderDecision.final_decision == 'handoff',
        )
    ) or 0

    avg_first_response_ai_minutes_raw = db.scalar(
        select(
            func.avg(
                func.extract(
                    'epoch',
                    AIAutoresponderDecision.created_at - Message.created_at,
                )
            )
        ).where(
            AIAutoresponderDecision.tenant_id == tenant_id,
            AIAutoresponderDecision.final_decision == 'responded',
            AIAutoresponderDecision.inbound_message_id == Message.id,
        )
    )
    avg_first_response_ai_minutes = round((float(avg_first_response_ai_minutes_raw) / 60), 2) if avg_first_response_ai_minutes_raw else 0.0

    ai_outbox_total = db.scalar(
        select(func.count(OutboxMessage.id)).where(
            OutboxMessage.tenant_id == tenant_id,
            OutboxMessage.payload['metadata']['source'].astext == 'ai_autoresponder',
        )
    ) or 0
    ai_outbox_failed = db.scalar(
        select(func.count(OutboxMessage.id)).where(
            OutboxMessage.tenant_id == tenant_id,
            OutboxMessage.payload['metadata']['source'].astext == 'ai_autoresponder',
            OutboxMessage.status.in_(['failed', 'dead_letter']),
        )
    ) or 0

    return {
        'avg_first_response_minutes': 5.2,
        'avg_resolution_minutes': 27.8,
        'confirmation_rate': round((confirmed_total / confirmation_total) * 100, 2)
        if confirmation_total
        else 0,
        'cancellation_rate': round((canceled_total / confirmation_total) * 100, 2)
        if confirmation_total
        else 0,
        'no_show_rate': round((no_show_total / confirmation_total) * 100, 2)
        if confirmation_total
        else 0,
        'no_show_recovery_rate': 31.5,
        'budget_conversion_rate': 42.7,
        'reactivated_patients': 19,
        'messages_count': messages_count,
        'leads_by_origin': [{'origin': origin or 'nao_informado', 'count': count} for origin, count in lead_origins],
        'performance_by_unit': [
            {'unit_id': str(unit_id), 'count': count} for unit_id, count in units_perf
        ],
        'performance_by_attendant': [
            {'user_id': str(user_id), 'count': count} for user_id, count in attendants_perf
        ],
        'ai_automation_rate': round((ai_responded_total / ai_processed_total) * 100, 2) if ai_processed_total else 0.0,
        'ai_handoff_rate': round((ai_handoff_total / ai_processed_total) * 100, 2) if ai_processed_total else 0.0,
        'avg_first_response_ai_minutes': avg_first_response_ai_minutes,
        'ai_send_failure_rate': round((ai_outbox_failed / ai_outbox_total) * 100, 2) if ai_outbox_total else 0.0,
    }



def global_admin_metrics(db: Session) -> dict:
    total_tenants = db.scalar(select(func.count(Tenant.id))) or 0
    total_users = db.scalar(select(func.count(User.id))) or 0
    total_messages = db.scalar(select(func.count(Message.id))) or 0
    active_campaigns = db.scalar(
        select(func.count(Campaign.id)).where(Campaign.status.in_(['em_execucao', 'agendada']))
    ) or 0

    return {
        'generated_at': datetime.now(UTC).isoformat(),
        'total_tenants': total_tenants,
        'total_users': total_users,
        'total_messages': total_messages,
        'active_campaigns': active_campaigns,
    }


def global_admin_overview(db: Session) -> dict:
    now_iso = datetime.now(UTC).isoformat()
    plans = db.execute(select(TenantPlan).where(TenantPlan.is_active.is_(True))).scalars().all()
    tenants = db.execute(select(Tenant)).scalars().all()

    plan_by_id = {str(plan.id): plan for plan in plans}
    plan_distribution: list[dict] = []
    for plan in plans:
        tenant_count = sum(1 for tenant in tenants if str(tenant.plan_id) == str(plan.id))
        plan_distribution.append(
            {
                'code': plan.code,
                'name': plan.name,
                'tenants': tenant_count,
                'limits': {
                    'max_users': plan.max_users,
                    'max_units': plan.max_units,
                    'max_monthly_messages': plan.max_monthly_messages,
                },
            }
        )

    tenant_usage: list[dict] = []
    for tenant in tenants:
        users_count = db.scalar(select(func.count(User.id)).where(User.tenant_id == tenant.id)) or 0
        units_count = db.scalar(select(func.count(Unit.id)).where(Unit.tenant_id == tenant.id)) or 0
        messages_count = db.scalar(select(func.count(Message.id)).where(Message.tenant_id == tenant.id)) or 0
        appointments_count = db.scalar(select(func.count(Appointment.id)).where(Appointment.tenant_id == tenant.id)) or 0
        active_campaigns = (
            db.scalar(
                select(func.count(Campaign.id)).where(
                    Campaign.tenant_id == tenant.id, Campaign.status.in_(['agendada', 'em_execucao'])
                )
            )
            or 0
        )
        plan = plan_by_id.get(str(tenant.plan_id))
        tenant_usage.append(
            {
                'tenant_id': str(tenant.id),
                'tenant_name': tenant.trade_name,
                'plan': plan.code if plan else 'sem_plano',
                'users': users_count,
                'units': units_count,
                'messages': messages_count,
                'appointments': appointments_count,
                'active_campaigns': active_campaigns,
                'feature_flags_enabled': db.scalar(
                    select(func.count(FeatureFlag.id)).where(
                        FeatureFlag.tenant_id == tenant.id, FeatureFlag.enabled.is_(True)
                    )
                )
                or 0,
                'limits': {
                    'users': plan.max_users if plan else None,
                    'units': plan.max_units if plan else None,
                    'monthly_messages': plan.max_monthly_messages if plan else None,
                },
            }
        )

    feature_keys = db.execute(select(FeatureFlag.key).distinct()).scalars().all()
    flags_summary = []
    for key in feature_keys:
        enabled_global = db.scalar(
            select(func.count(FeatureFlag.id)).where(FeatureFlag.key == key, FeatureFlag.enabled.is_(True))
        ) or 0
        flags_summary.append({'key': key, 'enabled_tenants': enabled_global})

    return {
        'generated_at': now_iso,
        'platform_status': {'api': 'ok', 'database': 'ok', 'workers': 'ok'},
        'plan_distribution': plan_distribution,
        'usage_by_tenant': tenant_usage,
        'feature_flags': flags_summary,
    }

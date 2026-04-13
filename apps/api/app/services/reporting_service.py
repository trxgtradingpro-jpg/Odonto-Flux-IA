from calendar import monthrange
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Appointment, Lead, Message, Patient


def month_bounds(reference: datetime) -> tuple[datetime, datetime]:
    year = reference.year
    month = reference.month
    start = datetime(year, month, 1, tzinfo=UTC)
    last_day = monthrange(year, month)[1]
    end = datetime(year, month, last_day, 23, 59, 59, tzinfo=UTC)
    return start, end


def monthly_report(db: Session, tenant_id, reference: datetime) -> dict:
    start_at, end_at = month_bounds(reference)

    messages_total = db.scalar(
        select(func.count(Message.id)).where(
            Message.tenant_id == tenant_id,
            Message.created_at >= start_at,
            Message.created_at <= end_at,
        )
    ) or 0

    appointments_total = db.scalar(
        select(func.count(Appointment.id)).where(
            Appointment.tenant_id == tenant_id,
            Appointment.starts_at >= start_at,
            Appointment.starts_at <= end_at,
        )
    ) or 0
    confirmed_appointments = db.scalar(
        select(func.count(Appointment.id)).where(
            Appointment.tenant_id == tenant_id,
            Appointment.starts_at >= start_at,
            Appointment.starts_at <= end_at,
            Appointment.confirmation_status == 'confirmada',
        )
    ) or 0
    canceled_appointments = db.scalar(
        select(func.count(Appointment.id)).where(
            Appointment.tenant_id == tenant_id,
            Appointment.starts_at >= start_at,
            Appointment.starts_at <= end_at,
            Appointment.status == 'cancelada',
        )
    ) or 0
    no_show_appointments = db.scalar(
        select(func.count(Appointment.id)).where(
            Appointment.tenant_id == tenant_id,
            Appointment.starts_at >= start_at,
            Appointment.starts_at <= end_at,
            Appointment.status == 'falta',
        )
    ) or 0

    leads_created = db.scalar(
        select(func.count(Lead.id)).where(
            Lead.tenant_id == tenant_id,
            Lead.created_at >= start_at,
            Lead.created_at <= end_at,
        )
    ) or 0
    leads_converted = db.scalar(
        select(func.count(Lead.id)).where(
            Lead.tenant_id == tenant_id,
            Lead.converted_at.is_not(None),
            Lead.converted_at >= start_at,
            Lead.converted_at <= end_at,
        )
    ) or 0

    reactivated_patients = db.scalar(
        select(func.count(Patient.id)).where(
            Patient.tenant_id == tenant_id,
            Patient.status == 'ativo',
            Patient.inactive_since.is_not(None),
            Patient.updated_at >= start_at,
            Patient.updated_at <= end_at,
        )
    ) or 0

    confirmation_rate = round((confirmed_appointments / appointments_total) * 100, 2) if appointments_total else 0
    no_show_rate = round((no_show_appointments / appointments_total) * 100, 2) if appointments_total else 0
    cancellation_rate = round((canceled_appointments / appointments_total) * 100, 2) if appointments_total else 0
    budget_conversion_rate = round((leads_converted / leads_created) * 100, 2) if leads_created else 0

    highlights = []
    if confirmation_rate >= 70:
        highlights.append('Taxa de confirmacao acima de 70%.')
    if no_show_rate <= 12:
        highlights.append('No-show sob controle no periodo.')
    if budget_conversion_rate >= 35:
        highlights.append('Conversao comercial saudavel para leads do mes.')
    if not highlights:
        highlights.append('Periodo com oportunidades de melhoria em confirmacao e follow-up.')

    recommendations = [
        'Priorizar contato para consultas pendentes a menos de 24h.',
        'Executar cadencia de follow-up em 2 e 7 dias para orcamentos.',
        'Reforcar campanha de reativacao para pacientes inativos.',
    ]

    return {
        'period': {
            'year': reference.year,
            'month': reference.month,
            'start_at': start_at.isoformat(),
            'end_at': end_at.isoformat(),
            'label': reference.strftime('%m/%Y'),
        },
        'kpis': {
            'messages_total': messages_total,
            'appointments_total': appointments_total,
            'confirmed_appointments': confirmed_appointments,
            'canceled_appointments': canceled_appointments,
            'no_show_appointments': no_show_appointments,
            'leads_created': leads_created,
            'leads_converted': leads_converted,
            'reactivated_patients': reactivated_patients,
            'confirmation_rate': confirmation_rate,
            'no_show_rate': no_show_rate,
            'cancellation_rate': cancellation_rate,
            'budget_conversion_rate': budget_conversion_rate,
        },
        'highlights': highlights,
        'recommendations': recommendations,
        'generated_at': datetime.now(UTC).isoformat(),
    }


def monthly_report_csv_payload(report: dict) -> str:
    kpis = report['kpis']
    rows = [
        'indicador,valor',
        f"periodo,{report['period']['label']}",
        f"mensagens_total,{kpis['messages_total']}",
        f"consultas_total,{kpis['appointments_total']}",
        f"consultas_confirmadas,{kpis['confirmed_appointments']}",
        f"consultas_canceladas,{kpis['canceled_appointments']}",
        f"consultas_no_show,{kpis['no_show_appointments']}",
        f"leads_criados,{kpis['leads_created']}",
        f"leads_convertidos,{kpis['leads_converted']}",
        f"pacientes_reativados,{kpis['reactivated_patients']}",
        f"taxa_confirmacao,{kpis['confirmation_rate']}",
        f"taxa_cancelamento,{kpis['cancellation_rate']}",
        f"taxa_no_show,{kpis['no_show_rate']}",
        f"taxa_conversao_orcamento,{kpis['budget_conversion_rate']}",
    ]
    return '\n'.join(rows)

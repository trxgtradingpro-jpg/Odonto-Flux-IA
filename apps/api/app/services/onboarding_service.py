from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Automation, Campaign, Setting, Unit, User, WhatsAppAccount


def _has_clinic_profile(settings_by_key: dict[str, Setting]) -> bool:
    display = settings_by_key.get('clinic.display_name') or settings_by_key.get('clinic.name')
    timezone = settings_by_key.get('clinic.timezone')
    return bool(display and timezone)


def onboarding_status(db: Session, tenant_id) -> dict:
    settings = db.execute(select(Setting).where(Setting.tenant_id == tenant_id)).scalars().all()
    settings_by_key = {item.key: item for item in settings}
    manually_completed = set()
    manual_setting = settings_by_key.get('onboarding.completed_steps')
    if manual_setting and isinstance(manual_setting.value, dict):
        manually_completed = set(manual_setting.value.get('steps', []))

    units_count = db.scalar(select(func.count(Unit.id)).where(Unit.tenant_id == tenant_id)) or 0
    users_count = db.scalar(select(func.count(User.id)).where(User.tenant_id == tenant_id)) or 0
    whatsapp_count = db.scalar(
        select(func.count(WhatsAppAccount.id)).where(
            WhatsAppAccount.tenant_id == tenant_id,
            WhatsAppAccount.is_active.is_(True),
        )
    ) or 0
    automations_count = db.scalar(
        select(func.count(Automation.id)).where(
            Automation.tenant_id == tenant_id,
            Automation.is_active.is_(True),
        )
    ) or 0
    campaigns_count = db.scalar(select(func.count(Campaign.id)).where(Campaign.tenant_id == tenant_id)) or 0

    terms_accepted = settings_by_key.get('privacy.accepted_at') is not None

    steps = [
        {
            'id': 'clinic_profile',
            'title': 'Configurar dados da clinica',
            'description': 'Nome de exibicao e timezone operacional.',
            'completed': _has_clinic_profile(settings_by_key),
            'href': '/configuracoes',
        },
        {
            'id': 'units',
            'title': 'Cadastrar unidades',
            'description': 'Unidades permitem agenda e capacidade por local.',
            'completed': units_count >= 1,
            'href': '/configuracoes',
        },
        {
            'id': 'users',
            'title': 'Convidar equipe',
            'description': 'Owner, recepcao e analista para operacao diaria.',
            'completed': users_count >= 2,
            'href': '/usuarios',
        },
        {
            'id': 'whatsapp',
            'title': 'Conectar WhatsApp',
            'description': 'Ativa lembretes, follow-up e atendimento centralizado.',
            'completed': whatsapp_count >= 1,
            'href': '/configuracoes',
        },
        {
            'id': 'import_data',
            'title': 'Importar base',
            'description': 'Importe pacientes e leads por CSV para acelerar onboarding.',
            'completed': settings_by_key.get('onboarding.import_done') is not None or 'import_data' in manually_completed,
            'href': '/importacao',
        },
        {
            'id': 'automations',
            'title': 'Ativar automacoes',
            'description': 'Fluxos de confirmacao, no-show e follow-up.',
            'completed': automations_count >= 1,
            'href': '/automacoes',
        },
        {
            'id': 'campaign',
            'title': 'Publicar primeira campanha',
            'description': 'Acione reativacao e retorno de pacientes.',
            'completed': campaigns_count >= 1,
            'href': '/campanhas',
        },
        {
            'id': 'lgpd',
            'title': 'Aceitar termos e politica',
            'description': 'Finalize conformidade LGPD antes de operar em producao.',
            'completed': terms_accepted or 'lgpd' in manually_completed,
            'href': '/configuracoes',
        },
    ]

    for step in steps:
        if step['id'] in manually_completed:
            step['completed'] = True

    completed = sum(1 for step in steps if step['completed'])
    completion_percent = round((completed / len(steps)) * 100, 2) if steps else 0
    next_step = next((step for step in steps if not step['completed']), None)

    tour_steps = [
        {
            'id': 'tour_dashboard',
            'title': 'Visao executiva no Dashboard',
            'description': 'Entenda KPIs, alertas operacionais e fila do dia.',
            'href': '/dashboard',
            'duration_minutes': 5,
        },
        {
            'id': 'tour_conversas',
            'title': 'Operacao de atendimento',
            'description': 'Aprenda triagem de conversas e acompanhamento por responsavel.',
            'href': '/conversas',
            'duration_minutes': 6,
        },
        {
            'id': 'tour_agenda',
            'title': 'Agenda e confirmacoes',
            'description': 'Valide consulta, status de confirmacao e no-show.',
            'href': '/agenda',
            'duration_minutes': 6,
        },
        {
            'id': 'tour_automacoes',
            'title': 'Automacoes de recuperacao',
            'description': 'Ative gatilhos para lembrete, follow-up e reativacao.',
            'href': '/automacoes',
            'duration_minutes': 6,
        },
        {
            'id': 'tour_faturamento',
            'title': 'Faturamento e limite de plano',
            'description': 'Configure cobranca e acompanhe risco de inadimplencia.',
            'href': '/faturamento',
            'duration_minutes': 5,
        },
    ]

    help_resources = [
        {
            'id': 'resource_go_live',
            'title': 'Checklist de go-live',
            'description': 'Roteiro de abertura operacional em 7 dias.',
            'href': '/onboarding',
            'cta': 'Ver checklist',
        },
        {
            'id': 'resource_import',
            'title': 'Importacao de base por CSV',
            'description': 'Modelo de dados para importar pacientes e leads.',
            'href': '/importacao',
            'cta': 'Abrir importacao',
        },
        {
            'id': 'resource_support',
            'title': 'Canal de suporte e SLA',
            'description': 'Incidentes e tempo de resposta por severidade.',
            'href': '/suporte',
            'cta': 'Abrir suporte',
        },
    ]

    faq = [
        {
            'question': 'Quanto tempo leva para colocar a clinica em operacao?',
            'answer': 'Em media de 3 a 7 dias, dependendo da importacao da base e conexao do WhatsApp.',
        },
        {
            'question': 'Quem precisa participar do onboarding?',
            'answer': 'Owner, recepcao e pelo menos um responsavel comercial para validar fluxos do dia a dia.',
        },
        {
            'question': 'Quando devo ativar automacoes?',
            'answer': 'Assim que agenda e WhatsApp estiverem conectados, para reduzir no-show desde a primeira semana.',
        },
        {
            'question': 'Como solicitar ajuda durante a implantacao?',
            'answer': 'Pela Central de Suporte, abrindo incidente com severidade e impacto operacional.',
        },
    ]

    return {
        'completion_percent': completion_percent,
        'completed_steps': completed,
        'total_steps': len(steps),
        'next_step': next_step,
        'steps': steps,
        'tour': {
            'title': 'Tour guiado de ativacao',
            'description': 'Percurso recomendado para preparar equipe e operacao comercial.',
            'steps': tour_steps,
            'estimated_total_minutes': sum(item['duration_minutes'] for item in tour_steps),
        },
        'help_resources': help_resources,
        'faq': faq,
        'support': {
            'email': 'suporte@odontoflux.com',
            'whatsapp': '+55 11 95555-0101',
            'hours': 'Seg-Sex 08:00-18:00',
        },
    }

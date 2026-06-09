from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
import logging
import re
import secrets
import unicodedata
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi.encoders import jsonable_encoder
from sqlalchemy import delete, func, or_, select
from sqlalchemy.exc import IntegrityError
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
    OutboxMessage,
    Patient,
    PatientContact,
    Professional,
    ProspectAccount,
    ProspectNote,
    ProspectService,
    ProspectTimelineEvent,
    ProspectUnit,
    RefreshToken,
    Role,
    Setting,
    Tenant,
    TenantPlan,
    Unit,
    User,
    UserRole,
    WhatsAppAccount,
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
from app.services.link_flow_service import validate_intake_config_payload
from app.services.llm_service import run_llm_task
from app.services.password_policy_service import validate_password_strength
from app.services.whatsapp_bridge_support import (
    WHATSAPP_WEB_BRIDGE_TRANSPORT,
    resolve_sales_outreach_transport,
)
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

DEMO_AI_DEFAULT_SETTINGS = {
    "enabled": True,
    "whatsapp_enabled": True,
    "max_consecutive_auto_replies": 3,
}

DEMO_INTAKE_DEFAULT_SETTINGS = {
    "mode": "hybrid",
    "link_flow": {
        "enabled": True,
        "cta_mode": "whatsapp_redirect",
        "headline": "Agendamento oficial da clinica",
        "trust_message": "Continue pelo canal oficial para falar com a assistente de agendamento.",
        "button_label": "Continuar pelo WhatsApp",
        "session_ttl_minutes": 30,
    },
}

DEMO_BACKGROUND_DEFAULT_IMAGE_URL = "/images/dental-floss-smile-background.png"
DEMO_BACKGROUND_DEFAULT_OPACITY = 0.18
HANDOFF_CONTACT_PHONE_PATTERN = re.compile(r"(?:(?:telefone|celular|whatsapp|fone|numero)\s*[:\-]?\s*)?(\+?\d[\d\s().-]{8,}\d)")

DEMO_BRANDING_THEME_DEFAULTS = {
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
    "demo_background_image_url": DEMO_BACKGROUND_DEFAULT_IMAGE_URL,
    "demo_background_opacity": DEMO_BACKGROUND_DEFAULT_OPACITY,
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
SALES_OUTREACH_STEPS.update(
    {
        "responsibility_check": "Confirmacao de responsavel pelo WhatsApp",
        "contact_handoff_ack": "Confirmacao de encaminhamento de contato",
        "reception_triage": "Descoberta de responsavel pelo WhatsApp",
        "reception_cta": "CTA final para chegar no decisor",
        "clarification_reply": "Resposta curta para duvida inicial",
        "clarification_cta": "CTA final apos esclarecer a duvida",
        "direct_demo_offer": "Pedido de autorizacao para enviar demo ou resumo direto",
        "timing_followup": "Retorno em melhor horario",
        "auto_reply_hold": "Aguardar retorno da resposta automatica",
        "routing_followup": "Tentativa de identificar canal correto",
        "access_request": "Pedido de encaminhamento interno",
    }
)
SALES_OUTREACH_INITIAL_MESSAGES = (
    "Oi! Tudo bem? Quem cuida dos agendamentos pelo WhatsApp da clinica?",
    "Tudo bem? Consigo falar com quem organiza os agendamentos da clinica por aqui?",
    "Esse numero e usado para novos pacientes e agendamentos?",
    "Oi! Esse WhatsApp e o principal canal de atendimento da clinica?",
    "Consigo falar com alguem responsavel pelo atendimento no WhatsApp da clinica?",
    "Vocês fazem os agendamentos dos pacientes por esse WhatsApp mesmo?",
    "Quem costuma responder os pacientes que chamam a clinica por aqui?",
    "Esse WhatsApp e da recepcao ou de quem cuida dos agendamentos?",
    "Quem seria a melhor pessoa para falar sobre atendimento e agendamentos pelo WhatsApp?",
    "Tudo bem? Esse numero e usado para atendimento e marcacao de consultas?",
)
SALES_OUTREACH_REPLY_CLASSIFICATIONS: dict[str, dict] = {
    "sem_interesse": {
        "priority": 100,
        "keywords": (
            "nao tenho interesse",
            "sem interesse",
            "nao quero",
            "pare",
            "parar",
            "nao entre em contato",
            "retire meu numero",
            "remova meu numero",
        ),
    },
    "automatica": {
        "priority": 90,
        "keywords": (
            "mensagem automatica",
            "resposta automatica",
            "nao respondemos por aqui",
            "este numero e apenas para envio",
            "nao conseguimos responder por aqui",
            "atendimento automatico",
        ),
    },
    "gestor": {
        "priority": 80,
        "keywords": (
            "sou o responsavel",
            "sou a responsavel",
            "sou o gerente",
            "sou a gerente",
            "sou o dono",
            "sou a dona",
            "eu cuido",
            "pode falar comigo",
            "falo por aqui",
            "sou quem cuida",
            "pode mandar a demo",
            "pode mandar o video",
            "pode me mandar",
            "mandar a demo",
            "mandar o video",
            "me manda a demo",
            "manda a demo",
            "manda o video",
        ),
    },
    "recepcao": {
        "priority": 70,
        "keywords": (
            "sou da recepcao",
            "recepcao",
            "posso ajudar",
            "o que precisa",
            "vou encaminhar",
            "vou verificar",
            "pode me falar",
            "atendimento da clinica",
            "sou do atendimento",
            "pode falar",
            "como posso ajudar",
        ),
    },
    "pediu_tempo": {
        "priority": 60,
        "keywords": (
            "agora nao",
            "retorne depois",
            "fala mais tarde",
            "mande mais tarde",
            "estou ocupado",
            "estamos ocupados",
            "sem tempo agora",
            "depois eu vejo",
            "me chama depois",
            "retorna mais tarde",
        ),
    },
    "duvida": {
        "priority": 50,
        "keywords": (
            "sobre o que se trata",
            "do que se trata",
            "quem e voce",
            "como conseguiu meu numero",
            "que tipo de solucao",
            "e sistema",
            "como funciona",
            "sobre o que e",
            "qual o assunto",
            "pode explicar melhor",
        ),
    },
    "fora_de_escopo": {
        "priority": 40,
        "keywords": (
            "nao e da clinica",
            "so financeiro",
            "so suporte",
            "so cobranca",
            "nao cuidamos disso",
            "esse numero nao e para isso",
        ),
    },
    "bloqueio_acesso": {
        "priority": 30,
        "keywords": (
            "nao posso passar contato",
            "manda no e-mail",
            "mande no e-mail",
            "fala pelo site",
            "nao posso informar",
            "nao passamos contato",
        ),
    },
}
SALES_OUTREACH_FLOW_SETTING_KEY = "sales.outreach_flow"
NO_SITE_OUTREACH_FLOW_SETTING_KEY = "sales.no_site_outreach_flow"
NO_SITE_OUTREACH_STAGES = ("first", "second", "third")
NO_SITE_OUTREACH_STAGE_TO_STEP = {
    "first": "no_site_first",
    "second": "no_site_second",
    "third": "no_site_third",
}
NO_SITE_OUTREACH_STAGE_LABELS = {
    "first": "Primeira mensagem sem site",
    "second": "Segunda mensagem sem site",
    "third": "Terceira mensagem sem site",
}
AFFILIATE_FIRST_MESSAGES_SETTING_PREFIX = "sales.affiliate_first_messages"
AFFILIATE_FIRST_MESSAGE_DEFAULTS = [
    (
        "Oi, tudo bem? Encontrei a clinica no Google. Aqui e o time comercial da ClinicFlux AI. "
        "Posso falar com quem cuida do WhatsApp e dos agendamentos?"
    ),
    (
        "Ola! Aqui e o time comercial da ClinicFlux AI. Vi a clinica no Google e queria apresentar "
        "uma ideia para melhorar o atendimento e os agendamentos pelo WhatsApp. Quem cuida dessa parte?"
    ),
    (
        "Oi, tudo bem? Meu contato e comercial. Trabalho com a ClinicFlux AI e encontrei a clinica "
        "em uma busca local. Posso falar com a pessoa responsavel pelo atendimento no WhatsApp?"
    ),
    (
        "Bom dia! Aqui e da ClinicFlux AI. Estamos conversando com clinicas da regiao sobre atendimento "
        "e agenda pelo WhatsApp. Quem seria a pessoa ideal para eu explicar rapidamente?"
    ),
    (
        "Ola! Encontrei a clinica no Google e gostaria de mostrar uma oportunidade comercial da ClinicFlux AI. "
        "Com quem posso falar sobre WhatsApp, recepcao e agendamentos?"
    ),
]
AFFILIATE_SECOND_MESSAGE_DEFAULTS = [
    (
        "Oi! Passando so para confirmar se conseguiu ver minha mensagem anterior. "
        "Se fizer sentido, posso explicar a ideia em dois minutos por aqui."
    ),
    (
        "Ola! Retomando meu contato comercial sobre WhatsApp e agendamentos. "
        "Posso falar com a pessoa responsavel por essa area?"
    ),
    (
        "Oi, tudo bem? So fazendo um acompanhamento rapido da mensagem que enviei. "
        "Se nao for o momento, pode me avisar sem problema."
    ),
    (
        "Bom dia! Queria apenas confirmar se este e o melhor canal para falar sobre "
        "atendimento e agenda da clinica."
    ),
    (
        "Ola! Voltei de forma breve sobre a oportunidade que encontrei para a clinica. "
        "Posso encaminhar um resumo para o responsavel?"
    ),
]
AFFILIATE_THIRD_MESSAGE_DEFAULTS = [
    (
        "Obrigado por responder. Para facilitar, posso te enviar um resumo curto da ideia "
        "e um exemplo preparado para a clinica?"
    ),
    (
        "Perfeito, obrigado pelo retorno. Posso mostrar em poucos minutos como a ClinicFlux AI "
        "ajuda no WhatsApp e nos agendamentos?"
    ),
    (
        "Obrigado pela abertura. Se preferir, eu envio primeiro um exemplo e voce avalia "
        "sem compromisso antes de continuarmos."
    ),
    (
        "Entendi. Posso adaptar a apresentacao ao que mais pesa hoje para voces: atendimento, "
        "agenda ou presenca no Google?"
    ),
    (
        "Obrigado pelo retorno. Qual seria a melhor forma de seguir: um resumo por aqui "
        "ou uma conversa rapida com o responsavel?"
    ),
]
AFFILIATE_CONTACT_MESSAGE_DEFAULTS = {
    "first": AFFILIATE_FIRST_MESSAGE_DEFAULTS,
    "second": AFFILIATE_SECOND_MESSAGE_DEFAULTS,
    "third": AFFILIATE_THIRD_MESSAGE_DEFAULTS,
}
NO_SITE_OUTREACH_MESSAGE_DEFAULTS = {
    "first": [
        (
            "Oi, tudo bem?\n\n"
            "Notei que a clinica ainda nao possui um site profissional.\n\n"
            "Eu ja montei um modelo de site para a clinica e gostaria de mostrar ao responsavel.\n\n"
            "Quem seria a pessoa ideal para eu encaminhar?"
        ),
        (
            "Oi, tudo bem? Encontrei a clinica no Google e vi que voces ainda nao aparecem com um site proprio. "
            "Aqui e o time comercial da ClinicFlux AI. Quem cuida dessa parte de site e WhatsApp por ai?"
        ),
        (
            "Bom dia! Aqui e o time comercial da ClinicFlux AI. Vi a clinica pelo Google e parece que ainda nao existe um site vinculado. "
            "Posso falar com quem decide sobre presenca online e WhatsApp?"
        ),
    ],
    "second": [
        (
            "Obrigado. Meu contato e comercial, nao e para agendamento de paciente. "
            "A ideia e mostrar um modelo simples de site local com WhatsApp, mapa e servicos. Quem seria o responsavel por isso?"
        ),
        (
            "So para alinhar: falo pela ClinicFlux AI, no contato comercial. "
            "Vi uma oportunidade de site local para ajudar pacientes a encontrarem a clinica no Google. Posso encaminhar ao responsavel?"
        ),
        (
            "Passando de forma bem objetiva: preparei um modelo de site para clinicas que ainda dependem so do Google e WhatsApp. "
            "Faz sentido eu mandar para quem cuida dessa decisao?"
        ),
    ],
    "third": [
        "Perfeito. Posso te enviar o preview do modelo de site da clinica para voce avaliar se faz sentido levar adiante?",
        "Boa. A proposta e simples: site local com WhatsApp, mapa, servicos e prova de confianca. Quer que eu te mostre o preview rapido?",
        "Combinado. Se voce me autorizar, envio um preview curto do site e depois voces decidem se vale conversar.",
    ],
}
SALES_OUTREACH_STEP_MESSAGE_DEFAULTS = {
    "responsibility_check": [
        "Perfeito. Voce mesmo cuida dos agendamentos e do atendimento no WhatsApp da clinica?",
        "Perfeito. E voce quem responde os pacientes e organiza os agendamentos por ai?",
        "Entendi. Para eu te responder certo: e voce quem cuida do atendimento e dos agendamentos da clinica?",
        "Perfeito. Posso seguir com voce mesmo sobre atendimento e agendamentos no WhatsApp da clinica?",
        "Antes de seguir, so para alinhar: e voce quem responde esse WhatsApp e cuida dos agendamentos por ai?",
    ],
    "contact_handoff_ack": [
        "Perfeito, obrigado! Pode me encaminhar por aqui, por favor.",
        "Perfeito, obrigado pelo apoio. Pode me passar esse contato por aqui mesmo.",
        "Combinado, obrigado! Assim que voce me enviar o contato, eu sigo por aqui.",
        "Perfeito. Pode me encaminhar o contato do setor por aqui, por favor.",
        "Obrigado! Fico no aguardo do contato para seguir com a pessoa responsavel.",
    ],
    "reception_triage": [
        (
            "Perfeito. Estou falando com clinicas porque muitas acabam perdendo pacientes por demora no WhatsApp, "
            "agenda desorganizada e falta de acompanhamento{pain_hint}.\n"
            "Quem seria a melhor pessoa para eu falar sobre isso por ai: gerente, dono(a) ou responsavel pelo atendimento?"
        ),
        (
            "Entendi. Tenho falado com clinicas que querem responder mais rapido, organizar melhor os agendamentos e evitar paciente esfriando no WhatsApp{pain_hint}.\n"
            "Quem costuma cuidar dessa parte por ai: gerente, dono(a) ou responsavel pela recepcao?"
        ),
        (
            "Perfeito. O motivo do meu contato e que muitas clinicas ainda acabam deixando consulta escapar por falha no atendimento e no retorno pelo WhatsApp{pain_hint}.\n"
            "Quem seria a pessoa certa para eu falar sobre isso com mais contexto?"
        ),
        (
            "Faz sentido. Estou conversando com clinicas para entender como elas organizam atendimento, agenda e retorno aos pacientes sem perder oportunidade no caminho{pain_hint}.\n"
            "Voce consegue me indicar quem responde por essa operacao ai?"
        ),
        (
            "Obrigado. O que eu mais vejo hoje e clinica perdendo paciente por demora no WhatsApp, processo manual e falta de acompanhamento depois do primeiro contato{pain_hint}.\n"
            "Com quem vale eu falar sobre isso por ai?"
        ),
    ],
    "reception_cta": [
        "Perfeito. Se fizer sentido, posso te mandar um resumo bem objetivo para voce encaminhar ao responsavel pelo atendimento e agendamentos.",
        "Sem problema. Se quiser, eu deixo uma mensagem curta pronta para voce repassar a quem decide essa parte na clinica.",
        "Posso te mandar uma explicacao rapida para voce avaliar se vale passar para o gerente ou dono(a)?",
        "Se ajudar, eu consigo resumir em poucas linhas como isso reduz demora no WhatsApp e perda de paciente, para ficar facil de encaminhar.",
        "Se fizer sentido, eu te mando uma versao bem direta para encaminhar a quem cuida dessa decisao por ai.",
    ],
    "clarification_reply": [
        (
            "Claro. Eu falo com clinicas porque muitas ainda acabam perdendo pacientes no WhatsApp por demora no atendimento, "
            "falta de resposta e agendamentos que se perdem no processo. A ideia e entender se isso tambem acontece ai e, se fizer sentido, te mostrar uma forma simples de organizar isso."
        ),
        (
            "Claro. O foco e ajudar clinicas a organizar atendimento e agendamentos pelo WhatsApp para responder mais rapido, perder menos pacientes e ter mais controle da operacao."
        ),
        (
            "Explico sim. Estou falando com clinicas que querem melhorar o atendimento no WhatsApp, evitar demora no retorno e transformar mais conversas em consulta agendada."
        ),
        (
            "Resumindo: a gente ajuda a organizar a operacao de atendimento da clinica no WhatsApp para que menos pacientes esfriem antes do agendamento."
        ),
        (
            "E uma forma de deixar o atendimento pelo WhatsApp mais organizado, com menos atraso na resposta, menos retrabalho e menos oportunidade perdida no processo da clinica."
        ),
    ],
    "clarification_cta": [
        "Se fizer sentido, posso te mostrar em 1 minuto como isso funciona na pratica por aqui mesmo.",
        "Se voce quiser, eu consigo te explicar de forma bem objetiva como isso ajuda a clinica a responder mais rapido e converter mais agendamentos.",
        "Faz sentido eu te mostrar rapidamente como isso organiza atendimento e agendamentos sem aumentar trabalho da equipe?",
        "Se preferir, eu posso resumir agora o ganho pratico e voce me diz se vale aprofundar.",
        "Posso te mostrar de forma bem curta onde isso normalmente reduz perda de pacientes no WhatsApp e melhora o retorno comercial?",
    ],
    "direct_demo_offer": [
        "Se for mais facil, posso te mandar uma demonstracao curta ou um resumo objetivo para voce validar se vale encaminhar internamente.",
        "Se ajudar, eu posso te enviar agora um material bem rapido para voce ver se faz sentido passar ao responsavel.",
        "Posso te mandar uma demo curta por aqui e, se fizer sentido, voce encaminha para quem decide essa parte?",
        "Se preferir, eu envio um resumo bem direto ou uma demonstracao rapida para facilitar essa avaliacao interna.",
        "Tudo bem. Posso te mandar um exemplo curto de como isso funciona e voce me diz se vale levar adiante por ai?",
    ],
    "timing_followup": [
        "Sem problema. Qual horario costuma ser melhor para eu te chamar sem atrapalhar?",
        "Tranquilo. Qual costuma ser o melhor horario para eu falar com voce sobre isso com mais objetividade?",
        "Sem problema nenhum. Se voce preferir, me diz um horario melhor e eu volto nesse momento.",
        "Claro. Para nao atrapalhar, qual horario costuma funcionar melhor por ai?",
        "Tudo bem. Me fala um horario melhor e eu retomo com voce de forma bem direta.",
    ],
    "auto_reply_hold": [
        "Beleza, vou aguardar o próximo retorno.",
        "Perfeito, fico no aguardo do próximo retorno.",
        "Tudo bem, vou aguardar a próxima mensagem da clínica.",
        "Combinado, vou esperar o próximo retorno por aqui.",
        "Certo, sigo no aguardo do próximo retorno.",
    ],
    "routing_followup": [
        "Entendi. Voce saberia me dizer qual e o canal ou a pessoa certa para falar sobre atendimento e agendamentos da clinica?",
        "Sem problema. Quem costuma responder por atendimento, WhatsApp e agendamentos por ai?",
        "Perfeito. Se nao for com voce, quem seria a pessoa certa para eu falar sobre esse tema na clinica?",
        "Entendi. Qual seria o melhor contato para tratar de atendimento, WhatsApp e conversao de agendamentos por ai?",
        "Tudo certo. Voce consegue me indicar quem cuida dessa parte na clinica?",
    ],
    "access_request": [
        "Tudo certo. Se for mais facil, posso resumir em uma frase por aqui e voce me diz se vale encaminhar para o responsavel.",
        "Sem problema. Se ajudar, eu posso te mandar um resumo bem curto para voce avaliar se faz sentido encaminhar.",
        "Claro. Posso te explicar em uma frase o objetivo e voce decide se vale passar para a pessoa certa.",
        "Tranquilo. Se preferir, eu deixo um resumo rapido por aqui e voce ve se faz sentido encaminhar.",
        "Tudo bem. Posso resumir de forma objetiva por aqui e voce me diz se vale levar isso ao responsavel.",
    ],
}
SALES_OUTREACH_CLASS_TO_STEP_DEFAULTS = {
    "gestor": "decision_maker_pitch",
    "recepcao": "reception_triage",
    "duvida": "clarification_reply",
    "pediu_tempo": "timing_followup",
    "automatica": "auto_reply_hold",
    "fora_de_escopo": "routing_followup",
    "bloqueio_acesso": "access_request",
}

SALES_OUTREACH_AI_ALLOWED_CLASSES = {
    "gestor",
    "recepcao",
    "pediu_tempo",
    "duvida",
    "fora_de_escopo",
    "bloqueio_acesso",
    "automatica",
}

ADM_INTERNAL_WHATSAPP_SIMULATION_SOURCE = "adm_internal_whatsapp_simulation"
ADM_INTERNAL_WHATSAPP_SIMULATION_TAG = "adm_whatsapp_internal_simulation"
SALES_OUTREACH_SEND_GATE_DECISIONS = {"send", "wait", "block"}
SALES_OUTREACH_OPT_OUT_PATTERNS = (
    "pare",
    "parar",
    "remova",
    "remover",
    "nao quero",
    "nao tenho interesse",
    "nao temos interesse",
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
DEFAULT_SALES_OUTREACH_SENDER_TENANT_SLUG = "clinicflux-ai-system"
DEFAULT_SALES_OUTREACH_SENDER_TENANT_LEGAL_NAME = "ClinicFlux AI Comercial LTDA"
DEFAULT_SALES_OUTREACH_SENDER_TENANT_TRADE_NAME = "ClinicFlux AI Comercial"
ADM_BOOTSTRAP_GRANT_ROLE_NAMES = ("admin_platform", "sales_admin")
ADM_BOOTSTRAP_ACCESS_ROLE_NAMES = ("admin_platform", "sales_admin", "sales_viewer")
ADM_FULL_ACCESS_ROLE_NAMES = ("admin_platform", "sales_admin")
ADM_AFFILIATE_ROLE_NAME = "sales_affiliate"
ADM_BOOTSTRAP_MANAGED_KEY = "adm_bootstrap_managed"
ADM_BOOTSTRAP_VERSION_KEY = "adm_bootstrap_version"
ADM_INITIAL_PASSWORD_KEY = "adm_initial_password"
ADM_AFFILIATE_MARKER_KEY = "adm_affiliate"
ADM_BOOTSTRAP_DISPLAY_NAME = "Admin Comercial ClinicFlux AI"
ADM_PERMISSION_ACTIONS = ("view", "create", "edit", "delete")
ADM_MANAGED_PAGES = (
    {"key": "adm_crm", "href": "/adm", "label": "CRM comercial"},
    {"key": "adm_messages", "href": "/adm/mensagens-para-clinicas", "label": "Mensagens prontas"},
    {"key": "adm_site_templates", "href": "/adm/modelos-sites", "label": "Modelos de sites"},
    {"key": "adm_outreach_automation", "href": "/adm/automacao-comercial", "label": "Automacao comercial"},
    {"key": "adm_import_places", "href": "/adm/importar-clinicas", "label": "Importar Google Places"},
    {"key": "adm_whatsapp", "href": "/adm", "label": "WhatsApp do /adm"},
    {"key": "adm_whatsapp_settings", "href": "/adm", "label": "WhatsApp do sistema"},
    {"key": "adm_agent_settings", "href": "/adm/configuracoes", "label": "Configuracoes do agente"},
    {"key": "adm_implementations", "href": "/adm/implementacoes", "label": "Implementacoes"},
    {"key": "adm_affiliates", "href": "/adm/afiliados", "label": "Afiliados"},
)
ADM_DEFAULT_AFFILIATE_PERMISSIONS = {
    "adm_crm": {"view": True, "create": True, "edit": True, "delete": False},
    "adm_messages": {"view": True, "create": True, "edit": True, "delete": False},
    "adm_site_templates": {"view": True, "create": True, "edit": True, "delete": False},
}
ADM_VIEWER_DEFAULT_PERMISSIONS = {
    "adm_crm": {"view": True, "create": False, "edit": False, "delete": False},
    "adm_messages": {"view": True, "create": False, "edit": False, "delete": False},
    "adm_site_templates": {"view": True, "create": False, "edit": False, "delete": False},
    "adm_outreach_automation": {"view": True, "create": False, "edit": False, "delete": False},
    "adm_whatsapp": {"view": True, "create": False, "edit": False, "delete": False},
}
PUBLIC_SITE_QUICK_DEMO_TAGS = ("site_home_demo", "demo_rapida")
PUBLIC_SITE_QUICK_DEMO_CHANNEL = "site_home_demo"
PUBLIC_SITE_QUICK_DEMO_LEAD_SOURCE = "site_home_demo"
PUBLIC_SITE_QUICK_DEMO_NOTE = "Demo rapida solicitada pela home publica."


def _adm_bootstrap_credentials_configured() -> bool:
    return bool(settings.adm_bootstrap_email and settings.adm_bootstrap_password)


def _now() -> datetime:
    return datetime.now(UTC)


def _utc_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


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


def _resolve_demo_timezone(timezone_name: str | None) -> ZoneInfo:
    candidate = str(timezone_name or settings.app_timezone or "America/Sao_Paulo").strip()
    try:
        return ZoneInfo(candidate)
    except ZoneInfoNotFoundError:
        return ZoneInfo("America/Sao_Paulo")


def _parse_minutes_since_midnight(time_text: str | None, *, fallback: int) -> int:
    candidate = str(time_text or "").strip()
    match = re.fullmatch(r"([01]?\d|2[0-3]):([0-5]\d)", candidate)
    if not match:
        return fallback
    return int(match.group(1)) * 60 + int(match.group(2))


def _parse_working_hours_range_text(value: object) -> tuple[int, int] | None:
    text = str(value or "").strip()
    match = re.fullmatch(r"([01]?\d|2[0-3]):([0-5]\d)\s*-\s*([01]?\d|2[0-3]):([0-5]\d)", text)
    if not match:
        return None
    start = int(match.group(1)) * 60 + int(match.group(2))
    end = int(match.group(3)) * 60 + int(match.group(4))
    if end <= start:
        return None
    return start, end


def _resolve_unit_working_window_minutes(unit: Unit | None) -> tuple[int, int]:
    if not unit or not isinstance(unit.working_hours, dict):
        return 8 * 60, 18 * 60

    working_hours = unit.working_hours
    for key in ("range", "hours", "monday_friday", "seg-sex", "segunda-sexta", "segunda sexta"):
        parsed_range = _parse_working_hours_range_text(working_hours.get(key))
        if parsed_range:
            return parsed_range

    start = _parse_minutes_since_midnight(
        working_hours.get("start") or working_hours.get("opens_at"),
        fallback=8 * 60,
    )
    end = _parse_minutes_since_midnight(
        working_hours.get("end") or working_hours.get("closes_at"),
        fallback=18 * 60,
    )
    if end <= start:
        return 8 * 60, 18 * 60
    return start, end


def _resolve_professional_working_window_minutes(professional: Professional | None) -> tuple[int, int]:
    if not professional:
        return 8 * 60, 18 * 60
    start = _parse_minutes_since_midnight(professional.shift_start, fallback=8 * 60)
    end = _parse_minutes_since_midnight(professional.shift_end, fallback=18 * 60)
    if end <= start:
        return 8 * 60, 18 * 60
    return start, end


def _build_demo_showcase_slot_start(
    *,
    showcase_day_local: datetime,
    preferred_time_text: str,
    tenant_timezone: ZoneInfo,
    unit: Unit | None,
    professional: Professional | None,
    duration_minutes: int = 60,
) -> datetime:
    preferred_minutes = _parse_minutes_since_midnight(preferred_time_text, fallback=9 * 60)
    unit_start, unit_end = _resolve_unit_working_window_minutes(unit)
    professional_start, professional_end = _resolve_professional_working_window_minutes(professional)
    effective_start = max(unit_start, professional_start)
    effective_end = min(unit_end, professional_end)

    if effective_end - effective_start < duration_minutes:
        effective_start = 8 * 60
        effective_end = 18 * 60

    last_possible_start = max(effective_start, effective_end - duration_minutes)
    clamped_minutes = min(max(preferred_minutes, effective_start), last_possible_start)

    local_slot = showcase_day_local.replace(
        hour=clamped_minutes // 60,
        minute=clamped_minutes % 60,
        second=0,
        microsecond=0,
        tzinfo=tenant_timezone,
    )
    return local_slot.astimezone(UTC)


def _slugify(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", str(value or ""))
    text = normalized.encode("ascii", "ignore").decode("ascii").lower().strip()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-") or "clinica-demo"


def _last_four_phone_digits(*phones: str | None) -> str | None:
    for phone in phones:
        normalized = normalize_phone(phone)
        if len(normalized) >= 4:
            return normalized[-4:]
    return None


def _limited_slug(base: str, suffix: str | None = None, *, max_length: int = 120) -> str:
    clean_base = (base or "clinica-demo").strip("-") or "clinica-demo"
    clean_suffix = (suffix or "").strip("-")
    suffix_text = f"-{clean_suffix}" if clean_suffix else ""
    available = max(1, max_length - len(suffix_text))
    trimmed_base = clean_base[:available].strip("-") or "clinica-demo"
    return f"{trimmed_base}{suffix_text}"[:max_length].strip("-") or "clinica-demo"


def _prospect_name_exists(db: Session, *, clinic_name: str, current_prospect_id: UUID | None = None) -> bool:
    normalized_name = str(clinic_name or "").strip().lower()
    if not normalized_name:
        return False
    stmt = select(ProspectAccount.id).where(func.lower(ProspectAccount.clinic_name) == normalized_name)
    if current_prospect_id:
        stmt = stmt.where(ProspectAccount.id != current_prospect_id)
    return db.scalar(stmt.limit(1)) is not None


def _unique_seed_key(db: Session, candidate: str, *, current_prospect_id: UUID | None = None) -> str:
    base = (candidate or "clinica-demo").strip("-")[:120] or "clinica-demo"
    index = 2
    current = base
    while True:
        stmt = select(ProspectAccount.id).where(ProspectAccount.tenant_seed_key == current)
        if current_prospect_id:
            stmt = stmt.where(ProspectAccount.id != current_prospect_id)
        if db.scalar(stmt.limit(1)) is None:
            return current
        suffix = f"-{index}"
        current = f"{base[: 120 - len(suffix)]}{suffix}"
        index += 1


def _friendly_prospect_key(
    db: Session,
    *,
    clinic_name: str,
    phone: str | None,
    whatsapp_phone: str | None,
    current_prospect_id: UUID | None = None,
) -> str:
    base = _slugify(clinic_name)
    has_same_name = _prospect_name_exists(db, clinic_name=clinic_name, current_prospect_id=current_prospect_id)
    suffix = _last_four_phone_digits(whatsapp_phone, phone) if has_same_name else None
    candidate = _limited_slug(base, suffix)
    if has_same_name and not suffix:
        candidate = _limited_slug(base, "2")
    return _unique_seed_key(db, candidate, current_prospect_id=current_prospect_id)


def _demo_token_taken(db: Session, token: str, *, current_prospect_id: UUID | None = None) -> bool:
    stmt = select(ProspectAccount.id).where(ProspectAccount.demo_access_token_hash == sha256_text(token))
    if current_prospect_id:
        stmt = stmt.where(ProspectAccount.id != current_prospect_id)
    return db.scalar(stmt.limit(1)) is not None


def _friendly_demo_access_token(db: Session, prospect: ProspectAccount) -> str:
    base = _slugify(prospect.clinic_name)
    has_same_name = _prospect_name_exists(db, clinic_name=prospect.clinic_name, current_prospect_id=prospect.id)
    suffix = _last_four_phone_digits(prospect.whatsapp_phone, prospect.phone, prospect.test_phone_number) if has_same_name else None
    candidate = _limited_slug(base, suffix)
    if has_same_name and not suffix:
        candidate = _limited_slug(base, "2")

    index = 2
    token = candidate
    while _demo_token_taken(db, token, current_prospect_id=prospect.id):
        token = _limited_slug(candidate, str(index))
        index += 1
    return token


def build_demo_login_url(base_url: str, token: str) -> str:
    return f"{base_url}/login?demo_token={token}"


def build_demo_booking_path(clinic_slug: str) -> str:
    return f"/agendar/{clinic_slug}"


def build_demo_booking_url(base_url: str, clinic_slug: str) -> str:
    normalized_base = str(base_url or "").rstrip("/") or "http://localhost:3000"
    return f"{normalized_base}{build_demo_booking_path(clinic_slug)}"


def _resolve_demo_booking_slug(db: Session, *, prospect: ProspectAccount) -> str | None:
    if not prospect.demo_tenant_id:
        return None
    tenant = db.get(Tenant, prospect.demo_tenant_id)
    if not tenant:
        return None
    return str(tenant.slug or "").strip() or None


def _resolve_demo_booking_path(db: Session, *, prospect: ProspectAccount) -> str | None:
    demo_slug = _resolve_demo_booking_slug(db, prospect=prospect)
    if not demo_slug:
        return None
    return build_demo_booking_path(demo_slug)


def resolve_demo_booking_path(db: Session, *, prospect: ProspectAccount) -> str | None:
    return _resolve_demo_booking_path(db, prospect=prospect)


def _demo_email(prospect: ProspectAccount) -> str:
    seed = prospect.tenant_seed_key or _slugify(prospect.clinic_name)
    return f"demo+{seed}@demo.clinicfluxai.com.br"


def _random_password() -> str:
    # Meets the local password policy while staying temporary and non-human-picked.
    return f"Demo.{secrets.token_urlsafe(16)}A1"


def _normalize_site_template_slug(value: str | None) -> str | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    return _slugify(raw)[:120] or None


def build_site_template_preview_path(
    template_slug: str,
    *,
    clinic_name: str | None = None,
    city: str | None = None,
    whatsapp: str | None = None,
) -> str:
    path = f"/modelos-sites/{template_slug}"
    params = {
        key: value
        for key, value in {
            "clinic": str(clinic_name or "").strip(),
            "city": str(city or "").strip(),
            "whatsapp": str(whatsapp or "").strip(),
        }.items()
        if value
    }
    query = urlencode(params)
    return f"{path}?{query}" if query else path


def build_site_template_preview_url(
    base_url: str,
    template_slug: str,
    *,
    clinic_name: str | None = None,
    city: str | None = None,
    whatsapp: str | None = None,
) -> str:
    normalized_base = str(base_url or "").rstrip("/") or "http://localhost:3000"
    return f"{normalized_base}{build_site_template_preview_path(template_slug, clinic_name=clinic_name, city=city, whatsapp=whatsapp)}"


def _public_site_demo_snapshot(*, template_slug: str | None = None, base_url: str | None = None, clinic_name: str | None = None, city: str | None = None, whatsapp: str | None = None) -> dict:
    intake_settings = jsonable_encoder(DEMO_INTAKE_DEFAULT_SETTINGS)
    link_flow = intake_settings.get("link_flow") if isinstance(intake_settings.get("link_flow"), dict) else {}
    intake_settings["mode"] = "hybrid"
    intake_settings["link_flow"] = {
        **link_flow,
        "enabled": True,
        "cta_mode": "webchat",
        "headline": "Agendamento oficial da clinica",
        "trust_message": "Teste o agendamento como se fosse um paciente em menos de um minuto.",
        "button_label": "Simular como paciente",
    }
    snapshot = {
        "demo_intake": intake_settings,
    }
    normalized_template_slug = _normalize_site_template_slug(template_slug)
    if normalized_template_slug:
        personalized_path = build_site_template_preview_path(
            normalized_template_slug,
            clinic_name=clinic_name,
            city=city,
            whatsapp=whatsapp,
        )
        snapshot["site_template"] = {
            "version": "2026.05.30-initial-10",
            "selected_template_slug": normalized_template_slug,
            "selected_at": _now().isoformat(),
            "source": "public_site_templates",
            "public_catalog_path": "/modelos-sites",
            "public_preview_path": f"/modelos-sites/{normalized_template_slug}",
            "personalized_preview_path": personalized_path,
            "personalized_preview_url": f"{str(base_url or 'http://localhost:3000').rstrip('/')}{personalized_path}",
        }
    return snapshot


def _find_public_site_prospect(db: Session, *, clinic_name: str, phone: str) -> ProspectAccount | None:
    normalized_name = str(clinic_name or "").strip().lower()
    raw_phone = str(phone or "").strip()
    if not normalized_name and not raw_phone:
        return None

    stmt = (
        select(ProspectAccount)
        .where(
            or_(
                ProspectAccount.whatsapp_phone == raw_phone,
                ProspectAccount.phone == raw_phone,
                func.lower(ProspectAccount.clinic_name) == normalized_name,
            )
        )
        .order_by(ProspectAccount.updated_at.desc())
    )
    return db.scalar(stmt.limit(1))


def ensure_sales_roles(db: Session) -> dict[str, Role]:
    roles = {
        "sales_admin": ["sales.prospects.manage", "sales.demos.manage", "sales.activity.read"],
        "sales_viewer": ["sales.prospects.read", "sales.activity.read"],
        ADM_AFFILIATE_ROLE_NAME: ["sales.prospects.manage", "sales.activity.read"],
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
                scope="platform"
                if name in {"admin_platform", "sales_admin", "sales_viewer", ADM_AFFILIATE_ROLE_NAME}
                else "tenant",
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


def _bootstrap_version() -> str:
    return str(settings.adm_bootstrap_version or "1").strip() or "1"


def _page_permissions(user: User) -> dict:
    return dict(user.page_permissions or {})


def _empty_adm_permission_flags() -> dict[str, bool]:
    return {action: False for action in ADM_PERMISSION_ACTIONS}


def _clone_adm_permission_flags(raw: object) -> dict[str, bool]:
    if not isinstance(raw, dict):
        return _empty_adm_permission_flags()
    return {action: bool(raw.get(action)) for action in ADM_PERMISSION_ACTIONS}


def _empty_adm_page_permissions() -> dict[str, dict[str, bool]]:
    return {str(page["key"]): _empty_adm_permission_flags() for page in ADM_MANAGED_PAGES}


def _full_adm_page_permissions() -> dict[str, dict[str, bool]]:
    return {str(page["key"]): {action: True for action in ADM_PERMISSION_ACTIONS} for page in ADM_MANAGED_PAGES}


def adm_page_definitions() -> list[dict[str, str]]:
    return [dict(page) for page in ADM_MANAGED_PAGES]


def normalize_adm_page_permissions(
    raw_permissions: dict | None,
    roles: list[str] | tuple[str, ...] | set[str] | None = None,
) -> dict[str, dict[str, bool]]:
    role_set = set(roles or [])
    if role_set.intersection(ADM_FULL_ACCESS_ROLE_NAMES):
        return _full_adm_page_permissions()

    normalized = _empty_adm_page_permissions()
    defaults: dict[str, dict[str, bool]] = {}
    if ADM_AFFILIATE_ROLE_NAME in role_set:
        defaults.update(ADM_DEFAULT_AFFILIATE_PERMISSIONS)
    if "sales_viewer" in role_set:
        defaults.update(ADM_VIEWER_DEFAULT_PERMISSIONS)

    for page_key, flags in defaults.items():
        normalized[page_key] = _clone_adm_permission_flags(flags)

    raw = raw_permissions or {}
    for page in ADM_MANAGED_PAGES:
        page_key = str(page["key"])
        if page_key in raw:
            normalized[page_key] = _clone_adm_permission_flags(raw.get(page_key))

    return normalized


def _write_adm_page_permissions(
    current_permissions: dict | None,
    page_permissions: dict | None,
    *,
    mark_affiliate: bool = False,
) -> dict:
    permissions = dict(current_permissions or {})
    normalized = normalize_adm_page_permissions(page_permissions or {}, roles=[])
    for page in ADM_MANAGED_PAGES:
        page_key = str(page["key"])
        if page_permissions and page_key in page_permissions:
            permissions[page_key] = normalized[page_key]
    if mark_affiliate:
        permissions[ADM_AFFILIATE_MARKER_KEY] = True
    return permissions


def _user_role_ids(db: Session, user_id: UUID) -> set[UUID]:
    return {row[0] for row in db.execute(select(UserRole.role_id).where(UserRole.user_id == user_id)).all()}


def _user_role_names(db: Session, user_id: UUID) -> list[str]:
    return [
        row[0]
        for row in db.execute(
            select(Role.name)
            .join(UserRole, UserRole.role_id == Role.id)
            .where(UserRole.user_id == user_id)
            .order_by(Role.name.asc())
        ).all()
    ]


def _revoke_user_refresh_tokens(db: Session, *, user_id: UUID) -> None:
    db.execute(delete(RefreshToken).where(RefreshToken.user_id == user_id))


def _demo_has_expired(prospect: ProspectAccount) -> bool:
    return bool(prospect.demo_expires_at and prospect.demo_expires_at <= _now())


def cleanup_demo_resources(
    db: Session,
    *,
    prospect: ProspectAccount,
    reason: str,
    actor_id: UUID | None = None,
    delete_prospect: bool = False,
) -> dict[str, object]:
    demo_tenant_id = prospect.demo_tenant_id
    demo_user_id = prospect.demo_user_id
    demo_tenant = db.get(Tenant, demo_tenant_id) if demo_tenant_id else None
    demo_user = db.get(User, demo_user_id) if demo_user_id else None

    if demo_user_id:
        _revoke_user_refresh_tokens(db, user_id=demo_user_id)

    if demo_tenant:
        db.delete(demo_tenant)
    elif demo_user and (not demo_tenant_id or demo_user.tenant_id == demo_tenant_id):
        db.delete(demo_user)

    normalized_reason = "expired" if str(reason or "").strip().lower() == "expired" else "deleted"
    now = _now()
    prospect.demo_tenant_id = None
    prospect.demo_user_id = None
    prospect.demo_login_email = None
    prospect.demo_access_token_hash = None
    prospect.demo_access_token_expires_at = None
    prospect.demo_access_revoked_at = now
    prospect.demo_status = "expirada" if normalized_reason == "expired" else "removida"
    prospect.demo_checklist = {}
    prospect.demo_expires_at = now if normalized_reason == "expired" else None
    db.add(prospect)

    if not delete_prospect:
        add_timeline(
            db,
            prospect,
            event_type=f"demo.{normalized_reason}_cleanup",
            event_label="Demo expirada e limpa automaticamente"
            if normalized_reason == "expired"
            else "Demo e dados vinculados removidos",
            actor_id=actor_id,
            actor_type="system" if actor_id is None else "admin",
            payload={
                "reason": normalized_reason,
                "demo_tenant_id": str(demo_tenant_id) if demo_tenant_id else None,
                "demo_user_id": str(demo_user_id) if demo_user_id else None,
            },
        )

    db.flush()
    return {
        "tenant_deleted": bool(demo_tenant_id),
        "user_deleted": bool(demo_user_id),
        "reason": normalized_reason,
    }


def cleanup_expired_demos(db: Session) -> dict[str, int]:
    prospects = db.execute(
        select(ProspectAccount).where(
            ProspectAccount.demo_tenant_id.is_not(None),
            ProspectAccount.demo_expires_at.is_not(None),
            ProspectAccount.demo_expires_at <= _now(),
        )
    ).scalars().all()

    cleaned = 0
    for prospect in prospects:
        cleanup_demo_resources(
            db,
            prospect=prospect,
            reason="expired",
            actor_id=None,
        )
        cleaned += 1

    if cleaned:
        db.commit()

    return {
        "processed": len(prospects),
        "cleaned": cleaned,
    }


def _retire_bootstrap_access(
    db: Session,
    *,
    user: User,
    access_role_ids: set[UUID],
) -> None:
    db.execute(delete(UserRole).where(UserRole.user_id == user.id, UserRole.role_id.in_(tuple(access_role_ids))))
    permissions = _page_permissions(user)
    permissions.pop(ADM_INITIAL_PASSWORD_KEY, None)
    permissions.pop(ADM_BOOTSTRAP_MANAGED_KEY, None)
    permissions.pop(ADM_BOOTSTRAP_VERSION_KEY, None)
    user.page_permissions = permissions
    db.add(user)
    _revoke_user_refresh_tokens(db, user_id=user.id)


def _looks_like_bootstrap_user(
    user: User,
    *,
    user_role_ids: set[UUID],
    access_role_ids: set[UUID],
) -> bool:
    permissions = _page_permissions(user)
    if permissions.get(ADM_BOOTSTRAP_MANAGED_KEY):
        return True
    if permissions.get(ADM_INITIAL_PASSWORD_KEY) and user_role_ids.intersection(access_role_ids):
        return True
    return user.tenant_id is None and user.full_name == ADM_BOOTSTRAP_DISPLAY_NAME and bool(user_role_ids.intersection(access_role_ids))


def ensure_admin_bootstrap(db: Session) -> None:
    if not _adm_bootstrap_credentials_configured():
        return

    email = settings.adm_bootstrap_email.lower().strip()
    validate_password_strength(settings.adm_bootstrap_password)
    existing = db.scalar(select(User).where(User.email == email))
    roles = ensure_sales_roles(db)
    bootstrap_version = _bootstrap_version()
    access_role_ids = {roles[role_name].id for role_name in ADM_BOOTSTRAP_ACCESS_ROLE_NAMES}
    current_role_ids = _user_role_ids(db, existing.id) if existing else set()

    for candidate in db.execute(select(User).where(User.email != email)).scalars().all():
        candidate_role_ids = _user_role_ids(db, candidate.id)
        if _looks_like_bootstrap_user(candidate, user_role_ids=candidate_role_ids, access_role_ids=access_role_ids):
            _retire_bootstrap_access(db, user=candidate, access_role_ids=access_role_ids)

    if not existing:
        existing = User(
            tenant_id=None,
            unit_id=None,
            email=email,
            full_name=ADM_BOOTSTRAP_DISPLAY_NAME,
            phone=None,
            hashed_password=hash_password(settings.adm_bootstrap_password),
            is_active=True,
            page_permissions={
                ADM_INITIAL_PASSWORD_KEY: True,
                ADM_BOOTSTRAP_MANAGED_KEY: True,
                ADM_BOOTSTRAP_VERSION_KEY: bootstrap_version,
            },
        )
        db.add(existing)
        db.flush()
        current_role_ids = set()

    missing_role = False
    for role_name in ADM_BOOTSTRAP_GRANT_ROLE_NAMES:
        if roles[role_name].id not in current_role_ids:
            db.add(UserRole(tenant_id=None, user_id=existing.id, role_id=roles[role_name].id))
            missing_role = True

    permissions = _page_permissions(existing)
    should_revoke_tokens = (
        missing_role
        or not permissions.get(ADM_BOOTSTRAP_MANAGED_KEY)
        or str(permissions.get(ADM_BOOTSTRAP_VERSION_KEY) or "").strip() != bootstrap_version
        or not verify_password(settings.adm_bootstrap_password, existing.hashed_password)
    )
    permissions.pop(ADM_INITIAL_PASSWORD_KEY, None)
    permissions[ADM_BOOTSTRAP_MANAGED_KEY] = True
    permissions[ADM_BOOTSTRAP_VERSION_KEY] = bootstrap_version
    existing.page_permissions = permissions
    existing.hashed_password = hash_password(settings.adm_bootstrap_password)
    existing.is_active = True
    if should_revoke_tokens:
        _revoke_user_refresh_tokens(db, user_id=existing.id)

    db.add(existing)
    db.commit()


def require_sales_principal(principal) -> None:
    if not {"admin_platform", "sales_admin", "sales_viewer", ADM_AFFILIATE_ROLE_NAME}.intersection(set(principal.roles)):
        raise ApiError(status_code=403, code="SALES_FORBIDDEN", message="Acesso restrito ao modulo comercial")
    if principal.user.page_permissions.get("adm_initial_password"):
        raise ApiError(status_code=403, code="ADM_PASSWORD_CHANGE_REQUIRED", message="Troque a senha inicial para continuar")


def require_sales_write(principal) -> None:
    require_sales_principal(principal)
    if not {"admin_platform", "sales_admin"}.intersection(set(principal.roles)):
        raise ApiError(status_code=403, code="SALES_WRITE_FORBIDDEN", message="Permissao comercial insuficiente")


def require_adm_page_permission(principal, page_key: str, action: str = "view") -> None:
    require_sales_principal(principal)
    if action not in ADM_PERMISSION_ACTIONS:
        raise ApiError(status_code=400, code="ADM_PERMISSION_ACTION_INVALID", message="Acao de permissao invalida")
    if set(principal.roles).intersection(ADM_FULL_ACCESS_ROLE_NAMES):
        return
    if page_key == "adm_outreach_automation" and ADM_AFFILIATE_ROLE_NAME in set(principal.roles):
        raise ApiError(
            status_code=403,
            code="ADM_PAGE_FORBIDDEN",
            message="Afiliados nao acessam a automacao comercial interna",
            details={"page": page_key, "action": action},
        )
    permissions = normalize_adm_page_permissions(principal.user.page_permissions or {}, principal.roles)
    if permissions.get(page_key, {}).get(action):
        return
    raise ApiError(
        status_code=403,
        code="ADM_PAGE_FORBIDDEN",
        message="Voce nao tem permissao para acessar essa area do /adm",
        details={"page": page_key, "action": action},
    )


def build_admin_auth_payload(*, user: User, roles: list[str]) -> dict:
    access_token = create_access_token(subject=str(user.id), tenant_id=user.tenant_id, roles=roles)
    refresh_token = create_refresh_token(subject=str(user.id), tenant_id=user.tenant_id, roles=roles)
    adm_permissions = normalize_adm_page_permissions(user.page_permissions or {}, roles)
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "expires_in": settings.api_access_token_expire_minutes * 60,
        "force_password_change": bool(user.page_permissions.get(ADM_INITIAL_PASSWORD_KEY)),
        "roles": roles,
        "page_permissions": user.page_permissions or {},
        "adm_page_permissions": adm_permissions,
        "is_affiliate": ADM_AFFILIATE_ROLE_NAME in set(roles),
    }


def serialize_admin_session(*, user: User, roles: list[str]) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "full_name": user.full_name,
        "phone": user.phone,
        "roles": roles,
        "is_active": user.is_active,
        "force_password_change": bool(user.page_permissions.get(ADM_INITIAL_PASSWORD_KEY)),
        "page_permissions": user.page_permissions or {},
        "adm_page_permissions": normalize_adm_page_permissions(user.page_permissions or {}, roles),
        "is_affiliate": ADM_AFFILIATE_ROLE_NAME in set(roles),
        "last_login_at": user.last_login_at,
        "created_at": user.created_at,
        "updated_at": user.updated_at,
    }


def _get_affiliate_user(db: Session, user_id: UUID) -> User:
    user = db.get(User, user_id)
    if not user:
        raise ApiError(status_code=404, code="ADM_AFFILIATE_NOT_FOUND", message="Afiliado nao encontrado")
    roles = set(_user_role_names(db, user.id))
    if ADM_AFFILIATE_ROLE_NAME not in roles:
        raise ApiError(status_code=404, code="ADM_AFFILIATE_NOT_FOUND", message="Afiliado nao encontrado")
    return user


def serialize_adm_affiliate_user(db: Session, user: User) -> dict:
    roles = _user_role_names(db, user.id)
    return serialize_admin_session(user=user, roles=roles)


def list_adm_affiliates(db: Session) -> list[dict]:
    rows = (
        db.execute(
            select(User)
            .join(UserRole, UserRole.user_id == User.id)
            .join(Role, Role.id == UserRole.role_id)
            .where(Role.name == ADM_AFFILIATE_ROLE_NAME)
            .order_by(User.created_at.desc())
        )
        .scalars()
        .unique()
        .all()
    )
    return [serialize_adm_affiliate_user(db, user) for user in rows]


def register_adm_affiliate(
    db: Session,
    *,
    full_name: str,
    email: str,
    password: str,
    phone: str | None = None,
) -> dict:
    ensure_admin_bootstrap(db)
    normalized_email = email.lower().strip()
    if db.scalar(select(User.id).where(func.lower(User.email) == normalized_email)):
        raise ApiError(status_code=409, code="ADM_AFFILIATE_EMAIL_EXISTS", message="Ja existe um usuario com este e-mail")
    validate_password_strength(password)
    roles = ensure_sales_roles(db)
    permissions = _write_adm_page_permissions(
        {},
        ADM_DEFAULT_AFFILIATE_PERMISSIONS,
        mark_affiliate=True,
    )
    user = User(
        tenant_id=None,
        unit_id=None,
        email=normalized_email,
        full_name=full_name.strip(),
        phone=phone.strip() if phone else None,
        hashed_password=hash_password(password),
        is_active=True,
        page_permissions=permissions,
    )
    db.add(user)
    db.flush()
    db.add(UserRole(tenant_id=None, user_id=user.id, role_id=roles[ADM_AFFILIATE_ROLE_NAME].id))
    db.commit()
    db.refresh(user)
    role_names = _user_role_names(db, user.id)
    return build_admin_auth_payload(user=user, roles=role_names)


def update_adm_affiliate(
    db: Session,
    *,
    user_id: UUID,
    full_name: str | None = None,
    phone: str | None = None,
    is_active: bool | None = None,
    page_permissions: dict | None = None,
) -> dict:
    user = _get_affiliate_user(db, user_id)
    if full_name is not None:
        user.full_name = full_name.strip()
    if phone is not None:
        user.phone = phone.strip() or None
    if is_active is not None:
        user.is_active = is_active
        if not is_active:
            _revoke_user_refresh_tokens(db, user_id=user.id)
    if page_permissions is not None:
        user.page_permissions = _write_adm_page_permissions(
            user.page_permissions or {},
            page_permissions,
            mark_affiliate=True,
        )
    db.add(user)
    db.commit()
    db.refresh(user)
    return serialize_adm_affiliate_user(db, user)


def delete_adm_affiliate(db: Session, *, user_id: UUID) -> None:
    user = _get_affiliate_user(db, user_id)
    _revoke_user_refresh_tokens(db, user_id=user.id)
    db.execute(delete(UserRole).where(UserRole.user_id == user.id))
    db.delete(user)
    db.commit()


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


def _serialize_prospect_created_by_user(db: Session, user_id: UUID | None) -> dict[str, object]:
    if not user_id:
        return {
            "created_by_user_id": None,
            "created_by_user_name": None,
            "created_by_user_email": None,
            "created_by_user_is_affiliate": False,
        }
    user = db.get(User, user_id)
    if not user:
        return {
            "created_by_user_id": user_id,
            "created_by_user_name": None,
            "created_by_user_email": None,
            "created_by_user_is_affiliate": False,
        }
    return {
        "created_by_user_id": user.id,
        "created_by_user_name": user.full_name,
        "created_by_user_email": user.email,
        "created_by_user_is_affiliate": ADM_AFFILIATE_ROLE_NAME in set(_user_role_names(db, user.id)),
    }


def _serialize_prospect_affiliate_owner(db: Session, user_id: UUID | None) -> dict[str, object]:
    if not user_id:
        return {
            "affiliate_owner_user_id": None,
            "affiliate_owner_user_name": None,
            "affiliate_owner_user_email": None,
        }
    user = db.get(User, user_id)
    return {
        "affiliate_owner_user_id": user_id,
        "affiliate_owner_user_name": user.full_name if user else None,
        "affiliate_owner_user_email": user.email if user else None,
    }


def serialize_prospect(db: Session, prospect: ProspectAccount, *, include_children: bool = True) -> dict:
    units: list[dict] = []
    services: list[dict] = []
    demo_booking_slug = _resolve_demo_booking_slug(db, prospect=prospect)
    prospect_slug = demo_booking_slug or prospect.tenant_seed_key
    demo_booking_path = build_demo_booking_path(demo_booking_slug) if demo_booking_slug else None
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
        "slug": prospect_slug,
        "clinic_name": prospect.clinic_name,
        **_serialize_prospect_affiliate_owner(db, prospect.affiliate_owner_user_id),
        "affiliate_claimed_at": prospect.affiliate_claimed_at,
        **_serialize_prospect_created_by_user(db, prospect.created_by),
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
        "demo_booking_path": demo_booking_path,
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
    return ensure_sales_outreach_sender_tenant(db)


def resolve_sales_outreach_sender_tenant_slug() -> str:
    configured_slug = str(settings.sales_outreach_sender_tenant_slug or "").strip()
    return configured_slug or DEFAULT_SALES_OUTREACH_SENDER_TENANT_SLUG


def ensure_sales_outreach_sender_tenant(db: Session) -> Tenant:
    slug = resolve_sales_outreach_sender_tenant_slug()
    tenant = db.scalar(select(Tenant).where(Tenant.slug == slug))
    if tenant:
        if not tenant.is_active:
            tenant.is_active = True
            db.add(tenant)
            db.commit()
            db.refresh(tenant)
        return tenant

    tenant = Tenant(
        legal_name=DEFAULT_SALES_OUTREACH_SENDER_TENANT_LEGAL_NAME,
        trade_name=DEFAULT_SALES_OUTREACH_SENDER_TENANT_TRADE_NAME,
        slug=slug,
        timezone=settings.app_timezone or "America/Sao_Paulo",
        locale=settings.default_locale or "pt-BR",
        currency=settings.default_currency or "BRL",
        subscription_status="active",
        is_active=True,
    )
    db.add(tenant)
    try:
        db.commit()
    except IntegrityError:
        # Multiple admin requests can hit /admin/platform/whatsapp/* in parallel.
        # If another request created the technical tenant first, reuse it instead
        # of surfacing a 500 for duplicate slug creation.
        db.rollback()
        tenant = db.scalar(select(Tenant).where(Tenant.slug == slug))
        if tenant:
            if not tenant.is_active:
                tenant.is_active = True
                db.add(tenant)
                db.commit()
                db.refresh(tenant)
            return tenant
        raise
    db.refresh(tenant)
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


def _admin_internal_simulation_phone(prospect_id: UUID) -> str:
    return f"internal-sim-{str(prospect_id).replace('-', '')[:12]}"


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


def _value_looks_like_phone_label(value: str | None) -> bool:
    text = str(value or "").strip()
    normalized_phone = normalize_phone(text)
    if len(normalized_phone) < 10:
        return False
    leftover = re.sub(r"[\d\s()+-]", "", text)
    return not leftover


def _handoff_shared_contact_to_sales_outreach(
    db: Session,
    *,
    source_prospect: ProspectAccount,
    shared_contact_name: str,
    shared_contact_phone: str,
) -> dict:
    shared_contact_name = str(shared_contact_name or "").strip()
    shared_contact_phone = str(shared_contact_phone or "").strip()
    normalized_phone = normalize_phone(shared_contact_phone)
    if not shared_contact_name or not normalized_phone:
        return {
            "status": "skipped",
            "reason": "missing_shared_contact_details",
        }

    prospect = _find_public_site_prospect(
        db,
        clinic_name=shared_contact_name,
        phone=shared_contact_phone,
    )
    created = False
    shared_name_looks_better = not _value_looks_like_phone_label(shared_contact_name)
    if not prospect:
        from app.schemas.admin_sales import ProspectCreate

        prospect = create_prospect(
            db,
            ProspectCreate(
                clinic_name=shared_contact_name,
                owner_name=shared_contact_name,
                manager_name=shared_contact_name,
                phone=shared_contact_phone,
                whatsapp_phone=shared_contact_phone,
                lead_source="whatsapp_contact_shared",
                first_contact_channel="whatsapp",
                first_contact_at=_now(),
                notes=(
                    "Contato compartilhado a partir do WhatsApp comercial. "
                    f"Origem: {source_prospect.clinic_name}."
                ),
                tags=[
                    "whatsapp_contact_shared",
                    f"shared_from:{source_prospect.id}",
                ],
                proposal_snapshot={
                    "handoff": {
                        "source_prospect_id": str(source_prospect.id),
                        "source_clinic_name": source_prospect.clinic_name,
                        "shared_contact_name": shared_contact_name,
                        "shared_contact_phone": shared_contact_phone,
                    }
                },
            ),
            actor_id=None,
        )
        created = True
    elif shared_name_looks_better:
        updated = False
        if _value_looks_like_phone_label(prospect.clinic_name):
            prospect.clinic_name = shared_contact_name
            updated = True
        if not str(prospect.owner_name or "").strip() or _value_looks_like_phone_label(prospect.owner_name):
            prospect.owner_name = shared_contact_name
            updated = True
        if not str(prospect.manager_name or "").strip() or _value_looks_like_phone_label(prospect.manager_name):
            prospect.manager_name = shared_contact_name
            updated = True
        if updated:
            db.add(prospect)
            db.flush()

    outreach = _outreach_snapshot(prospect)
    if outreach.get("automation_active"):
        return {
            "status": "already_active",
            "created": created,
            "prospect_id": str(prospect.id),
        }

    started = start_sales_outreach_automation(
        db,
        prospect=prospect,
        actor_id=None,
        base_url=_default_sales_outreach_base_url(),
    )
    return {
        "status": "started",
        "created": created,
        "prospect_id": str(prospect.id),
        "conversation_id": str(started.get("conversation_id") or ""),
        "step": started.get("step"),
    }


def _update_outreach_snapshot(prospect: ProspectAccount, *, patch: dict) -> None:
    snapshot = dict(prospect.proposal_snapshot or {})
    outreach = dict(snapshot.get("outreach") or {}) if isinstance(snapshot.get("outreach"), dict) else {}
    outreach.update(jsonable_encoder(patch))
    snapshot["outreach"] = outreach
    prospect.proposal_snapshot = snapshot


def _normalize_demo_ai_settings(value: dict | None) -> dict[str, bool | int]:
    raw = value if isinstance(value, dict) else {}
    max_consecutive = int(raw.get("max_consecutive_auto_replies") or DEMO_AI_DEFAULT_SETTINGS["max_consecutive_auto_replies"])
    return {
        "enabled": bool(raw.get("enabled", DEMO_AI_DEFAULT_SETTINGS["enabled"])),
        "whatsapp_enabled": bool(raw.get("whatsapp_enabled", DEMO_AI_DEFAULT_SETTINGS["whatsapp_enabled"])),
        "max_consecutive_auto_replies": max(1, min(max_consecutive, 20)),
    }


def _demo_ai_settings(prospect: ProspectAccount) -> dict[str, bool | int]:
    snapshot = dict(prospect.proposal_snapshot or {})
    raw = snapshot.get("demo_ai")
    return _normalize_demo_ai_settings(raw if isinstance(raw, dict) else None)


def _normalize_demo_whatsapp_settings(value: dict | None) -> dict[str, str | None]:
    raw = value if isinstance(value, dict) else {}
    account_id = str(raw.get("account_id") or "").strip() or None
    return {"account_id": account_id}


def _demo_whatsapp_settings(prospect: ProspectAccount) -> dict[str, str | None]:
    snapshot = dict(prospect.proposal_snapshot or {})
    raw = snapshot.get("demo_whatsapp")
    return _normalize_demo_whatsapp_settings(raw if isinstance(raw, dict) else None)


def _normalize_demo_intake_settings(value: dict | None, *, prefer_webchat: bool = False) -> dict:
    raw = value if isinstance(value, dict) else {}
    raw_link_flow = raw.get("link_flow") if isinstance(raw.get("link_flow"), dict) else {}
    mode = str(raw.get("mode") or DEMO_INTAKE_DEFAULT_SETTINGS["mode"]).strip()
    default_cta_mode = "webchat" if prefer_webchat else DEMO_INTAKE_DEFAULT_SETTINGS["link_flow"]["cta_mode"]
    cta_mode = str(
        raw_link_flow.get("cta_mode")
        or default_cta_mode
    ).strip()

    payload = {
        "mode": mode,
        "link_flow": {
            "enabled": bool(raw_link_flow.get("enabled", mode in {"link_flow", "hybrid"})),
            "cta_mode": cta_mode,
            "headline": str(
                raw_link_flow.get("headline")
                or DEMO_INTAKE_DEFAULT_SETTINGS["link_flow"]["headline"]
            ),
            "trust_message": str(
                raw_link_flow.get("trust_message")
                or DEMO_INTAKE_DEFAULT_SETTINGS["link_flow"]["trust_message"]
            ),
            "button_label": str(
                raw_link_flow.get("button_label")
                or (
                    "Iniciar atendimento no chat"
                    if cta_mode == "webchat"
                    else DEMO_INTAKE_DEFAULT_SETTINGS["link_flow"]["button_label"]
                )
            ),
            "session_ttl_minutes": int(
                raw_link_flow.get("session_ttl_minutes")
                or DEMO_INTAKE_DEFAULT_SETTINGS["link_flow"]["session_ttl_minutes"]
            ),
        },
    }
    return validate_intake_config_payload(payload)


def _demo_should_default_to_webchat(db: Session, *, prospect: ProspectAccount) -> bool:
    snapshot = dict(prospect.proposal_snapshot or {})
    raw_demo_intake = snapshot.get("demo_intake")
    if isinstance(raw_demo_intake, dict) and raw_demo_intake:
        return False
    if not prospect.demo_tenant_id:
        return False
    return _resolve_demo_whatsapp_link(db, tenant_id=prospect.demo_tenant_id) is None


def _demo_intake_settings(db: Session, prospect: ProspectAccount) -> dict:
    snapshot = dict(prospect.proposal_snapshot or {})
    raw = snapshot.get("demo_intake")
    return _normalize_demo_intake_settings(
        raw if isinstance(raw, dict) else None,
        prefer_webchat=_demo_should_default_to_webchat(db, prospect=prospect),
    )


def _normalize_demo_background_settings(value: dict | None) -> dict[str, str | float]:
    raw = value if isinstance(value, dict) else {}
    image_url = str(raw.get("background_image_url") or "").strip() or DEMO_BACKGROUND_DEFAULT_IMAGE_URL
    try:
        opacity = float(raw.get("background_image_opacity", DEMO_BACKGROUND_DEFAULT_OPACITY))
    except (TypeError, ValueError):
        opacity = DEMO_BACKGROUND_DEFAULT_OPACITY
    return {
        "background_image_url": image_url,
        "background_image_opacity": max(0.0, min(opacity, 1.0)),
    }


def _demo_background_settings(prospect: ProspectAccount) -> dict[str, str | float]:
    snapshot = dict(prospect.proposal_snapshot or {})
    raw = snapshot.get("demo_branding")
    return _normalize_demo_background_settings(raw if isinstance(raw, dict) else None)


def ensure_demo_branding_ready(
    db: Session,
    *,
    tenant_id: UUID,
    prospect: ProspectAccount | None = None,
) -> dict:
    linked_prospect = prospect or db.scalar(
        select(ProspectAccount).where(ProspectAccount.demo_tenant_id == tenant_id).limit(1)
    )
    desired_background = (
        _demo_background_settings(linked_prospect)
        if linked_prospect
        else _normalize_demo_background_settings(None)
    )
    theme_item = db.scalar(select(Setting).where(Setting.tenant_id == tenant_id, Setting.key == "branding.theme"))
    current_theme = dict(theme_item.value) if theme_item and isinstance(theme_item.value, dict) else {}
    next_theme = {
        **DEMO_BRANDING_THEME_DEFAULTS,
        **current_theme,
        "demo_background_image_url": desired_background["background_image_url"],
        "demo_background_opacity": desired_background["background_image_opacity"],
    }
    _upsert_setting(db, tenant_id=tenant_id, key="branding.theme", value=next_theme)
    _upsert_setting(db, tenant_id=tenant_id, key="branding.logo_data_url", value=next_theme.get("logo_data_url"))
    return next_theme


def _current_demo_background_from_theme(value: dict | None) -> dict[str, str | float]:
    if not isinstance(value, dict):
        return _normalize_demo_background_settings(None)
    return _normalize_demo_background_settings(
        {
            "background_image_url": value.get("demo_background_image_url"),
            "background_image_opacity": value.get("demo_background_opacity"),
        }
    )


def ensure_demo_intake_config_ready(
    db: Session,
    *,
    tenant_id: UUID,
    prospect: ProspectAccount | None = None,
) -> dict:
    linked_prospect = prospect or db.scalar(
        select(ProspectAccount).where(ProspectAccount.demo_tenant_id == tenant_id).limit(1)
    )
    desired_config = _demo_intake_settings(db, linked_prospect) if linked_prospect else dict(DEMO_INTAKE_DEFAULT_SETTINGS)
    _upsert_setting(db, tenant_id=tenant_id, key="intake.config", value=desired_config)
    return desired_config


def _sanitize_demo_whatsapp_assignment(
    db: Session,
    *,
    snapshot: dict | None,
    current_prospect_id: UUID | None,
) -> dict:
    payload = dict(jsonable_encoder(snapshot or {}))
    demo_whatsapp = _normalize_demo_whatsapp_settings(
        payload.get("demo_whatsapp") if isinstance(payload.get("demo_whatsapp"), dict) else None
    )
    account_id = demo_whatsapp["account_id"]
    if not account_id:
        payload["demo_whatsapp"] = {"account_id": None}
        return payload

    try:
        account_uuid = UUID(account_id)
    except ValueError as exc:
        raise ApiError(
            status_code=400,
            code="DEMO_WHATSAPP_ACCOUNT_INVALID",
            message="Numero da demo invalido.",
        ) from exc

    account = db.get(WhatsAppAccount, account_uuid)
    sender_tenant = ensure_sales_outreach_sender_tenant(db)
    if (
        not account
        or not account.is_active
        or account.tenant_id != sender_tenant.id
        or str(account.phone_number_id or "").strip().startswith("demo_virtual_")
    ):
        raise ApiError(
            status_code=400,
            code="DEMO_WHATSAPP_ACCOUNT_INVALID",
            message="Selecione um numero real criado na area de WhatsApp do sistema.",
        )

    payload["demo_whatsapp"] = {"account_id": account_id}
    return payload


def _sanitize_demo_configuration_snapshot(
    db: Session,
    *,
    snapshot: dict | None,
    current_prospect_id: UUID | None,
) -> dict:
    payload = _sanitize_demo_whatsapp_assignment(
        db,
        snapshot=snapshot,
        current_prospect_id=current_prospect_id,
    )
    payload["demo_branding"] = _normalize_demo_background_settings(
        payload.get("demo_branding") if isinstance(payload.get("demo_branding"), dict) else None
    )
    return payload


def resolve_demo_assigned_platform_account(
    db: Session,
    *,
    prospect: ProspectAccount | None = None,
    tenant_id: UUID | None = None,
) -> WhatsAppAccount | None:
    linked_prospect = prospect
    if not linked_prospect and tenant_id:
        linked_prospect = db.scalar(
            select(ProspectAccount).where(ProspectAccount.demo_tenant_id == tenant_id).limit(1)
        )
    if not linked_prospect:
        return None

    account_id = _demo_whatsapp_settings(linked_prospect).get("account_id")
    if not account_id:
        return None

    try:
        account_uuid = UUID(account_id)
    except ValueError:
        return None

    sender_tenant = ensure_sales_outreach_sender_tenant(db)
    account = db.get(WhatsAppAccount, account_uuid)
    if (
        not account
        or not account.is_active
        or account.tenant_id != sender_tenant.id
        or str(account.phone_number_id or "").strip().startswith("demo_virtual_")
    ):
        return None
    return account


def _outreach_snapshot(prospect: ProspectAccount) -> dict:
    snapshot = dict(prospect.proposal_snapshot or {})
    outreach = snapshot.get("outreach")
    return dict(outreach) if isinstance(outreach, dict) else {}


def _no_site_outreach_snapshot(prospect: ProspectAccount) -> dict:
    snapshot = dict(prospect.proposal_snapshot or {})
    no_site_outreach = snapshot.get("no_site_outreach")
    return dict(no_site_outreach) if isinstance(no_site_outreach, dict) else {}


def _update_no_site_outreach_snapshot(prospect: ProspectAccount, *, patch: dict) -> None:
    snapshot = dict(prospect.proposal_snapshot or {})
    no_site_outreach = dict(snapshot.get("no_site_outreach") or {}) if isinstance(snapshot.get("no_site_outreach"), dict) else {}
    no_site_outreach.update(jsonable_encoder(patch))
    snapshot["no_site_outreach"] = no_site_outreach
    prospect.proposal_snapshot = snapshot


def _sales_outreach_skill_enabled() -> bool:
    return bool(getattr(settings, "sales_outreach_skill_enabled", True))


def _sales_outreach_llm_model() -> str | None:
    model = str(getattr(settings, "sales_outreach_llm_model", "") or "").strip()
    return model or None


def _run_sales_outreach_llm_task(
    db: Session,
    *,
    tenant_id: UUID | None,
    conversation_id: UUID | None,
    task: str,
    prompt: str,
) -> dict:
    return run_llm_task(
        db,
        tenant_id=tenant_id,
        conversation_id=conversation_id,
        task=task,
        prompt=prompt,
        model_override=_sales_outreach_llm_model(),
    )


def _sales_outreach_google_places_snapshot(prospect: ProspectAccount | None) -> dict:
    snapshot = prospect.proposal_snapshot if prospect and isinstance(prospect.proposal_snapshot, dict) else {}
    google_places = snapshot.get("google_places") if isinstance(snapshot.get("google_places"), dict) else {}
    return dict(google_places) if isinstance(google_places, dict) else {}


def _sales_outreach_source_is_google_places(prospect: ProspectAccount | None) -> bool:
    if not prospect:
        return False
    tags = {str(item).strip().lower() for item in (prospect.tags or []) if str(item).strip()}
    source = str(prospect.lead_source or "").strip().lower()
    snapshot = prospect.proposal_snapshot if isinstance(prospect.proposal_snapshot, dict) else {}
    return source == "google_places" or "google_places" in tags or snapshot.get("source") == "google_places"


def _sales_outreach_offer_lane(prospect: ProspectAccount | None) -> str:
    if not prospect:
        return "saas"
    website = str(prospect.website or "").strip()
    if _sales_outreach_source_is_google_places(prospect) and not website:
        return "website_first"
    return "saas"


def _sales_outreach_skill_context(prospect: ProspectAccount | None) -> str:
    if not _sales_outreach_skill_enabled():
        return ""

    google_places = _sales_outreach_google_places_snapshot(prospect)
    has_website = bool(str(prospect.website or "").strip()) if prospect else False
    offer_lane = _sales_outreach_offer_lane(prospect)
    category = ", ".join(str(item) for item in (google_places.get("types") or [])[:4]) if google_places else ""
    rating = google_places.get("rating")
    review_count = google_places.get("user_rating_count")
    location = ", ".join(
        item
        for item in [
            str(prospect.city or "").strip() if prospect else "",
            str(prospect.state or "").strip() if prospect else "",
        ]
        if item
    )

    return (
        "PLAYBOOK SEO/VENDAS LOCAL OBRIGATORIO: use a conversa para escolher o melhor momento de vender. "
        "Mantenha persona clara: ClinicFlux AI e contato comercial, nunca paciente ou recepcao da clinica. "
        "Responda perguntas diretas antes de vender. Se perguntarem como achou, diga que encontrou no Google. "
        "Se perguntarem o que pesquisou, responda com uma busca local plausivel de clinica odontologica na regiao. "
        "Use Google Places como contexto real: "
        f"has_website={has_website}; website={str(prospect.website or '').strip() if prospect else ''}; "
        f"offer_lane={offer_lane}; local={location or 'nao informado'}; categoria={category or 'nao informada'}; "
        f"rating={rating if rating is not None else 'nao informado'}; reviews={review_count if review_count is not None else 'nao informado'}. "
        "Se has_website=false, o primeiro angulo e site/SEO local com WhatsApp, mapa, servicos e prova de confianca. "
        "Se has_website=true, priorize ClinicFlux AI como camada de resposta, agenda e conversao do trafego que ja chega pelo Google/site. "
        "Nao venda site e SaaS juntos no primeiro pitch. Nao envie localhost/link de demo cedo demais. "
        "Nao repita pitch, nao ignore pergunta pendente, nao envie apos recusa, e pause em auto-resposta/fora de horario. "
        "Mensagem 90/100: curta, humana, consultiva, uma proxima acao clara."
    )


def _sales_outreach_initial_message_from_skill(prospect: ProspectAccount) -> str:
    if not _sales_outreach_source_is_google_places(prospect):
        return (
            "Oi, tudo bem? Aqui e o time comercial da ClinicFlux AI. "
            "Posso falar com quem cuida do WhatsApp e dos agendamentos da clinica?"
        )
    if _sales_outreach_offer_lane(prospect) == "website_first":
        return (
            "Oi, tudo bem?\n\n"
            "Notei que a clínica ainda não possui um site profissional.\n\n"
            "Eu já montei um modelo de site para a clínica e gostaria de mostrar ao responsável.\n\n"
            "Quem seria a pessoa ideal para eu encaminhar?"
        )
    return (
        "Oi, tudo bem? Encontrei a clinica no Google. Aqui e o time comercial da ClinicFlux AI. "
        "Posso falar com quem cuida do WhatsApp e dos agendamentos?"
    )


def _normalized_lookup_text(value: str | None) -> str:
    normalized = unicodedata.normalize("NFKD", str(value or ""))
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", ascii_text.lower()).strip()


def _pick_sales_outreach_initial_message(prospect: ProspectAccount, initial_messages: list[str] | None = None) -> str:
    if _sales_outreach_skill_enabled():
        return _sales_outreach_initial_message_from_skill(prospect)
    messages = initial_messages if initial_messages else list(SALES_OUTREACH_INITIAL_MESSAGES)
    if not messages:
        return "Oi! Tudo bem? Quem cuida dos agendamentos pelo WhatsApp da clínica?"
    seed = str(prospect.id or prospect.whatsapp_phone or prospect.clinic_name or "")
    index = sum(ord(char) for char in seed) % len(messages)
    return messages[index]


def _pick_sales_outreach_step_message(
    prospect: ProspectAccount,
    *,
    step: str,
    variations: list[str] | None = None,
) -> str:
    messages = [str(item).strip() for item in (variations or []) if str(item).strip()]
    if not messages:
        default_messages = SALES_OUTREACH_STEP_MESSAGE_DEFAULTS.get(step) or []
        messages = [str(item).strip() for item in default_messages if str(item).strip()]
    if not messages:
        return ""
    seed = f"{prospect.id or prospect.whatsapp_phone or prospect.clinic_name or ''}:{step}"
    index = sum(ord(char) for char in seed) % len(messages)
    return messages[index]


def classify_sales_outreach_reply(body: str | None, rules: dict[str, dict] | None = None) -> str:
    normalized = _normalized_lookup_text(body)
    # Automatic clinic replies and out-of-hours messages should pause the flow,
    # not trigger the next outreach step as if a person had answered.
    automatic_markers = (
        "nao estamos disponiveis no momento",
        "não estamos disponíveis no momento",
        "estamos ausentes",
        "no momento estamos ausentes",
        "ausentes no momento",
        "assim que possivel",
        "respondemos assim que possivel",
        "responderemos assim que possivel",
        "responderemos assim que possível",
        "retornaremos em breve",
        "em breve retornaremos",
        "fora do horario",
        "fora do horário",
        "fora do expediente",
        "atendimento automatico",
        "mensagem automatica",
        "resposta automatica",
        "recebemos sua mensagem",
    )
    if normalized and any(marker in normalized for marker in automatic_markers):
        return "automatica"

    # Common clinic welcome/autoreply messages should behave like reception handoff,
    # not as a generic question that triggers another explanation.
    if normalized and (
        ("bem-vindo" in normalized and "como podemos te ajudar" in normalized)
        or ("bem-vindo" in normalized and "horario de funcionamento" in normalized)
        or ("estamos felizes em recebe-lo" in normalized and "como podemos te ajudar" in normalized)
    ):
        return "recepcao"
    best_class = "duvida"
    best_priority = -1
    source_rules = rules if rules is not None else SALES_OUTREACH_REPLY_CLASSIFICATIONS
    for class_name, config in source_rules.items():
        keywords = config.get("keywords") or ()
        if any(keyword in normalized for keyword in keywords):
            priority = int(config.get("priority") or 0)
            if priority > best_priority:
                best_class = class_name
                best_priority = priority
    return best_class


def _default_sales_outreach_flow_config() -> dict:
    return {
        "initial_messages": list(SALES_OUTREACH_INITIAL_MESSAGES),
        "classification_rules": {
            class_name: {
                "priority": int(config.get("priority") or 0),
                "keywords": list(config.get("keywords") or ()),
            }
            for class_name, config in SALES_OUTREACH_REPLY_CLASSIFICATIONS.items()
        },
        "step_messages": {key: list(value) for key, value in SALES_OUTREACH_STEP_MESSAGE_DEFAULTS.items()},
        "class_to_step": dict(SALES_OUTREACH_CLASS_TO_STEP_DEFAULTS),
    }


def _normalize_sales_outreach_flow_config(raw_value: dict | None) -> dict:
    defaults = _default_sales_outreach_flow_config()
    payload = raw_value if isinstance(raw_value, dict) else {}

    raw_initial_messages = payload.get("initial_messages")
    initial_messages = [
        str(item).strip()
        for item in (raw_initial_messages if isinstance(raw_initial_messages, list) else defaults["initial_messages"])
        if str(item).strip()
    ] or list(defaults["initial_messages"])

    raw_rules = payload.get("classification_rules") if isinstance(payload.get("classification_rules"), dict) else {}
    classification_rules: dict[str, dict] = {}
    for class_name, default_rule in defaults["classification_rules"].items():
        candidate = raw_rules.get(class_name) if isinstance(raw_rules.get(class_name), dict) else {}
        keywords = [
            _normalized_lookup_text(item)
            for item in (candidate.get("keywords") if isinstance(candidate.get("keywords"), list) else default_rule["keywords"])
            if _normalized_lookup_text(item)
        ] or list(default_rule["keywords"])
        classification_rules[class_name] = {
            "priority": int(candidate.get("priority") or default_rule["priority"]),
            "keywords": keywords,
        }

    raw_step_messages = payload.get("step_messages") if isinstance(payload.get("step_messages"), dict) else {}
    step_messages: dict[str, list[str]] = {}
    for key, default_values in defaults["step_messages"].items():
        candidate_values = raw_step_messages.get(key)
        if isinstance(candidate_values, list):
            values = [str(item).strip() for item in candidate_values if str(item).strip()]
        elif isinstance(candidate_values, str):
            values = [candidate_values.strip()] if candidate_values.strip() else []
        else:
            values = []
        fallback_values = [str(item).strip() for item in default_values if str(item).strip()]
        merged_values = values or fallback_values
        step_messages[key] = (merged_values + fallback_values)[:5] if len(merged_values) < 5 else merged_values[:5]

    raw_class_to_step = payload.get("class_to_step") if isinstance(payload.get("class_to_step"), dict) else {}
    class_to_step = {
        key: str(raw_class_to_step.get(key) or default_value).strip() or default_value
        for key, default_value in defaults["class_to_step"].items()
    }

    return {
        "initial_messages": initial_messages,
        "classification_rules": classification_rules,
        "step_messages": step_messages,
        "class_to_step": class_to_step,
    }


def get_sales_outreach_flow_config(db: Session) -> dict:
    sender_tenant = ensure_sales_outreach_sender_tenant(db)
    item = db.scalar(select(Setting).where(Setting.tenant_id == sender_tenant.id, Setting.key == SALES_OUTREACH_FLOW_SETTING_KEY))
    raw_value = item.value if item and isinstance(item.value, dict) else None
    return _normalize_sales_outreach_flow_config(raw_value)


def save_sales_outreach_flow_config(db: Session, payload: dict) -> dict:
    sender_tenant = ensure_sales_outreach_sender_tenant(db)
    normalized = _normalize_sales_outreach_flow_config(payload)
    _upsert_setting(db, tenant_id=sender_tenant.id, key=SALES_OUTREACH_FLOW_SETTING_KEY, value=normalized)
    db.commit()
    return normalized


def _normalize_no_site_outreach_flow_config(raw_value: dict | None, *, strict: bool = False) -> dict:
    payload = raw_value if isinstance(raw_value, dict) else {}
    normalized: dict[str, list[str]] = {}
    for stage in NO_SITE_OUTREACH_STAGES:
        key = f"{stage}_messages"
        raw_messages = payload.get(key)
        if isinstance(raw_messages, list):
            messages = [str(item).strip() for item in raw_messages if str(item).strip()]
        else:
            messages = []
        if strict and len(messages) != 3:
            raise ApiError(
                status_code=422,
                code="NO_SITE_OUTREACH_MESSAGES_INVALID",
                message="Configure exatamente 3 mensagens preenchidas para cada etapa sem site.",
                details={"stage": stage, "expected": 3, "received": len(messages)},
            )
        defaults = [str(item).strip() for item in NO_SITE_OUTREACH_MESSAGE_DEFAULTS[stage] if str(item).strip()]
        normalized[key] = (messages or defaults)[:3]
        if len(normalized[key]) < 3:
            normalized[key] = (normalized[key] + defaults)[:3]
    return normalized


def get_no_site_outreach_flow_config(db: Session) -> dict:
    sender_tenant = ensure_sales_outreach_sender_tenant(db)
    item = db.scalar(select(Setting).where(Setting.tenant_id == sender_tenant.id, Setting.key == NO_SITE_OUTREACH_FLOW_SETTING_KEY))
    raw_value = item.value if item and isinstance(item.value, dict) else None
    return _normalize_no_site_outreach_flow_config(raw_value)


def save_no_site_outreach_flow_config(db: Session, payload: dict) -> dict:
    sender_tenant = ensure_sales_outreach_sender_tenant(db)
    normalized = _normalize_no_site_outreach_flow_config(payload, strict=True)
    _upsert_setting(db, tenant_id=sender_tenant.id, key=NO_SITE_OUTREACH_FLOW_SETTING_KEY, value=normalized)
    db.commit()
    return normalized


def _affiliate_first_messages_setting_key(user_id: UUID) -> str:
    return f"{AFFILIATE_FIRST_MESSAGES_SETTING_PREFIX}.{user_id}"


def _normalize_affiliate_contact_messages(raw_value: dict | None, *, strict: bool = False) -> dict:
    payload = raw_value if isinstance(raw_value, dict) else {}
    normalized: dict[str, list[str]] = {}
    for stage in ("first", "second", "third"):
        key = f"{stage}_messages"
        raw_messages = payload.get(key)
        if stage == "first" and not isinstance(raw_messages, list):
            raw_messages = payload.get("messages")
        messages = [str(item).strip() for item in raw_messages] if isinstance(raw_messages, list) else []
        if strict and (len(messages) != 5 or any(len(item) < 2 or len(item) > 5000 for item in messages)):
            raise ApiError(
                status_code=422,
                code="AFFILIATE_CONTACT_MESSAGES_INVALID",
                message="Configure exatamente 5 mensagens preenchidas, com ate 5000 caracteres, para cada contato.",
                details={"stage": stage, "expected": 5, "received": len(messages)},
            )
        if len(messages) != 5 or any(not item for item in messages):
            messages = list(AFFILIATE_CONTACT_MESSAGE_DEFAULTS[stage])
        normalized[key] = messages[:5]
    return normalized


def _normalize_affiliate_first_messages(raw_value: dict | None, *, strict: bool = False) -> dict:
    normalized = _normalize_affiliate_contact_messages(raw_value, strict=False)
    raw_messages = (raw_value or {}).get("messages") if isinstance(raw_value, dict) else None
    if strict:
        messages = [str(item).strip() for item in raw_messages] if isinstance(raw_messages, list) else []
        if len(messages) != 5 or any(len(item) < 2 or len(item) > 5000 for item in messages):
            raise ApiError(
                status_code=422,
                code="AFFILIATE_FIRST_MESSAGES_INVALID",
                message="Configure exatamente 5 mensagens preenchidas, com ate 5000 caracteres cada.",
            )
        normalized["first_messages"] = messages
    return {"messages": normalized["first_messages"]}


def get_affiliate_contact_message_config(db: Session, *, user_id: UUID) -> dict:
    sender_tenant = ensure_sales_outreach_sender_tenant(db)
    item = db.scalar(
        select(Setting).where(
            Setting.tenant_id == sender_tenant.id,
            Setting.key == _affiliate_first_messages_setting_key(user_id),
        )
    )
    raw_value = item.value if item and isinstance(item.value, dict) else None
    return _normalize_affiliate_contact_messages(raw_value)


def save_affiliate_contact_message_config(db: Session, *, user_id: UUID, payload: dict) -> dict:
    sender_tenant = ensure_sales_outreach_sender_tenant(db)
    normalized = _normalize_affiliate_contact_messages(payload, strict=True)
    _upsert_setting(
        db,
        tenant_id=sender_tenant.id,
        key=_affiliate_first_messages_setting_key(user_id),
        value=normalized,
    )
    db.commit()
    return normalized


def get_affiliate_first_message_config(db: Session, *, user_id: UUID) -> dict:
    config = get_affiliate_contact_message_config(db, user_id=user_id)
    return {"messages": config["first_messages"]}


def save_affiliate_first_message_config(db: Session, *, user_id: UUID, payload: dict) -> dict:
    normalized = _normalize_affiliate_first_messages(payload, strict=True)
    current = get_affiliate_contact_message_config(db, user_id=user_id)
    current["first_messages"] = normalized["messages"]
    saved = save_affiliate_contact_message_config(db, user_id=user_id, payload=current)
    return {"messages": saved["first_messages"]}


def _affiliate_available_prospect_query():
    return (
        select(ProspectAccount)
        .where(
            ProspectAccount.affiliate_owner_user_id.is_(None),
            ProspectAccount.first_contact_at.is_(None),
            ProspectAccount.do_not_contact.is_(False),
            ProspectAccount.status.in_(["novo", "pesquisado"]),
            or_(ProspectAccount.whatsapp_phone.is_not(None), ProspectAccount.phone.is_not(None)),
        )
        .order_by(ProspectAccount.score.desc(), ProspectAccount.created_at.asc())
    )


def get_next_affiliate_prospect(db: Session) -> ProspectAccount | None:
    candidates = db.execute(_affiliate_available_prospect_query().limit(100)).scalars().all()
    return next(
        (
            prospect
            for prospect in candidates
            if normalize_phone(prospect.whatsapp_phone or prospect.phone)
        ),
        None,
    )


def list_affiliate_claimed_prospects(
    db: Session,
    *,
    user_id: UUID,
    limit: int = 200,
    offset: int = 0,
) -> dict:
    filters = [ProspectAccount.affiliate_owner_user_id == user_id]
    rows = db.execute(
        select(ProspectAccount)
        .where(*filters)
        .order_by(ProspectAccount.affiliate_claimed_at.desc().nullslast(), ProspectAccount.updated_at.desc())
        .limit(limit)
        .offset(offset)
    ).scalars().all()
    total = db.scalar(select(func.count(ProspectAccount.id)).where(*filters)) or 0
    return {
        "data": [serialize_prospect(db, prospect) for prospect in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


def _sales_outreach_ai_is_enabled() -> bool:
    provider = str(settings.llm_provider or "").strip().lower()
    return bool(
        settings.sales_outreach_ai_review_enabled
        and str(settings.llm_api_key or "").strip()
        and provider in {"openai", "openai_chat", "openai_api"}
    )


def _sales_outreach_ai_min_confidence() -> float:
    try:
        return max(0.0, min(float(settings.sales_outreach_ai_min_confidence), 1.0))
    except (TypeError, ValueError):
        return 0.7


def _sales_outreach_send_gate_min_wait_minutes() -> int:
    try:
        return max(1, int(settings.sales_outreach_send_gate_min_wait_minutes or 120))
    except (TypeError, ValueError):
        return 120


def _sales_outreach_parse_llm_json(raw_output: str | None) -> dict | None:
    text = str(raw_output or "").strip()
    if not text:
        return None
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _sales_outreach_clean_ai_text(value: str | None) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def _sales_outreach_violates_sender_persona(value: str | None) -> bool:
    lookup = _normalized_lookup_text(value)
    if not lookup:
        return False
    forbidden_fragments = (
        "aqui e da recepcao",
        "sou da recepcao",
        "como posso ajudar no agendamento",
        "como podemos ajudar voce hoje",
        "este numero e utilizado para atendimento",
        "este numero e utilizado para agendamento",
        "este numero e utilizado para marcacao",
        "seja muito bem vindo",
        "para darmos continuidade ao seu atendimento",
        "por gentileza nos informe",
        "carteirinha do plano",
        "motivo da consulta",
        "nosso endereco",
    )
    return any(fragment in lookup for fragment in forbidden_fragments)


def _sales_outreach_safe_context_reply(
    prospect: ProspectAccount | None = None,
    *,
    recipient_name: str | None = None,
) -> str:
    sender_name = str(settings.sales_outreach_display_name or "Time ClinicFlux AI").strip() or "Time ClinicFlux AI"
    sender_intro = sender_name if "clinicflux" in _normalized_lookup_text(sender_name) else f"{sender_name} da ClinicFlux AI"
    addressee = _first_name(recipient_name or (prospect.owner_name if prospect else None) or (prospect.manager_name if prospect else None))
    greeting = f"Oi, {addressee}! " if addressee else "Oi! "
    if prospect and _sales_outreach_offer_lane(prospect) == "website_first":
        return (
            f"{greeting}Aqui e {sender_intro}. "
            "Meu contato e comercial, nao e agendamento de paciente. Encontrei a clinica no Google e vi uma oportunidade na presenca local: "
            "site com WhatsApp, mapa, servicos e prova de confianca para ajudar pacientes a escolherem e chamarem com menos duvida. "
            "Quem seria a pessoa responsavel por essa parte por ai?"
        )
    return (
        f"{greeting}Aqui e {sender_intro}. "
        "Meu contato e comercial, nao e agendamento de paciente: ajudamos clinicas a organizar atendimento, WhatsApp e agenda "
        "para responder mais rapido e perder menos oportunidades. "
        "Quem seria a pessoa responsavel por essa parte por ai?"
    )


def _sales_outreach_auto_reply_hold_text(prospect: ProspectAccount | None = None) -> str:
    if prospect:
        return _pick_sales_outreach_step_message(prospect, step="auto_reply_hold")
    return "Tudo bem, vou aguardar o proximo retorno por aqui."


def _sales_outreach_auto_reply_block_gate(*, facts: dict, reason: str | None = None) -> dict:
    return {
        "decision": "block",
        "confidence": 1.0,
        "reason": reason
        or "Resposta automatica ou fora de horario detectada; fluxo pausado para aguardar retorno humano.",
        "wait_minutes": None,
        "facts": facts,
    }


def _sales_outreach_format_message_lines(messages: list[Message]) -> list[str]:
    lines: list[str] = []
    for item in messages:
        body = _sales_outreach_clean_ai_text(item.body)[:500]
        if not body:
            continue
        speaker = "ClinicFlux AI" if item.direction == MessageDirection.OUTBOUND.value else "Clinica"
        lines.append(f"{speaker}: {body}")
    return lines


def _sales_outreach_actual_conversation_messages(
    db: Session,
    *,
    conversation_id: UUID,
) -> list[Message]:
    rows = db.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .where(
            or_(
                Message.direction == MessageDirection.INBOUND.value,
                Message.status.in_(
                    [
                        MessageStatus.SENT.value,
                        MessageStatus.DELIVERED.value,
                        MessageStatus.READ.value,
                        MessageStatus.RECEIVED.value,
                    ]
                ),
            )
        )
        .order_by(Message.created_at.asc(), Message.id.asc())
    ).scalars().all()
    return list(rows)


def _sales_outreach_complete_actual_transcript(
    db: Session,
    *,
    conversation_id: UUID,
) -> str:
    rows = _sales_outreach_actual_conversation_messages(db, conversation_id=conversation_id)
    return "\n".join(_sales_outreach_format_message_lines(rows))


def _sales_outreach_conversation_has_human_reply(db: Session, *, conversation_id: UUID) -> bool:
    for message in _sales_outreach_actual_conversation_messages(db, conversation_id=conversation_id):
        if message.direction != MessageDirection.INBOUND.value:
            continue
        body = _sales_outreach_clean_ai_text(message.body)
        if body and classify_sales_outreach_reply(body) != "automatica":
            return True
    return False


def _sales_outreach_message_time(message: Message | None) -> datetime | None:
    if not message:
        return None
    return message.sent_at or message.created_at


def _sales_outreach_send_gate_facts(
    *,
    messages: list[Message],
    now: datetime,
) -> dict:
    last_actual = messages[-1] if messages else None
    last_outbound = next((item for item in reversed(messages) if item.direction == MessageDirection.OUTBOUND.value), None)
    last_inbound = next((item for item in reversed(messages) if item.direction == MessageDirection.INBOUND.value), None)
    last_outbound_at = _sales_outreach_message_time(last_outbound)
    last_inbound_at = _sales_outreach_message_time(last_inbound)
    consecutive_outbound = 0
    for item in reversed(messages):
        if item.direction == MessageDirection.INBOUND.value:
            break
        if item.direction == MessageDirection.OUTBOUND.value:
            consecutive_outbound += 1

    minutes_since_last_outbound: int | None = None
    if last_outbound_at:
        elapsed = now - last_outbound_at
        minutes_since_last_outbound = max(0, int(elapsed.total_seconds() // 60))

    return {
        "total_actual_messages": len(messages),
        "last_actual_direction": str(last_actual.direction) if last_actual else None,
        "last_outbound_at": last_outbound_at.isoformat() if last_outbound_at else None,
        "last_inbound_at": last_inbound_at.isoformat() if last_inbound_at else None,
        "minutes_since_last_outbound": minutes_since_last_outbound,
        "consecutive_outbound_without_reply": consecutive_outbound,
    }


def _sales_outreach_outbox_metadata(payload: dict | None) -> dict:
    if not isinstance(payload, dict):
        return {}
    metadata = payload.get("metadata")
    return metadata if isinstance(metadata, dict) else {}


def _sales_outreach_uuid_from_value(value: object) -> UUID | None:
    try:
        return UUID(str(value))
    except (TypeError, ValueError):
        return None


def review_sales_outreach_outbox_send_gate(
    db: Session,
    *,
    outbox: OutboxMessage,
    now: datetime | None = None,
) -> dict:
    if not settings.sales_outreach_send_gate_enabled:
        return {"decision": "send", "confidence": 1.0, "reason": "send_gate_disabled"}

    payload = outbox.payload if isinstance(outbox.payload, dict) else {}
    metadata = _sales_outreach_outbox_metadata(payload)
    if str(metadata.get("source") or "").strip() != "sales_outreach":
        return {"decision": "send", "confidence": 1.0, "reason": "not_sales_outreach"}
    candidate_step = str(metadata.get("step") or "").strip()
    prospect = None
    prospect_id = _sales_outreach_uuid_from_value(metadata.get("prospect_account_id"))
    if prospect_id:
        prospect = db.get(ProspectAccount, prospect_id)

    conversation_id = _sales_outreach_uuid_from_value(payload.get("conversation_id"))
    if not conversation_id:
        return {
            "decision": "block",
            "confidence": 1.0,
            "reason": "Envio bloqueado: conversa ausente, impossivel revisar o contexto completo antes do envio.",
        }

    conversation = db.get(Conversation, conversation_id)
    if not conversation:
        return {
            "decision": "block",
            "confidence": 1.0,
            "reason": "Envio bloqueado: conversa nao encontrada, impossivel revisar o contexto completo antes do envio.",
        }
    if _latest_sales_outreach_inbound_is_opt_out(db, conversation_id=conversation.id):
        return {
            "decision": "block",
            "confidence": 1.0,
            "reason": "Envio bloqueado: a ultima resposta da clinica recusou contato comercial.",
        }

    effective_now = now or _now()
    candidate_message = _sales_outreach_clean_ai_text(payload.get("body"))[:1200]
    linked_outbound_message_id = _sales_outreach_uuid_from_value(metadata.get("outbound_message_id"))
    actual_messages = [
        message
        for message in _sales_outreach_actual_conversation_messages(db, conversation_id=conversation.id)
        if not linked_outbound_message_id or message.id != linked_outbound_message_id
    ]
    transcript = "\n".join(_sales_outreach_format_message_lines(actual_messages)) or "Sem mensagens enviadas ou recebidas ainda."
    facts = _sales_outreach_send_gate_facts(messages=actual_messages, now=effective_now)
    min_wait_minutes = _sales_outreach_send_gate_min_wait_minutes()
    latest_inbound = next((item for item in reversed(actual_messages) if item.direction == MessageDirection.INBOUND.value), None)
    latest_inbound_body = _sales_outreach_clean_ai_text(latest_inbound.body if latest_inbound else "")
    latest_inbound_classification = classify_sales_outreach_reply(latest_inbound_body) if latest_inbound_body else ""
    no_site_stage = str(metadata.get("no_site_outreach_stage") or "").strip()

    if facts.get("last_actual_direction") == MessageDirection.INBOUND.value and (
        candidate_step == "auto_reply_hold" or latest_inbound_classification == "automatica"
    ):
        if not (no_site_stage == "second" and latest_inbound_classification == "automatica"):
            return _sales_outreach_auto_reply_block_gate(
                facts=facts,
                reason="Clinica retornou com mensagem automatica/fora de horario; nao enviar nova mensagem ate retorno humano.",
            )

    if _sales_outreach_violates_sender_persona(candidate_message):
        repaired_message = (
            _pick_sales_outreach_initial_message(prospect)
            if prospect and candidate_step == "reception_intro" and facts.get("last_actual_direction") != MessageDirection.INBOUND.value
            else _sales_outreach_safe_context_reply(prospect)
        )
        return {
            "decision": "send",
            "confidence": 1.0,
            "reason": "Mensagem candidata corrigida para manter a persona comercial da ClinicFlux AI.",
            "wait_minutes": None,
            "final_message": repaired_message,
            "facts": facts,
        }

    normalized_candidate = _normalized_lookup_text(candidate_message)
    for item in actual_messages:
        if item.direction == MessageDirection.OUTBOUND.value and _normalized_lookup_text(item.body) == normalized_candidate:
            return {
                "decision": "block",
                "confidence": 1.0,
                "reason": "Mensagem candidata repete exatamente uma mensagem ja enviada nessa conversa.",
                "wait_minutes": None,
                "facts": facts,
            }

    if no_site_stage:
        outbound_count = len([item for item in actual_messages if item.direction == MessageDirection.OUTBOUND.value])
        human_reply_received = (
            _sales_outreach_conversation_has_human_reply(db, conversation_id=conversation.id)
            if conversation.id
            else False
        )
        if no_site_stage not in NO_SITE_OUTREACH_STAGES:
            return {
                "decision": "block",
                "confidence": 1.0,
                "reason": "Envio bloqueado: etapa sem-site invalida.",
                "wait_minutes": None,
                "facts": facts,
            }
        if not prospect:
            return {
                "decision": "block",
                "confidence": 1.0,
                "reason": "Envio bloqueado: prospect sem-site nao encontrado.",
                "wait_minutes": None,
                "facts": facts,
            }
        if str(prospect.website or "").strip():
            return {
                "decision": "block",
                "confidence": 1.0,
                "reason": "Envio bloqueado: a clinica ja possui site cadastrado.",
                "wait_minutes": None,
                "facts": facts,
            }
        if no_site_stage == "first" and outbound_count > 0:
            return {
                "decision": "block",
                "confidence": 1.0,
                "reason": "Envio bloqueado: a primeira mensagem sem-site ja passou nesta conversa.",
                "wait_minutes": None,
                "facts": facts,
            }
        if no_site_stage == "second" and outbound_count != 1:
            return {
                "decision": "block",
                "confidence": 1.0,
                "reason": "Envio bloqueado: a segunda mensagem sem-site exige exatamente uma mensagem anterior.",
                "wait_minutes": None,
                "facts": facts,
            }
        if no_site_stage == "third":
            if outbound_count < 2:
                return {
                    "decision": "block",
                    "confidence": 1.0,
                    "reason": "Envio bloqueado: a terceira mensagem sem-site exige as duas primeiras etapas.",
                    "wait_minutes": None,
                    "facts": facts,
                }
            if not human_reply_received:
                return {
                    "decision": "block",
                    "confidence": 1.0,
                    "reason": "Envio bloqueado: terceira mensagem fria sem resposta humana nao e permitida.",
                    "wait_minutes": None,
                    "facts": facts,
                }
        minutes_since_last_outbound = facts.get("minutes_since_last_outbound")
        if no_site_stage == "first" and outbound_count == 0:
            return {
                "decision": "send",
                "confidence": 1.0,
                "reason": "Primeira mensagem sem-site liberada.",
                "wait_minutes": None,
                "facts": facts,
            }
        if no_site_stage == "second" and not human_reply_received:
            if facts.get("last_actual_direction") == MessageDirection.OUTBOUND.value and isinstance(minutes_since_last_outbound, int):
                min_wait_minutes = _sales_outreach_send_gate_min_wait_minutes()
                if minutes_since_last_outbound < min_wait_minutes:
                    return {
                        "decision": "wait",
                        "confidence": 1.0,
                        "reason": f"Aguardar pelo menos {min_wait_minutes} minutos antes da segunda mensagem sem-site.",
                        "wait_minutes": max(1, min_wait_minutes - minutes_since_last_outbound),
                        "facts": facts,
                    }
            return {
                "decision": "send",
                "confidence": 1.0,
                "reason": "Segunda mensagem sem-site liberada dentro do limite de cold outreach.",
                "wait_minutes": None,
                "facts": facts,
            }
        if human_reply_received:
            return {
                "decision": "send",
                "confidence": 1.0,
                "reason": "Mensagem sem-site liberada porque existe resposta humana registrada.",
                "wait_minutes": None,
                "facts": facts,
            }

    minutes_since_last_outbound = facts.get("minutes_since_last_outbound")
    if (
        facts.get("last_actual_direction") == MessageDirection.OUTBOUND.value
        and isinstance(minutes_since_last_outbound, int)
        and minutes_since_last_outbound < min_wait_minutes
    ):
        wait_minutes = max(1, min_wait_minutes - minutes_since_last_outbound)
        return {
            "decision": "wait",
            "confidence": 1.0,
            "reason": f"A clinica ainda nao respondeu a ultima mensagem. Aguardar pelo menos {min_wait_minutes} minutos entre follow-ups.",
            "wait_minutes": wait_minutes,
            "facts": facts,
        }

    if facts.get("last_actual_direction") == MessageDirection.INBOUND.value:
        if candidate_step == "auto_reply_hold" or latest_inbound_classification == "automatica":
            if not (no_site_stage == "second" and latest_inbound_classification == "automatica"):
                return _sales_outreach_auto_reply_block_gate(
                    facts=facts,
                    reason="Clinica retornou com mensagem automatica/fora de horario; nao enviar nova mensagem ate retorno humano.",
                )
        if candidate_step == "reception_intro" and facts.get("total_actual_messages", 0) > 1:
            return {
                "decision": "send",
                "confidence": 1.0,
                "reason": "Clinica respondeu; trocando pergunta inicial por resposta comercial contextual.",
                "wait_minutes": None,
                "final_message": _sales_outreach_safe_context_reply(prospect),
                "facts": facts,
            }

    if not _sales_outreach_ai_is_enabled():
        if not actual_messages:
            return {
                "decision": "send",
                "confidence": 1.0,
                "reason": "Primeira mensagem comercial sem historico previo; envio liberado sem IA.",
                "wait_minutes": None,
                "facts": facts,
            }
        if facts.get("last_actual_direction") == MessageDirection.INBOUND.value:
            if latest_inbound_classification == "automatica":
                return _sales_outreach_auto_reply_block_gate(facts=facts)
            return {
                "decision": "send",
                "confidence": 1.0,
                "reason": "IA indisponivel; resposta fallback enviada para nao deixar a clinica sem retorno.",
                "wait_minutes": None,
                "final_message": _sales_outreach_safe_context_reply(prospect),
                "facts": facts,
            }
        return {
            "decision": "wait",
            "confidence": 1.0,
            "reason": "IA indisponivel; aguardando revisao antes de enviar mensagem comercial.",
            "wait_minutes": 15,
            "facts": facts,
        }

    prompt = (
        "Voce e um diretor comercial revisando uma mensagem B2B antes de envio por WhatsApp. "
        f"{_sales_outreach_skill_context(prospect)} "
        "Decida se a ClinicFlux AI deve enviar a mensagem candidata agora, esperar, ou bloquear. "
        f"Regras obrigatorias: se a clinica ainda nao respondeu a ultima mensagem enviada e passaram menos de {min_wait_minutes} minutos, decida wait; "
        "se a mensagem for repetitiva, invasiva ou ignorar uma pergunta pendente, decida wait ou block; "
        "se enviar, a resposta deve ser natural, curta, profissional e coerente com a conversa inteira. "
        "Retorne JSON com os campos decision, confidence, reason, wait_minutes, final_message. "
        "decision deve ser um destes valores: send, wait, block. "
        f"Fatos calculados: {json.dumps(facts, ensure_ascii=False)}. "
        f"Historico completo real da conversa:\n{transcript}\n"
        f"Mensagem candidata: {candidate_message}"
    )
    try:
        result = _run_sales_outreach_llm_task(
            db,
            tenant_id=conversation.tenant_id,
            conversation_id=conversation.id,
            task="sales_outreach_send_gate",
            prompt=prompt,
        )
        payload_json = _sales_outreach_parse_llm_json(result.get("output"))
    except Exception:
        payload_json = None

    if not payload_json:
        if not actual_messages:
            return {
                "decision": "send",
                "confidence": 1.0,
                "reason": "Primeira mensagem comercial sem historico previo; envio liberado com fallback local do gate.",
                "wait_minutes": None,
                "facts": facts,
            }
        if facts.get("last_actual_direction") == MessageDirection.INBOUND.value:
            if latest_inbound_classification == "automatica":
                return _sales_outreach_auto_reply_block_gate(facts=facts)
            return {
                "decision": "send",
                "confidence": 1.0,
                "reason": "IA do gate indisponivel; resposta fallback enviada para nao deixar a clinica sem retorno.",
                "wait_minutes": None,
                "final_message": _sales_outreach_safe_context_reply(prospect),
                "facts": facts,
            }
        return {
            "decision": "wait",
            "confidence": 1.0,
            "reason": "IA do gate indisponivel; aguardando nova tentativa antes de enviar.",
            "wait_minutes": 15,
            "facts": facts,
        }

    decision = str(payload_json.get("decision") or "").strip().lower()
    if decision not in SALES_OUTREACH_SEND_GATE_DECISIONS:
        decision = "wait"

    try:
        confidence = max(0.0, min(float(payload_json.get("confidence")), 1.0))
    except (TypeError, ValueError):
        confidence = 0.0

    if confidence < _sales_outreach_ai_min_confidence():
        decision = "wait"

    try:
        wait_minutes = int(payload_json.get("wait_minutes") or 0)
    except (TypeError, ValueError):
        wait_minutes = 0
    if decision == "wait":
        wait_minutes = max(5, wait_minutes or min_wait_minutes)

    final_message = str(payload_json.get("final_message") or "").strip()
    if decision == "send" and _sales_outreach_violates_sender_persona(final_message):
        final_message = _sales_outreach_safe_context_reply(prospect)
    if decision == "wait" and facts.get("last_actual_direction") == MessageDirection.INBOUND.value:
        if latest_inbound_classification == "automatica":
            return _sales_outreach_auto_reply_block_gate(facts=facts)
        decision = "send"
        wait_minutes = 0
        final_message = final_message if final_message and not _sales_outreach_violates_sender_persona(final_message) else _sales_outreach_safe_context_reply(prospect)
        payload_json["reason"] = "Clinica respondeu; fallback comercial liberado para nao deixar resposta humana sem retorno."
    return {
        "decision": decision,
        "confidence": confidence,
        "reason": _sales_outreach_clean_ai_text(payload_json.get("reason"))[:500] or "Decisao do gate comercial.",
        "wait_minutes": wait_minutes if decision == "wait" else None,
        "final_message": final_message if decision == "send" else None,
        "facts": facts,
    }


def _sales_outreach_live_direction(value: object) -> str | None:
    normalized = str(value or "").strip().lower()
    if normalized in {"out", "outbound", "sent", "me", "clinicflux", "clinicflux ai"}:
        return MessageDirection.OUTBOUND.value
    if normalized in {"in", "inbound", "received", "clinic", "clinica", "lead", "patient"}:
        return MessageDirection.INBOUND.value
    return None


def _sales_outreach_parse_iso_datetime(value: object) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _sales_outreach_minutes_since_visible_time(visible_time: object, captured_at: datetime) -> int | None:
    text = str(visible_time or "").strip()
    match = re.search(r"\b(\d{1,2}):(\d{2})\b", text)
    if not match:
        return None
    hour = int(match.group(1))
    minute = int(match.group(2))
    if hour > 23 or minute > 59:
        return None
    base = captured_at.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if base > captured_at + timedelta(minutes=5):
        base -= timedelta(days=1)
    return max(0, int((captured_at - base).total_seconds() // 60))


def _sales_outreach_normalize_live_messages(live_messages: list[dict] | None) -> list[dict]:
    normalized_messages: list[dict] = []
    for item in live_messages or []:
        if not isinstance(item, dict):
            continue
        direction = _sales_outreach_live_direction(item.get("direction"))
        body = _sales_outreach_clean_ai_text(item.get("body") or item.get("message") or item.get("text"))[:1200]
        if not direction or not body:
            continue
        normalized_messages.append(
            {
                "direction": direction,
                "body": body,
                "visible_time": str(item.get("visible_time") or "").strip(),
                "timestamp": str(item.get("timestamp") or "").strip(),
            }
        )
    return normalized_messages[-120:]


def _sales_outreach_live_transcript(live_messages: list[dict]) -> str:
    lines: list[str] = []
    for item in live_messages:
        speaker = "ClinicFlux AI" if item["direction"] == MessageDirection.OUTBOUND.value else "Clinica"
        visible_time = str(item.get("visible_time") or "").strip()
        prefix = f"[{visible_time}] " if visible_time else ""
        lines.append(f"{prefix}{speaker}: {item['body']}")
    return "\n".join(lines)


def _sales_outreach_live_facts(*, live_messages: list[dict], captured_at: datetime) -> dict:
    last_actual = live_messages[-1] if live_messages else None
    last_outbound = next((item for item in reversed(live_messages) if item["direction"] == MessageDirection.OUTBOUND.value), None)
    last_inbound = next((item for item in reversed(live_messages) if item["direction"] == MessageDirection.INBOUND.value), None)

    consecutive_outbound = 0
    for item in reversed(live_messages):
        if item["direction"] == MessageDirection.INBOUND.value:
            break
        if item["direction"] == MessageDirection.OUTBOUND.value:
            consecutive_outbound += 1

    minutes_since_last_outbound = None
    if last_outbound:
        minutes_since_last_outbound = _sales_outreach_minutes_since_visible_time(last_outbound.get("visible_time"), captured_at)

    return {
        "source": "whatsapp_web_live_dom",
        "total_live_messages": len(live_messages),
        "last_live_direction": last_actual["direction"] if last_actual else None,
        "last_outbound_visible_time": last_outbound.get("visible_time") if last_outbound else None,
        "last_inbound_visible_time": last_inbound.get("visible_time") if last_inbound else None,
        "minutes_since_last_outbound": minutes_since_last_outbound,
        "consecutive_outbound_without_reply": consecutive_outbound,
    }


def review_sales_outreach_live_whatsapp_send_gate(
    db: Session,
    *,
    conversation: Conversation,
    candidate_message: str,
    live_messages: list[dict] | None,
    captured_at: datetime | None = None,
    candidate_step: str | None = None,
) -> dict:
    min_wait_minutes = _sales_outreach_send_gate_min_wait_minutes()
    effective_now = captured_at or _now()
    normalized_live_messages = _sales_outreach_normalize_live_messages(live_messages)
    facts = _sales_outreach_live_facts(live_messages=normalized_live_messages, captured_at=effective_now)
    normalized_candidate = _normalized_lookup_text(candidate_message)
    resolved_step = str(candidate_step or "").strip()
    prospect = None
    prospect_id = _prospect_id_from_conversation_tags(conversation.tags or [])
    if prospect_id:
        prospect = db.get(ProspectAccount, prospect_id)

    db_messages = db.execute(
        select(Message)
        .where(Message.conversation_id == conversation.id)
        .order_by(Message.created_at.asc(), Message.id.asc())
    ).scalars().all()
    db_inbound_count = sum(1 for item in db_messages if item.direction == MessageDirection.INBOUND.value)
    db_sent_outbound_count = sum(
        1
        for item in db_messages
        if item.direction == MessageDirection.OUTBOUND.value and item.status == MessageStatus.SENT.value
    )
    facts["db_inbound_count"] = db_inbound_count
    facts["db_sent_outbound_count"] = db_sent_outbound_count
    latest_live_inbound = next(
        (item for item in reversed(normalized_live_messages) if item["direction"] == MessageDirection.INBOUND.value),
        None,
    )
    latest_live_inbound_body = str((latest_live_inbound or {}).get("body") or "").strip()
    latest_live_inbound_classification = classify_sales_outreach_reply(latest_live_inbound_body) if latest_live_inbound_body else ""

    if _latest_sales_outreach_inbound_is_opt_out(db, conversation_id=conversation.id) or _looks_like_outreach_opt_out(latest_live_inbound_body):
        return {
            "decision": "block",
            "confidence": 1.0,
            "reason": "Envio bloqueado: a ultima resposta da clinica recusou contato comercial.",
            "wait_minutes": None,
            "facts": facts,
        }

    if facts.get("last_live_direction") == MessageDirection.INBOUND.value and (
        latest_live_inbound_classification == "automatica" or resolved_step == "auto_reply_hold"
    ):
        return _sales_outreach_auto_reply_block_gate(
            facts=facts,
            reason="WhatsApp Web mostra resposta automatica/fora de horario; fluxo pausado ate uma mensagem humana.",
        )

    if _sales_outreach_violates_sender_persona(candidate_message):
        repaired_message = (
            _pick_sales_outreach_initial_message(prospect)
            if prospect and resolved_step == "reception_intro" and facts.get("last_live_direction") != MessageDirection.INBOUND.value
            else _sales_outreach_safe_context_reply(prospect)
        )
        return {
            "decision": "send",
            "confidence": 1.0,
            "reason": "Mensagem candidata corrigida para manter a persona comercial da ClinicFlux AI.",
            "wait_minutes": None,
            "final_message": repaired_message,
            "facts": facts,
        }

    if not normalized_live_messages:
        if db_inbound_count == 0 and db_sent_outbound_count == 0:
            return {
                "decision": "send",
                "confidence": 1.0,
                "reason": "Conversa nova no WhatsApp Web sem historico visivel; primeiro contato liberado.",
                "wait_minutes": None,
                "final_message": _sales_outreach_clean_ai_text(candidate_message)[:1200],
                "facts": facts,
            }
        return {
            "decision": "wait",
            "confidence": 1.0,
            "reason": "Nao foi possivel ler o historico live do WhatsApp Web antes do envio.",
            "wait_minutes": 15,
            "facts": facts,
        }

    if (
        facts.get("last_live_direction") == MessageDirection.INBOUND.value
        and resolved_step == "reception_intro"
        and db_sent_outbound_count > 0
        and db_inbound_count > 0
    ):
        return {
            "decision": "send",
            "confidence": 1.0,
            "reason": "Clinica respondeu; trocando a pergunta inicial repetida por uma resposta comercial contextual.",
            "wait_minutes": None,
            "final_message": _sales_outreach_safe_context_reply(prospect),
            "facts": facts,
        }

    for item in normalized_live_messages:
        if item["direction"] == MessageDirection.OUTBOUND.value and _normalized_lookup_text(item["body"]) == normalized_candidate:
            return {
                "decision": "block",
                "confidence": 1.0,
                "reason": "A mensagem candidata ja aparece no WhatsApp Web ou repete exatamente uma mensagem enviada.",
                "wait_minutes": None,
                "facts": facts,
            }

    consecutive_outbound = int(facts.get("consecutive_outbound_without_reply") or 0)
    minutes_since_last_outbound = facts.get("minutes_since_last_outbound")
    if consecutive_outbound >= 2:
        return {
            "decision": "wait",
            "confidence": 1.0,
            "reason": "O WhatsApp Web mostra duas ou mais mensagens da ClinicFlux AI sem resposta da clinica. Aguardar resposta antes de continuar.",
            "wait_minutes": min_wait_minutes,
            "facts": facts,
        }

    if facts.get("last_live_direction") == MessageDirection.OUTBOUND.value:
        if not isinstance(minutes_since_last_outbound, int) or minutes_since_last_outbound < min_wait_minutes:
            wait_minutes = min_wait_minutes
            if isinstance(minutes_since_last_outbound, int):
                wait_minutes = max(1, min_wait_minutes - minutes_since_last_outbound)
            return {
                "decision": "wait",
                "confidence": 1.0,
                "reason": f"O WhatsApp Web mostra que a ultima mensagem ainda e da ClinicFlux AI. Aguardar resposta da clinica ou pelo menos {min_wait_minutes} minutos.",
                "wait_minutes": wait_minutes,
                "facts": facts,
            }

    if not _sales_outreach_ai_is_enabled():
        if facts.get("last_live_direction") == MessageDirection.INBOUND.value:
            return {
                "decision": "send",
                "confidence": 1.0,
                "reason": "IA indisponivel; resposta fallback enviada para nao deixar a clinica sem retorno.",
                "wait_minutes": None,
                "final_message": _sales_outreach_safe_context_reply(prospect),
                "facts": facts,
            }
        return {
            "decision": "wait",
            "confidence": 1.0,
            "reason": "IA indisponivel; aguardando revisao live antes de enviar.",
            "wait_minutes": 15,
            "facts": facts,
        }

    transcript = _sales_outreach_live_transcript(normalized_live_messages)
    prompt = (
        "Voce e um diretor comercial revisando a conversa REAL carregada no WhatsApp Web antes do envio. "
        f"{_sales_outreach_skill_context(prospect)} "
        "Decida se a ClinicFlux AI deve enviar a mensagem candidata agora, esperar, ou bloquear. "
        "Regra obrigatoria: se a ultima mensagem real do WhatsApp for da ClinicFlux AI e a clinica nao respondeu depois, decida wait; "
        "se houver duas ou mais mensagens da ClinicFlux AI seguidas sem resposta, decida wait; "
        "se a mensagem ignorar pergunta pendente, parecer insistente ou repetir algo, decida wait ou block. "
        "Se enviar, ajuste para uma resposta natural, curta, humana, profissional e coerente com o historico completo. "
        "Retorne JSON com os campos decision, confidence, reason, wait_minutes, final_message. "
        "decision deve ser um destes valores: send, wait, block. "
        f"Fatos calculados do WhatsApp Web: {json.dumps(facts, ensure_ascii=False)}. "
        f"Historico live do WhatsApp Web:\n{transcript}\n"
        f"Mensagem candidata: {_sales_outreach_clean_ai_text(candidate_message)[:1200]}"
    )
    try:
        result = _run_sales_outreach_llm_task(
            db,
            tenant_id=conversation.tenant_id,
            conversation_id=conversation.id,
            task="sales_outreach_live_send_gate",
            prompt=prompt,
        )
        payload_json = _sales_outreach_parse_llm_json(result.get("output"))
    except Exception:
        payload_json = None

    if not payload_json:
        if facts.get("last_live_direction") == MessageDirection.INBOUND.value:
            return {
                "decision": "send",
                "confidence": 1.0,
                "reason": "IA do gate live indisponivel; resposta fallback enviada para nao deixar a clinica sem retorno.",
                "wait_minutes": None,
                "final_message": _sales_outreach_safe_context_reply(prospect),
                "facts": facts,
            }
        return {
            "decision": "wait",
            "confidence": 1.0,
            "reason": "IA do gate live indisponivel; aguardando nova tentativa antes de enviar.",
            "wait_minutes": 15,
            "facts": facts,
        }

    decision = str(payload_json.get("decision") or "").strip().lower()
    if decision not in SALES_OUTREACH_SEND_GATE_DECISIONS:
        decision = "wait"

    try:
        confidence = max(0.0, min(float(payload_json.get("confidence")), 1.0))
    except (TypeError, ValueError):
        confidence = 0.0
    if confidence < _sales_outreach_ai_min_confidence():
        decision = "wait"

    try:
        wait_minutes = int(payload_json.get("wait_minutes") or 0)
    except (TypeError, ValueError):
        wait_minutes = 0
    if decision == "wait":
        wait_minutes = max(5, wait_minutes or min_wait_minutes)

    final_message = str(payload_json.get("final_message") or "").strip()
    if decision == "send" and _sales_outreach_violates_sender_persona(final_message):
        final_message = _sales_outreach_safe_context_reply(prospect)
    if decision == "wait" and facts.get("last_live_direction") == MessageDirection.INBOUND.value:
        if latest_live_inbound_classification == "automatica" or resolved_step == "auto_reply_hold":
            return _sales_outreach_auto_reply_block_gate(facts=facts)
        decision = "send"
        wait_minutes = 0
        if final_message and not _sales_outreach_violates_sender_persona(final_message):
            final_message = final_message
        else:
            final_message = _sales_outreach_safe_context_reply(prospect)
        payload_json["reason"] = "Clinica respondeu; fallback comercial liberado para nao deixar resposta humana sem retorno."
    return {
        "decision": decision,
        "confidence": confidence,
        "reason": _sales_outreach_clean_ai_text(payload_json.get("reason"))[:500] or "Decisao do gate live comercial.",
        "wait_minutes": wait_minutes if decision == "wait" else None,
        "final_message": final_message if decision == "send" else None,
        "facts": facts,
    }


def _sales_outreach_summarize_older_messages(
    db: Session,
    *,
    conversation_id: UUID,
    recent_limit: int,
) -> str:
    older_rows = db.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.desc(), Message.id.desc())
        .offset(max(0, recent_limit))
        .limit(24)
    ).scalars().all()
    if not older_rows:
        return ""

    formatted_lines = _sales_outreach_format_message_lines(list(reversed(older_rows)))
    if not formatted_lines:
        return ""

    if _sales_outreach_ai_is_enabled():
        prompt = (
            "Resuma o historico mais antigo de uma conversa comercial B2B no WhatsApp. "
            "Retorne JSON com os campos summary e confidence. "
            "O resumo deve ter no maximo 3 frases curtas, em portugues, e destacar explicitamente: "
            "origem do contato, objecao ou tema principal da clinica, o que a ClinicFlux AI ja explicou, "
            "pendencia aberta e tom da clinica. "
            "Prefira um formato compacto como: origem: ... tema: ... pendencia: ... tom: ... "
            f"Historico antigo:\n{chr(10).join(formatted_lines)}"
        )
        try:
            result = _run_sales_outreach_llm_task(
                db,
                tenant_id=None,
                conversation_id=conversation_id,
                task="sales_outreach_context_summary",
                prompt=prompt,
            )
            payload = _sales_outreach_parse_llm_json(result.get("output"))
            if payload:
                summary = _sales_outreach_clean_ai_text(payload.get("summary"))[:500]
                if summary:
                    return summary
        except Exception:
            pass

    first_line = formatted_lines[0] if formatted_lines else ""
    last_line = formatted_lines[-1] if formatted_lines else ""
    fallback = (
        f"origem: {first_line[:140] or 'contato comercial em andamento'}. "
        f"tema: {last_line[:140] or 'sem tema identificado'}. "
        "pendencia: contexto antigo sem resumo por IA; usar historico recente para decidir. "
        "tom: neutro."
    )
    return fallback[:500]


def _sales_outreach_recent_transcript(
    db: Session,
    *,
    conversation_id: UUID,
    limit: int | None = None,
) -> str:
    resolved_limit = limit
    if resolved_limit is None:
        try:
            resolved_limit = max(1, int(settings.sales_outreach_ai_context_messages or 12))
        except (TypeError, ValueError):
            resolved_limit = 12

    total_messages = db.scalar(
        select(func.count(Message.id)).where(Message.conversation_id == conversation_id)
    ) or 0
    rows = db.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.desc(), Message.id.desc())
        .limit(max(1, resolved_limit))
    ).scalars().all()
    if not rows:
        return ""

    transcript_lines: list[str] = []
    omitted_count = max(int(total_messages) - len(rows), 0)
    if omitted_count > 0:
        older_summary = _sales_outreach_summarize_older_messages(
            db,
            conversation_id=conversation_id,
            recent_limit=max(1, resolved_limit),
        )
        transcript_lines.append(
            f"[Resumo do historico anterior: {older_summary or f'{omitted_count} mensagem(ns) mais antiga(s) nao exibida(s)'}]"
        )
    transcript_lines.extend(_sales_outreach_format_message_lines(list(reversed(rows))))
    return "\n".join(transcript_lines)


def _latest_sales_outreach_inbound_message(db: Session, *, conversation_id: UUID) -> Message | None:
    return db.scalar(
        select(Message)
        .where(
            Message.conversation_id == conversation_id,
            Message.direction == MessageDirection.INBOUND.value,
        )
        .order_by(Message.created_at.desc(), Message.id.desc())
        .limit(1)
    )


def _latest_sales_outreach_inbound_is_opt_out(db: Session, *, conversation_id: UUID) -> bool:
    latest_inbound = _latest_sales_outreach_inbound_message(db, conversation_id=conversation_id)
    if not latest_inbound:
        return False
    return _looks_like_outreach_opt_out(latest_inbound.body)


def _review_sales_outreach_inbound_with_ai(
    db: Session,
    *,
    prospect: ProspectAccount,
    conversation: Conversation,
    inbound_body: str,
    heuristic_classification: str,
) -> dict | None:
    if (not _sales_outreach_ai_is_enabled()) or not inbound_body:
        return None
    recent_transcript = _sales_outreach_recent_transcript(db, conversation_id=conversation.id)

    prompt = (
        "Voce esta revisando uma resposta recebida em um fluxo comercial B2B por WhatsApp entre ClinicFlux AI e uma clinica. "
        f"{_sales_outreach_skill_context(prospect)} "
        "Classifique a mensagem recebida usando apenas uma destas classes: "
        "gestor, recepcao, pediu_tempo, duvida, fora_de_escopo, bloqueio_acesso, automatica. "
        "Considere que mensagens de boas-vindas, horario de funcionamento ou autoatendimento contam como recepcao ou automatica, "
        "nao como duvida real. "
        "Se a ultima pergunta da ClinicFlux AI era para descobrir quem cuida dos agendamentos e a clinica respondeu algo curto como "
        "'como posso ajudar?' sem mencionar encaminhamento, recepcao ou outro responsavel, trate isso como ambiguidade operacional: "
        "nao assuma pitch de recepcao longa; use gestor apenas se houver indicio de que a propria pessoa assumiu o atendimento. "
        "Responda JSON com os campos classification, confidence, reason, suggested_pause. "
        f"Clinica: {prospect.clinic_name}. "
        f"Historico recente:\n{recent_transcript or 'Sem historico anterior.'}\n"
        f"Mensagem recebida: {inbound_body}. "
        f"Classificacao heuristica atual: {heuristic_classification}."
    )

    try:
        result = _run_sales_outreach_llm_task(
            db,
            tenant_id=conversation.tenant_id,
            conversation_id=conversation.id,
            task="sales_outreach_inbound_review",
            prompt=prompt,
        )
    except Exception:
        return None

    payload = _sales_outreach_parse_llm_json(result.get("output"))
    if not payload:
        return None

    classification = str(payload.get("classification") or "").strip().lower()
    if classification not in SALES_OUTREACH_AI_ALLOWED_CLASSES:
        return None

    try:
        confidence = float(payload.get("confidence"))
    except (TypeError, ValueError):
        confidence = 0.0

    return {
        "classification": classification,
        "confidence": max(0.0, min(confidence, 1.0)),
        "reason": _sales_outreach_clean_ai_text(payload.get("reason"))[:300],
        "suggested_pause": bool(payload.get("suggested_pause")),
        "metadata": result.get("metadata") if isinstance(result.get("metadata"), dict) else {},
    }


def _review_sales_outreach_outbound_with_ai(
    db: Session,
    *,
    prospect: ProspectAccount,
    conversation: Conversation,
    step: str,
    candidate_message: str,
    recipient_name: str | None,
) -> dict | None:
    if (not _sales_outreach_ai_is_enabled()) or not candidate_message:
        return None
    if prospect.do_not_contact or _latest_sales_outreach_inbound_is_opt_out(db, conversation_id=conversation.id):
        return {
            "approved": False,
            "final_message": "",
            "confidence": 1.0,
            "reason": "A clinica recusou o contato comercial; nenhuma nova mensagem deve ser enviada.",
            "metadata": {"blocked_by_opt_out": True},
        }

    latest_inbound = _latest_sales_outreach_inbound_message(db, conversation_id=conversation.id)
    latest_inbound_text = _sales_outreach_clean_ai_text(latest_inbound.body if latest_inbound else "")[:500]
    recent_transcript = _sales_outreach_recent_transcript(db, conversation_id=conversation.id)
    outreach = _outreach_snapshot(prospect)
    last_reply_classification = str(outreach.get("last_reply_classification") or "").strip()

    prompt = (
        "Voce esta revisando uma mensagem comercial B2B que sera enviada pela ClinicFlux AI para uma clinica via WhatsApp. "
        f"{_sales_outreach_skill_context(prospect)} "
        "A mensagem precisa soar humana, objetiva, profissional e coerente com a ultima resposta da clinica. "
        "Nao invente preco, promessa, integracao, desconto ou dado que nao exista no contexto. "
        "Se a resposta da clinica parecer recepcao ou autoatendimento, a mensagem deve pedir o responsavel certo sem repetir um pitch longo. "
        "Responda JSON com os campos approved, final_message, confidence, reason. "
        f"Clinica: {prospect.clinic_name}. "
        f"Etapa atual: {step}. "
        f"Destinatario preferencial: {recipient_name or prospect.owner_name or prospect.manager_name or 'nao informado'}. "
        f"Ultima classificacao da clinica: {last_reply_classification or 'nao classificada'}. "
        f"Historico recente:\n{recent_transcript or 'Sem historico anterior.'}\n"
        f"Ultima mensagem recebida: {latest_inbound_text or 'nenhuma'}. "
        f"Mensagem candidata: {candidate_message}."
    )

    try:
        result = _run_sales_outreach_llm_task(
            db,
            tenant_id=conversation.tenant_id,
            conversation_id=conversation.id,
            task="sales_outreach_outbound_review",
            prompt=prompt,
        )
    except Exception:
        return None

    payload = _sales_outreach_parse_llm_json(result.get("output"))
    if not payload:
        return None

    final_message = str(payload.get("final_message") or "").strip()
    try:
        confidence = float(payload.get("confidence"))
    except (TypeError, ValueError):
        confidence = 0.0

    return {
        "approved": bool(payload.get("approved")),
        "final_message": final_message,
        "confidence": max(0.0, min(confidence, 1.0)),
        "reason": _sales_outreach_clean_ai_text(payload.get("reason"))[:300],
        "metadata": result.get("metadata") if isinstance(result.get("metadata"), dict) else {},
    }


def _looks_like_outreach_opt_out(value: str | None) -> bool:
    lookup = _normalized_lookup_text(value)
    if any(pattern in lookup for pattern in SALES_OUTREACH_OPT_OUT_PATTERNS):
        return True

    regex_patterns = (
        r"\bnao (tenho|temos) interesse\b",
        r"\bno momento nao (tenho|temos) interesse\b",
        r"\bsem interesse (no momento|agora)?\b",
        r"\bagradecemos [a-z\s]{0,40}contato[a-z\s]{0,40}mas[a-z\s]{0,20}nao[a-z\s]{0,20}interesse\b",
    )
    return any(re.search(pattern, lookup) for pattern in regex_patterns)


def _looks_like_ambiguous_help_reply(value: str | None) -> bool:
    lookup = _normalized_lookup_text(value)
    if not lookup:
        return False
    phrases = (
        "como posso ajudar",
        "sim como posso ajudar",
        "ola como posso ajudar",
        "olá como posso ajudar",
        "bom dia como posso ajudar",
        "boa tarde como posso ajudar",
        "boa noite como posso ajudar",
        "em que posso ajudar",
        "posso ajudar",
        "como posso te ajudar",
        "como posso ajuda lo",
        "como posso ajuda la",
    )
    return any(lookup == phrase or lookup.endswith(f" {phrase}") for phrase in phrases)


def _looks_like_contact_handoff(value: str | None) -> bool:
    lookup = _normalized_lookup_text(value)
    if not lookup:
        return False
    phrases = (
        "vou te passar o telefone",
        "vou passar o telefone",
        "vou te passar o contato",
        "vou passar o contato",
        "vou te encaminhar o contato",
        "vou encaminhar o contato",
        "vou te enviar o contato",
        "vou te passar o numero",
        "vou passar o numero",
        "posso te passar o contato",
        "posso te passar o telefone",
        "segue o contato",
        "segue o telefone",
        "estou te passando o contato",
        "estou te passando o telefone",
        "setor de convenios",
        "contato do nosso setor",
        "pessoa responsavel",
        "responsavel pelo setor",
        "responsavel pelo atendimento",
        "responsavel por ai",
        "telefone da pessoa responsavel",
        "numero da pessoa responsavel",
        "vou falar com a recepcao",
        "vou passar para a recepcao",
        "vou encaminhar para a recepcao",
    )
    return any(phrase in lookup for phrase in phrases)


def _clean_forwarded_contact_name(value: str | None) -> str:
    text = re.sub(r"\s+", " ", str(value or "").strip(" .,:;()-"))
    if not text:
        return ""
    text = re.sub(
        r"^(?:nome|contato|responsavel|telefone|numero|whatsapp|ramal|setor)\s*(?:do|da|de)?\s*",
        "",
        text,
        flags=re.IGNORECASE,
    ).strip(" .,:;()-")
    text = re.split(r"[|,/;]", text, maxsplit=1)[0].strip()
    words = [word for word in text.split() if re.search(r"[A-Za-z]", word)]
    if not words:
        return ""
    candidate = " ".join(words[:4]).strip()
    if len(candidate) > 80:
        candidate = candidate[:80].rsplit(" ", 1)[0].strip() or candidate[:80].strip()
    return candidate


def _extract_forwarded_contact_from_text(value: str | None) -> tuple[str | None, str | None]:
    raw_text = str(value or "").strip()
    if not raw_text or not _looks_like_contact_handoff(raw_text):
        return None, None

    return _extract_contact_phone_and_name_from_text(raw_text)


def _extract_contact_phone_and_name_from_text(value: str | None) -> tuple[str | None, str | None]:
    raw_text = str(value or "").strip()
    if not raw_text:
        return None, None

    for match in HANDOFF_CONTACT_PHONE_PATTERN.finditer(raw_text):
        raw_phone = str(match.group(1) or "").strip()
        normalized_phone = normalize_phone(raw_phone)
        if len(normalized_phone) < 10 or len(normalized_phone) > 15:
            continue
        trailing_name = _clean_forwarded_contact_name(raw_text[match.end() :])
        leading_name = _clean_forwarded_contact_name(raw_text[: match.start()])
        contact_name = trailing_name or leading_name or None
        return contact_name, normalized_phone
    return None, None


def _expire_stale_sales_outreach_outbox(
    db: Session,
    *,
    prospect: ProspectAccount,
    keep_phone: str,
) -> int:
    normalized_keep_phone = normalize_phone(keep_phone)
    if not normalized_keep_phone:
        return 0

    retired_count = 0
    sender_tenant = _sales_outreach_sender_tenant(db)
    candidates = db.execute(
        select(OutboxMessage).where(
            OutboxMessage.tenant_id == sender_tenant.id,
            OutboxMessage.status.in_(
                [
                    OutboxStatus.PENDING.value,
                    OutboxStatus.FAILED.value,
                    OutboxStatus.PROCESSING.value,
                ]
            ),
        )
    ).scalars().all()

    for item in candidates:
        payload = item.payload if isinstance(item.payload, dict) else {}
        metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
        if str(metadata.get("source") or "").strip() != "sales_outreach":
            continue
        if str(metadata.get("prospect_account_id") or "").strip() != str(prospect.id):
            continue

        destination = normalize_phone(str(payload.get("to") or "").strip())
        if not destination or destination == normalized_keep_phone:
            continue

        item.status = OutboxStatus.DEAD_LETTER.value
        item.next_retry_at = None
        item.last_error = "Outbox aposentada apos identificacao de novo contato responsavel."
        metadata["superseded_by_forwarded_contact_phone"] = normalized_keep_phone
        metadata["superseded_at"] = _now().isoformat()
        payload["metadata"] = metadata
        item.payload = payload
        db.add(item)
        retired_count += 1

        outbound_message_id = str(metadata.get("outbound_message_id") or "").strip()
        if outbound_message_id:
            try:
                outbound_message = db.get(Message, UUID(outbound_message_id))
            except (TypeError, ValueError):
                outbound_message = None
            if outbound_message and outbound_message.status == MessageStatus.QUEUED.value:
                existing_payload = outbound_message.payload if isinstance(outbound_message.payload, dict) else {}
                outbound_message.status = MessageStatus.FAILED.value
                outbound_message.payload = {
                    **existing_payload,
                    "dispatch_error": "Mensagem substituida por novo contato responsavel identificado na conversa.",
                }
                db.add(outbound_message)

    return retired_count


def _restart_sales_outreach_for_forwarded_contact(
    db: Session,
    *,
    prospect: ProspectAccount,
    forwarded_contact_name: str | None,
    forwarded_contact_phone: str,
) -> dict:
    normalized_phone = normalize_phone(forwarded_contact_phone)
    if not normalized_phone:
        return {"status": "skipped", "reason": "missing_forwarded_contact_phone"}

    retired_outbox_count = _expire_stale_sales_outreach_outbox(
        db,
        prospect=prospect,
        keep_phone=normalized_phone,
    )
    normalized_name = _clean_forwarded_contact_name(forwarded_contact_name) or prospect.owner_name or prospect.manager_name or ""
    prospect.phone = normalized_phone
    prospect.whatsapp_phone = normalized_phone
    if normalized_name:
        prospect.owner_name = normalized_name
        prospect.manager_name = normalized_name

    _update_outreach_snapshot(
        prospect,
        patch={
            "automation_active": False,
            "automation_stopped_at": _now().isoformat(),
            "automation_stop_reason": "forwarded_contact_restarted",
            "forwarded_contact_name": normalized_name or None,
            "forwarded_contact_phone": normalized_phone,
        },
    )
    add_timeline(
        db,
        prospect,
        event_type="prospect.outreach.forwarded_contact_restart",
        event_label="Contato responsavel identificado na mensagem e outreach reiniciado",
        actor_type="system",
        payload={
            "forwarded_contact_name": normalized_name or None,
            "forwarded_contact_phone": normalized_phone,
            "retired_outbox_count": retired_outbox_count,
        },
    )
    started = start_sales_outreach_automation(
        db,
        prospect=prospect,
        actor_id=None,
        base_url=_default_sales_outreach_base_url(),
    )
    return {
        "status": "restarted",
        "prospect_id": str(prospect.id),
        "contact_name": normalized_name or None,
        "contact_phone": normalized_phone,
        "retired_outbox_count": retired_outbox_count,
        "conversation_id": str(started.get("conversation_id") or ""),
        "step": str(started.get("step") or ""),
    }


def _conversation_has_recent_contact_handoff_hint(
    db: Session,
    *,
    conversation_id: UUID,
    current_message_id: UUID,
) -> bool:
    recent_inbound = db.execute(
        select(Message)
        .where(
            Message.conversation_id == conversation_id,
            Message.direction == MessageDirection.INBOUND.value,
            Message.id != current_message_id,
        )
        .order_by(Message.created_at.desc(), Message.id.desc())
        .limit(5)
    ).scalars().all()
    return any(_looks_like_contact_handoff(item.body) for item in recent_inbound)


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
            build_demo_login_url(base_url, raw_token),
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
        "ClinicFlux AI - contato inicial",
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
            "ClinicFlux AI - pitch com demo",
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
            "ClinicFlux AI - video follow-up",
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
    flow_config: dict | None = None,
) -> str:
    sender_name = str(settings.sales_outreach_display_name or "Time ClinicFlux AI").strip() or "Time ClinicFlux AI"
    pain_hint = f" e reduzir {prospect.main_pain.lower()}" if prospect.main_pain else ""
    resolved_flow_config = flow_config if isinstance(flow_config, dict) else _default_sales_outreach_flow_config()
    initial_messages = resolved_flow_config.get("initial_messages") if isinstance(resolved_flow_config.get("initial_messages"), list) else None
    step_messages = resolved_flow_config.get("step_messages") if isinstance(resolved_flow_config.get("step_messages"), dict) else {}

    if step == "reception_intro":
        return _pick_sales_outreach_initial_message(prospect, initial_messages=initial_messages)

    if step == "reception_triage":
        template = _pick_sales_outreach_step_message(
            prospect,
            step="reception_triage",
            variations=step_messages.get("reception_triage") if isinstance(step_messages.get("reception_triage"), list) else None,
        )
        return template.format(pain_hint=pain_hint)

    if step == "reception_cta":
        return _pick_sales_outreach_step_message(
            prospect,
            step="reception_cta",
            variations=step_messages.get("reception_cta") if isinstance(step_messages.get("reception_cta"), list) else None,
        )

    if step == "contact_handoff_ack":
        return _pick_sales_outreach_step_message(
            prospect,
            step="contact_handoff_ack",
            variations=step_messages.get("contact_handoff_ack") if isinstance(step_messages.get("contact_handoff_ack"), list) else None,
        )

    if step == "decision_maker_pitch":
        addressee = _first_name(recipient_name or prospect.owner_name or prospect.manager_name)
        greeting = f"Ola, {addressee}!" if addressee else "Ola!"
        if _sales_outreach_offer_lane(prospect) == "website_first":
            return (
                f"{greeting} Aqui e {sender_name} da ClinicFlux AI.\n"
                "Encontrei a clinica pelo Google e vi que nao aparece um site vinculado. Isso pode fazer pacientes dependerem so do perfil do Google antes de chamar no WhatsApp.\n"
                "Posso te mostrar uma proposta simples de site local com WhatsApp, mapa, servicos, prova de confianca e base de SEO?"
            )
        return (
            f"{greeting} Aqui e {sender_name} da ClinicFlux AI.\n"
            "Ajudamos clinicas a organizar atendimento, WhatsApp e agendamentos para responder mais rapido, perder menos pacientes e ter mais controle da operacao.\n"
            f"Demonstracao rapida: {demo_login_url}"
        )

    if step == "video_followup":
        addressee = _first_name(recipient_name or prospect.owner_name or prospect.manager_name)
        greeting = f"Ola, {addressee}!" if addressee else "Ola!"
        return (
            f"{greeting} Separei um video curto mostrando esse fluxo na pratica:\n"
            f"{video_url}\n"
            "Se fizer sentido, eu tambem posso te mostrar onde isso mais costuma destravar resultado: atendimento no WhatsApp, agenda e recuperacao de oportunidades."
        )

    if step == "clarification_reply":
        return _pick_sales_outreach_step_message(
            prospect,
            step="clarification_reply",
            variations=step_messages.get("clarification_reply") if isinstance(step_messages.get("clarification_reply"), list) else None,
        )

    if step == "clarification_cta":
        return _pick_sales_outreach_step_message(
            prospect,
            step="clarification_cta",
            variations=step_messages.get("clarification_cta") if isinstance(step_messages.get("clarification_cta"), list) else None,
        )

    if step == "direct_demo_offer":
        return _pick_sales_outreach_step_message(
            prospect,
            step="direct_demo_offer",
            variations=step_messages.get("direct_demo_offer") if isinstance(step_messages.get("direct_demo_offer"), list) else None,
        )

    if step == "timing_followup":
        return _pick_sales_outreach_step_message(
            prospect,
            step="timing_followup",
            variations=step_messages.get("timing_followup") if isinstance(step_messages.get("timing_followup"), list) else None,
        )

    if step == "auto_reply_hold":
        return _pick_sales_outreach_step_message(
            prospect,
            step="auto_reply_hold",
            variations=step_messages.get("auto_reply_hold") if isinstance(step_messages.get("auto_reply_hold"), list) else None,
        )

    if step == "routing_followup":
        return _pick_sales_outreach_step_message(
            prospect,
            step="routing_followup",
            variations=step_messages.get("routing_followup") if isinstance(step_messages.get("routing_followup"), list) else None,
        )

    if step == "access_request":
        return _pick_sales_outreach_step_message(
            prospect,
            step="access_request",
            variations=step_messages.get("access_request") if isinstance(step_messages.get("access_request"), list) else None,
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
            operational_notes=f"Prospect comercial ClinicFlux AI vinculado ao prospect_account_id={prospect.id}",
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


def ensure_admin_whatsapp_test_contact(
    db: Session,
    *,
    prospect: ProspectAccount,
) -> Conversation:
    sender_tenant = ensure_sales_outreach_sender_tenant(db)
    raw_phone = _admin_internal_simulation_phone(prospect.id)
    normalized_phone = raw_phone
    test_contact_name = f"Simulador interno - {prospect.clinic_name}"
    contact_tag = f"prospect_id:{prospect.id}"
    test_contact_tag = "adm_whatsapp_test_contact"
    internal_simulation_tag = ADM_INTERNAL_WHATSAPP_SIMULATION_TAG

    unit_id = db.scalar(
        select(Unit.id)
        .where(Unit.tenant_id == sender_tenant.id, Unit.is_active.is_(True))
        .order_by(Unit.created_at.asc())
        .limit(1)
    )

    patient = db.scalar(
        select(Patient)
        .where(
            Patient.tenant_id == sender_tenant.id,
            or_(
                Patient.normalized_phone == normalized_phone,
                Patient.phone == raw_phone,
                Patient.phone == normalized_phone,
            ),
        )
        .order_by(Patient.created_at.desc())
        .limit(1)
    )
    if not patient:
        patient = Patient(
            tenant_id=sender_tenant.id,
            unit_id=unit_id,
            full_name=test_contact_name,
            phone=raw_phone,
            normalized_phone=normalized_phone,
            status="lead",
            origin="adm_internal_whatsapp_simulation",
            lgpd_consent=False,
            marketing_opt_in=False,
            tags_cache=[test_contact_tag, internal_simulation_tag],
        )
        db.add(patient)
        db.flush()
    elif unit_id and not patient.unit_id:
        patient.unit_id = unit_id
        db.add(patient)
    else:
        patient.full_name = test_contact_name
        patient.phone = raw_phone
        patient.normalized_phone = normalized_phone
        tags = set(patient.tags_cache or [])
        tags.add(test_contact_tag)
        tags.add(internal_simulation_tag)
        patient.tags_cache = sorted(tags)
        db.add(patient)

    lead = db.scalar(
        select(Lead)
        .where(
            Lead.tenant_id == sender_tenant.id,
            or_(
                Lead.phone == raw_phone,
                Lead.phone == normalized_phone,
                Lead.name == test_contact_name,
            ),
        )
        .order_by(Lead.created_at.desc())
        .limit(1)
    )
    if not lead:
        lead = Lead(
            tenant_id=sender_tenant.id,
            patient_id=patient.id,
            owner_user_id=None,
            name=test_contact_name,
            phone=None,
            origin="adm_internal_whatsapp_simulation",
            interest=prospect.main_pain or "simulacao interna de conversa comercial",
            stage=LeadStage.QUALIFIED.value,
            score=80,
            temperature=LeadTemperature.WARM.value,
            status="ativo",
            notes="Simulador interno criado no /adm para validar conversa comercial sem WhatsApp oficial.",
        )
        db.add(lead)
        db.flush()
    else:
        lead.patient_id = patient.id
        lead.name = test_contact_name
        lead.phone = None
        lead.origin = lead.origin or "adm_internal_whatsapp_simulation"
        lead.interest = lead.interest or (prospect.main_pain or "simulacao interna de conversa comercial")
        lead.stage = LeadStage.QUALIFIED.value
        lead.score = max(int(lead.score or 0), 80)
        lead.temperature = LeadTemperature.WARM.value
        lead.status = "ativo"
        lead.notes = lead.notes or "Simulador interno criado no /adm para validar conversa comercial sem WhatsApp oficial."
        db.add(lead)

    external_thread_id = f"adm-whatsapp-internal-sim:{prospect.id}"
    conversation = db.scalar(
        select(Conversation)
        .where(
            Conversation.tenant_id == sender_tenant.id,
            Conversation.external_thread_id == external_thread_id,
        )
        .limit(1)
    )
    if not conversation:
        conversation = Conversation(
            tenant_id=sender_tenant.id,
            unit_id=unit_id or patient.unit_id,
            patient_id=patient.id,
            lead_id=lead.id,
            channel="whatsapp",
            external_thread_id=external_thread_id,
            assigned_user_id=None,
            status="aberta",
            ai_summary="Simulador interno para validar conversa comercial sem WhatsApp oficial, bridge ou telefone de teste.",
            ai_autoresponder_enabled=False,
            tags=sorted({contact_tag, test_contact_tag, internal_simulation_tag, "prospect_outreach"}),
            last_message_at=_now(),
        )
        db.add(conversation)
        db.flush()
    else:
        tags = set(conversation.tags or [])
        tags.add(contact_tag)
        tags.add(test_contact_tag)
        tags.add(internal_simulation_tag)
        tags.add("prospect_outreach")
        conversation.unit_id = unit_id or conversation.unit_id or patient.unit_id
        conversation.patient_id = patient.id
        conversation.lead_id = lead.id
        conversation.channel = "whatsapp"
        conversation.status = "aberta"
        conversation.ai_summary = conversation.ai_summary or "Simulador interno para validar conversa comercial sem WhatsApp oficial, bridge ou telefone de teste."
        conversation.ai_autoresponder_enabled = False
        conversation.tags = sorted(tags)
        conversation.last_message_at = conversation.last_message_at or _now()
        db.add(conversation)
        db.flush()

    _seed_admin_internal_sales_simulation_intro(db, prospect=prospect, conversation=conversation)
    db.commit()
    db.refresh(conversation)
    return conversation


def _seed_admin_internal_sales_simulation_intro(
    db: Session,
    *,
    prospect: ProspectAccount,
    conversation: Conversation,
) -> Message | None:
    existing = db.scalar(
        select(Message.id)
        .where(Message.tenant_id == conversation.tenant_id, Message.conversation_id == conversation.id)
        .limit(1)
    )
    if existing:
        return None

    step, message_text, ai_review, demo_login_url = _build_admin_internal_sales_simulation_reply(
        db,
        prospect=prospect,
        conversation=conversation,
        step="reception_intro",
        recipient_name=prospect.owner_name or prospect.manager_name,
    )
    now = _now()
    outbound = Message(
        tenant_id=conversation.tenant_id,
        conversation_id=conversation.id,
        direction=MessageDirection.OUTBOUND.value,
        channel="whatsapp",
        sender_type="ai",
        body=message_text,
        message_type="text",
        payload={
            "source": ADM_INTERNAL_WHATSAPP_SIMULATION_SOURCE,
            "simulated_system_response": True,
            "internal_delivery": True,
            "step": step,
            "demo_login_url": demo_login_url,
            "ai_review": jsonable_encoder(ai_review) if isinstance(ai_review, dict) else None,
            "note": "Mensagem inicial gerada internamente. Nenhum WhatsApp oficial ou bridge foi acionado.",
        },
        status=MessageStatus.SENT.value,
        sent_at=now,
        delivered_at=now,
    )
    db.add(outbound)
    conversation.last_message_at = now
    db.add(conversation)
    db.flush()
    return outbound


def _latest_admin_internal_sales_simulation_step(
    db: Session,
    *,
    conversation: Conversation,
) -> str:
    rows = db.execute(
        select(Message)
        .where(
            Message.tenant_id == conversation.tenant_id,
            Message.conversation_id == conversation.id,
            Message.direction == MessageDirection.OUTBOUND.value,
        )
        .order_by(Message.created_at.desc(), Message.id.desc())
        .limit(12)
    ).scalars().all()
    for message in rows:
        payload = message.payload if isinstance(message.payload, dict) else {}
        step = str(payload.get("step") or "").strip()
        if step in SALES_OUTREACH_STEPS:
            return step
    return "reception_intro"


def _admin_internal_sales_simulation_has_prior_step(
    db: Session,
    *,
    conversation: Conversation,
    step: str,
) -> bool:
    existing = db.scalar(
        select(Message.id)
        .where(
            Message.tenant_id == conversation.tenant_id,
            Message.conversation_id == conversation.id,
            Message.direction == MessageDirection.OUTBOUND.value,
            Message.payload["source"].astext == ADM_INTERNAL_WHATSAPP_SIMULATION_SOURCE,
            Message.payload["step"].astext == step,
        )
        .limit(1)
    )
    return existing is not None


def _admin_internal_sales_simulation_seen_text(
    db: Session,
    *,
    conversation: Conversation,
    candidate_text: str,
) -> bool:
    normalized_candidate = _normalized_lookup_text(candidate_text)
    if not normalized_candidate:
        return False
    rows = db.execute(
        select(Message.body)
        .where(
            Message.tenant_id == conversation.tenant_id,
            Message.conversation_id == conversation.id,
            Message.direction == MessageDirection.OUTBOUND.value,
        )
        .order_by(Message.created_at.desc(), Message.id.desc())
        .limit(20)
    ).all()
    return any(_normalized_lookup_text(row[0]) == normalized_candidate for row in rows)


def _admin_internal_sales_simulation_strip_unsafe_links(value: str) -> str:
    text = re.sub(r"https?://(?:localhost|127\.0\.0\.1|0\.0\.0\.0)(?::\d+)?[^\s]*", "", str(value or ""))
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _admin_internal_sales_simulation_non_repeating_reply(inbound_body: str) -> str:
    normalized = _normalized_lookup_text(inbound_body)
    if any(term in normalized for term in ("gostei", "interessante", "faz sentido", "legal", "boa")):
        return "Boa. O proximo passo mais util e eu te mostrar uma demo curta do fluxo de WhatsApp e agenda. Posso seguir por esse caminho?"
    if any(term in normalized for term in ("sou o dono", "sou dono", "gerente sou eu", "sou o gerente", "responsavel sou eu")):
        return "Perfeito, entao falo direto contigo. Quer que eu te mostre primeiro a parte de WhatsApp e agenda ou prefere um resumo rapido do ganho operacional?"
    return "Para eu nao repetir: a parte mais importante para voce agora e WhatsApp, agenda ou acompanhamento dos retornos?"


def _admin_internal_sales_simulation_contextual_reply(
    db: Session,
    *,
    prospect: ProspectAccount,
    conversation: Conversation,
    inbound_body: str,
    reply_classification: str,
    last_step: str,
) -> tuple[str, str]:
    normalized = _normalized_lookup_text(inbound_body)
    decision_pitch_sent = _admin_internal_sales_simulation_has_prior_step(
        db,
        conversation=conversation,
        step="decision_maker_pitch",
    )
    is_decision_maker = any(
        term in normalized
        for term in (
            "sou o dono",
            "sou dono",
            "dono da clinica",
            "sou a dona",
            "sou dona",
            "gerente sou eu",
            "sou o gerente",
            "sou gerente",
            "responsavel sou eu",
            "eu cuido",
        )
    )
    is_confused = any(
        term in normalized
        for term in (
            "nao entendi",
            "nao compreendi",
            "como assim",
            "explica melhor",
            "do que se trata",
            "o que e isso",
        )
    )
    is_positive = any(
        term in normalized
        for term in (
            "gostei",
            "interessante",
            "faz sentido",
            "legal",
            "boa",
            "quero ver",
            "pode mostrar",
            "manda",
        )
    )
    asks_price = any(term in normalized for term in ("preco", "valor", "custa", "quanto", "mensalidade"))
    asks_source = any(
        term in normalized
        for term in (
            "como me achou",
            "como nos achou",
            "como achou",
            "como acharam",
            "como voces acharam",
            "como encontrou",
            "de onde pegou",
            "onde pegou",
            "qual busca",
            "como chegaram",
            "por onde encontrou",
        )
    )
    asks_identity = any(term in normalized for term in ("quem e voce", "quem e voces", "do que se trata", "qual empresa"))
    patient_intent = any(
        term in normalized
        for term in (
            "quero marcar consulta",
            "quero agendar",
            "marcar horario",
            "agendar consulta",
            "tenho dor",
            "preciso de consulta",
        )
    )
    has_existing_system = any(
        term in normalized
        for term in (
            "ja tenho sistema",
            "ja temos sistema",
            "usamos sistema",
            "temos software",
            "ja usamos software",
            "ja tenho software",
        )
    )
    asks_integration = any(
        term in normalized
        for term in (
            "integra",
            "integracao",
            "doctoralia",
            "google agenda",
            "agenda google",
            "meu sistema",
            "nosso sistema",
        )
    )
    asks_proposal = any(
        term in normalized
        for term in (
            "manda proposta",
            "envia proposta",
            "pode mandar proposta",
            "mande proposta",
            "manda material",
            "envia material",
            "manda apresentacao",
        )
    )
    no_website_signal = any(
        term in normalized
        for term in (
            "nao temos site",
            "nao tem site",
            "nao possuimos site",
            "sem site",
            "precisamos de site",
            "quero site",
            "site novo",
            "nosso site e ruim",
        )
    )

    if asks_source:
        return (
            "clarification_reply",
            (
                "Encontrei a clinica pelo Google em uma pesquisa de clinicas odontologicas. "
                "Meu contato e comercial: a ideia e entender se faz sentido melhorar atendimento, WhatsApp e agenda por ai. "
                "Quem cuida dessa parte?"
            ),
        )

    if patient_intent:
        return (
            "routing_followup",
            (
                "So para alinhar: meu contato e comercial, nao sou paciente e nao estou tentando agendar consulta. "
                "Quem cuida do WhatsApp e dos agendamentos da clinica por ai?"
            ),
        )

    if asks_identity:
        return (
            "clarification_reply",
            (
                "Aqui e o time comercial da ClinicFlux AI. A gente ajuda clinicas a organizar conversas no WhatsApp, agenda e retornos. "
                "Faz sentido eu falar com voce sobre essa parte?"
            ),
        )

    if is_confused:
        return (
            "clarification_reply",
            (
                "Claro. Explicando de forma simples: a ClinicFlux AI ajuda a clinica a organizar o atendimento no WhatsApp, "
                "responder com mais agilidade e manter os agendamentos e retornos sob controle. Faz sentido eu te mostrar um exemplo rapido desse fluxo?"
            ),
        )

    if asks_integration:
        return (
            "clarification_reply",
            (
                "Pode depender do sistema que voces usam, entao eu nao quero prometer integracao sem validar. "
                "O caminho certo e mapear o fluxo atual de WhatsApp e agenda primeiro. Qual sistema voces usam hoje?"
            ),
        )

    if has_existing_system:
        return (
            "clarification_reply",
            (
                "Perfeito. A ideia nao e trocar uma agenda por outra sem necessidade. "
                "Normalmente olhamos onde o WhatsApp, a recepcao e os retornos ainda ficam soltos ao redor do sistema atual. "
                "Qual parte mais pesa hoje?"
            ),
        )

    if asks_price:
        return (
            "clarification_reply",
            (
                "Consigo te orientar sobre valores, sim. Antes, preciso entender o tamanho do fluxo para nao te passar algo solto: "
                "hoje voces recebem mais pacientes pelo WhatsApp, telefone ou indicacao?"
            ),
        )

    if asks_proposal:
        return (
            "clarification_cta",
            (
                "Posso montar uma proposta curta, sim. Para ela sair minimamente correta, me confirma uma coisa: "
                "o principal problema hoje esta em demora no WhatsApp, organizacao da agenda ou retorno de pacientes?"
            ),
        )

    if no_website_signal:
        return (
            "clarification_reply",
            (
                "Entendi. Se a clinica ainda nao tem um site bom, o melhor primeiro passo pode ser uma presenca local simples: "
                "site com servicos, mapa, WhatsApp e base de SEO para pacientes encontrarem e confiarem antes de chamar. "
                "Quer que eu te mostre esse caminho primeiro?"
            ),
        )

    if is_positive:
        return (
            "direct_demo_offer",
            "Boa. Posso te mostrar uma demo curta com o caminho WhatsApp, resposta, agenda e acompanhamento dos retornos?",
        )

    if is_decision_maker:
        if decision_pitch_sent or last_step in {"decision_maker_pitch", "direct_demo_offer"}:
            return (
                "clarification_cta",
                (
                    "Perfeito, entao falo direto contigo. O ponto principal e reduzir atraso no WhatsApp e dar mais controle sobre agenda e retornos. "
                    "Posso te mostrar uma demo curta desse fluxo?"
                ),
            )
        return (
            "decision_maker_pitch",
            (
                "Perfeito, entao falo direto contigo. Aqui e o time comercial da ClinicFlux AI. "
                "Ajudamos clinicas a organizar WhatsApp, agenda e retornos para a recepcao trabalhar com mais controle. "
                "Posso te mostrar uma demo curta desse fluxo?"
            ),
        )

    if reply_classification == "automatica":
        return "auto_reply_hold", "Tudo bem, vou aguardar uma pessoa da equipe retornar por aqui."
    if reply_classification == "recepcao":
        return (
            "reception_triage",
            (
                "Perfeito. Meu contato e comercial, nao e agendamento de paciente. "
                "Quem cuida do WhatsApp, agenda e retornos da clinica por ai?"
            ),
        )
    if reply_classification == "pediu_tempo":
        return "timing_followup", "Sem problema. Qual horario costuma ser melhor para eu te chamar sem atrapalhar?"
    if reply_classification == "fora_de_escopo":
        return "routing_followup", "Entendi. Qual seria o melhor canal ou pessoa para falar sobre atendimento e agendamentos da clinica?"
    if reply_classification == "bloqueio_acesso":
        return "access_request", "Tudo certo. Posso deixar um resumo bem curto para voce avaliar se vale encaminhar ao responsavel?"

    return (
        "clarification_reply",
        (
            "A ideia e ajudar a clinica a responder melhor no WhatsApp, organizar agenda e nao deixar retorno se perder. "
            "Quem costuma decidir essa parte por ai?"
        ),
    )


def _choose_admin_internal_sales_simulation_step(
    *,
    last_step: str,
    reply_classification: str,
    inbound_body: str,
    flow_config: dict,
) -> str:
    if _looks_like_contact_handoff(inbound_body):
        return "contact_handoff_ack"
    if reply_classification == "automatica":
        return "auto_reply_hold"
    if last_step == "reception_intro" and reply_classification == "recepcao" and _looks_like_ambiguous_help_reply(inbound_body):
        return "responsibility_check"

    class_to_step = flow_config.get("class_to_step") if isinstance(flow_config.get("class_to_step"), dict) else {}
    mapped_step = str(class_to_step.get(reply_classification) or SALES_OUTREACH_CLASS_TO_STEP_DEFAULTS.get(reply_classification) or "").strip()
    if mapped_step in SALES_OUTREACH_STEPS:
        return mapped_step

    if reply_classification == "gestor":
        return "decision_maker_pitch"
    if reply_classification == "recepcao":
        return "reception_triage"
    if reply_classification == "pediu_tempo":
        return "timing_followup"
    if reply_classification == "fora_de_escopo":
        return "routing_followup"
    if reply_classification == "bloqueio_acesso":
        return "access_request"
    return "clarification_reply"


def _existing_admin_internal_demo_url(db: Session, *, prospect: ProspectAccount) -> str | None:
    if not prospect.demo_tenant_id:
        return None
    try:
        raw_token = issue_demo_access(db, prospect, actor_id=None)
        return build_demo_login_url(_default_sales_outreach_base_url(), raw_token)
    except Exception:
        return None


def _build_admin_internal_sales_simulation_reply(
    db: Session,
    *,
    prospect: ProspectAccount,
    conversation: Conversation,
    step: str,
    recipient_name: str | None = None,
    inbound_body: str | None = None,
    reply_classification: str | None = None,
    last_step: str | None = None,
) -> tuple[str, str, dict | None, str | None]:
    flow_config = get_sales_outreach_flow_config(db)
    resolved_step = step if step in SALES_OUTREACH_STEPS else "clarification_reply"
    demo_login_url = None
    ai_review = None
    if inbound_body:
        resolved_step, message_text = _admin_internal_sales_simulation_contextual_reply(
            db,
            prospect=prospect,
            conversation=conversation,
            inbound_body=inbound_body,
            reply_classification=reply_classification or "",
            last_step=last_step or "",
        )
    else:
        message_text = _build_outreach_message(
            prospect,
            step=resolved_step,
            demo_login_url=None,
            recipient_name=recipient_name,
            flow_config=flow_config,
        )
        ai_review = _review_sales_outreach_outbound_with_ai(
            db,
            prospect=prospect,
            conversation=conversation,
            step=resolved_step,
            candidate_message=message_text,
            recipient_name=recipient_name,
        )
        if (
            resolved_step != "reception_intro"
            and isinstance(ai_review, dict)
            and ai_review.get("approved") is True
            and ai_review.get("final_message")
            and float(ai_review.get("confidence") or 0.0) >= _sales_outreach_ai_min_confidence()
        ):
            message_text = str(ai_review["final_message"]).strip()

    if _sales_outreach_violates_sender_persona(message_text):
        message_text = _sales_outreach_safe_context_reply(prospect, recipient_name=recipient_name)

    message_text = _admin_internal_sales_simulation_strip_unsafe_links(message_text)
    if _admin_internal_sales_simulation_seen_text(db, conversation=conversation, candidate_text=message_text):
        message_text = _admin_internal_sales_simulation_non_repeating_reply(inbound_body or "")

    if not message_text:
        message_text = _sales_outreach_safe_context_reply(prospect, recipient_name=recipient_name)
    return resolved_step, message_text, ai_review, demo_login_url


def simulate_admin_internal_whatsapp_inbound(
    db: Session,
    *,
    prospect: ProspectAccount,
    conversation: Conversation,
    body: str,
    actor_id: UUID | None,
) -> dict:
    clean_body = re.sub(r"\s+", " ", str(body or "").strip())
    if not clean_body:
        raise ApiError(status_code=400, code="ADM_INTERNAL_SIMULATION_EMPTY_MESSAGE", message="Digite uma mensagem para simular a resposta da clinica.")
    if len(clean_body) > 2000:
        raise ApiError(status_code=400, code="ADM_INTERNAL_SIMULATION_MESSAGE_TOO_LONG", message="A mensagem simulada deve ter no maximo 2000 caracteres.")

    tags = set(conversation.tags or [])
    if ADM_INTERNAL_WHATSAPP_SIMULATION_TAG not in tags:
        raise ApiError(
            status_code=400,
            code="ADM_INTERNAL_SIMULATION_REQUIRED",
            message="Abra o simulador interno antes de enviar mensagens simuladas.",
        )
    tags.add("adm_whatsapp_test_contact")
    tags.add(_prospect_outreach_tag(prospect.id))
    conversation.tags = sorted(tags)

    now = _now()
    inbound = Message(
        tenant_id=conversation.tenant_id,
        conversation_id=conversation.id,
        direction=MessageDirection.INBOUND.value,
        channel="whatsapp",
        sender_type="patient",
        body=clean_body,
        message_type="text",
        payload={
            "source": ADM_INTERNAL_WHATSAPP_SIMULATION_SOURCE,
            "simulated_clinic": True,
            "simulated_patient": True,
            "internal_delivery": True,
            "actor_id": str(actor_id) if actor_id else None,
            "note": "Mensagem inbound simulada pelo /adm. Nenhum WhatsApp oficial ou bridge foi acionado.",
        },
        status=MessageStatus.RECEIVED.value,
        sent_at=now,
    )
    db.add(inbound)
    db.flush()

    flow_config = get_sales_outreach_flow_config(db)
    classification_rules = flow_config.get("classification_rules") if isinstance(flow_config.get("classification_rules"), dict) else None
    reply_classification = classify_sales_outreach_reply(clean_body, rules=classification_rules)
    inbound_ai_review = _review_sales_outreach_inbound_with_ai(
        db,
        prospect=prospect,
        conversation=conversation,
        inbound_body=clean_body,
        heuristic_classification=reply_classification,
    )
    if (
        isinstance(inbound_ai_review, dict)
        and str(inbound_ai_review.get("classification") or "").strip() in SALES_OUTREACH_AI_ALLOWED_CLASSES
        and float(inbound_ai_review.get("confidence") or 0.0) >= _sales_outreach_ai_min_confidence()
    ):
        reply_classification = str(inbound_ai_review["classification"]).strip()
    if reply_classification != "automatica" and classify_sales_outreach_reply(clean_body) == "automatica":
        reply_classification = "automatica"

    last_step = _latest_admin_internal_sales_simulation_step(db, conversation=conversation)
    demo_login_url = None
    if _looks_like_outreach_opt_out(clean_body) or reply_classification == "sem_interesse":
        response_step = "stop_contact"
        response_text = (
            "Entendi, obrigado pelo retorno. Em uma conversa real, este seria o ponto de parar o contato e nao insistir. "
            "Como estamos no simulador interno, deixei isso registrado apenas neste teste."
        )
        outbound_ai_review = None
    else:
        response_step = _choose_admin_internal_sales_simulation_step(
            last_step=last_step,
            reply_classification=reply_classification,
            inbound_body=clean_body,
            flow_config=flow_config,
        )
        response_step, response_text, outbound_ai_review, demo_login_url = _build_admin_internal_sales_simulation_reply(
            db,
            prospect=prospect,
            conversation=conversation,
            step=response_step,
            recipient_name=prospect.owner_name or prospect.manager_name,
            inbound_body=clean_body,
            reply_classification=reply_classification,
            last_step=last_step,
        )

    outbound = Message(
        tenant_id=conversation.tenant_id,
        conversation_id=conversation.id,
        direction=MessageDirection.OUTBOUND.value,
        channel="whatsapp",
        sender_type="ai",
        body=response_text,
        message_type="text",
        payload={
            "source": ADM_INTERNAL_WHATSAPP_SIMULATION_SOURCE,
            "simulated_system_response": True,
            "internal_delivery": True,
            "reply_to_message_id": str(inbound.id),
            "step": response_step,
            "last_step": last_step,
            "reply_classification": reply_classification,
            "inbound_ai_review": jsonable_encoder(inbound_ai_review) if isinstance(inbound_ai_review, dict) else None,
            "ai_review": jsonable_encoder(outbound_ai_review) if isinstance(outbound_ai_review, dict) else None,
            "demo_login_url": demo_login_url,
            "note": "Resposta gerada internamente. Nenhum WhatsApp oficial, bridge ou outbox foi acionado.",
        },
        status=MessageStatus.SENT.value,
        sent_at=now,
        delivered_at=now,
    )
    db.add(outbound)

    conversation.last_message_at = _now()
    db.add(conversation)
    db.commit()
    db.refresh(inbound)
    db.refresh(outbound)
    db.refresh(conversation)

    return {
        "conversation": conversation,
        "inbound_message": inbound,
        "outbound_message": outbound,
        "reply_classification": reply_classification,
        "step": response_step,
        "internal_delivery": True,
    }


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
    outbox_metadata_patch: dict | None = None,
) -> dict:
    valid_steps = set(SALES_OUTREACH_STEPS)
    if step not in valid_steps:
        raise ApiError(status_code=400, code="SALES_OUTREACH_STEP_INVALID", message="Etapa comercial invalida")
    if prospect.do_not_contact:
        raise ApiError(
            status_code=409,
            code="SALES_OUTREACH_BLOCKED_OPT_OUT",
            message="Envio comercial bloqueado: a clinica recusou contato e esta marcada como nao contactar.",
        )

    sender_tenant = _sales_outreach_sender_tenant(db)
    conversation = _ensure_outreach_conversation(db, sender_tenant=sender_tenant, prospect=prospect)
    if _latest_sales_outreach_inbound_is_opt_out(db, conversation_id=conversation.id):
        prospect.do_not_contact = True
        prospect.status = "fechado_perdido"
        if not prospect.opt_out_at:
            prospect.opt_out_at = _now()
        _update_outreach_snapshot(
            prospect,
            patch={
                "automation_active": False,
                "automation_stopped_at": prospect.opt_out_at.isoformat(),
                "automation_stop_reason": "opt_out",
            },
        )
        db.add(prospect)
        db.flush()
        raise ApiError(
            status_code=409,
            code="SALES_OUTREACH_BLOCKED_OPT_OUT",
            message="Envio comercial bloqueado: a ultima resposta da clinica recusou o contato.",
        )
    raw_phone, _ = _prospect_outreach_destination(prospect)
    dispatch_transport = resolve_sales_outreach_transport()
    flow_config = get_sales_outreach_flow_config(db)

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
        flow_config=flow_config,
    )
    outbound_ai_review = _review_sales_outreach_outbound_with_ai(
        db,
        prospect=prospect,
        conversation=conversation,
        step=step,
        candidate_message=message_text,
        recipient_name=recipient_name,
    )
    if (
        step != "reception_intro"
        and isinstance(outbound_ai_review, dict)
        and outbound_ai_review.get("approved") is True
        and outbound_ai_review.get("final_message")
        and float(outbound_ai_review.get("confidence") or 0.0) >= _sales_outreach_ai_min_confidence()
    ):
        message_text = str(outbound_ai_review["final_message"]).strip()

    if _sales_outreach_violates_sender_persona(message_text):
        message_text = _sales_outreach_safe_context_reply(
            prospect,
            recipient_name=recipient_name or prospect.owner_name or prospect.manager_name,
        )

    if (
        isinstance(outbound_ai_review, dict)
        and step == "reception_intro"
    ):
        outbound_ai_review = {
            **outbound_ai_review,
            "final_message": message_text,
            "reason": (
                f"{str(outbound_ai_review.get('reason') or '').strip()} "
                "Reescrita por IA bloqueada no reception_intro; mantida a mensagem inicial original."
            ).strip(),
        }

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
            "ai_review": jsonable_encoder(outbound_ai_review) if isinstance(outbound_ai_review, dict) else None,
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
            "transport": dispatch_transport,
            "ai_review": jsonable_encoder(outbound_ai_review) if isinstance(outbound_ai_review, dict) else None,
            **(outbox_metadata_patch if isinstance(outbox_metadata_patch, dict) else {}),
        },
        immediate_dispatch=False if dispatch_transport == WHATSAPP_WEB_BRIDGE_TRANSPORT else immediate_dispatch,
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
    elif step == "decision_maker_pitch":
        if prospect.status in {"contato_iniciado", "respondeu", "decisor_identificado", "followup"}:
            prospect.status = "demo_enviada"
        if prospect.demo_status in {"rascunho", "criada", "expirada"}:
            prospect.demo_status = "enviada"
        prospect.demo_sent_at = prospect.demo_sent_at or _now()
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
        "dispatch_transport": dispatch_transport,
    }
    if extra_snapshot_patch:
        snapshot_patch.update(jsonable_encoder(extra_snapshot_patch))
    _update_outreach_snapshot(prospect, patch=snapshot_patch)
    add_timeline(
        db,
        prospect,
        event_type=f"prospect.outreach.{step}",
        event_label=f"{(SALES_OUTREACH_STEPS.get(step) or step)} enviada no WhatsApp",
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
    _apply_recalculated_score(db, prospect)
    try:
        from app.services.sales_outreach_automation_service import sync_batch_item_for_prospect

        sync_batch_item_for_prospect(db, prospect=prospect, message=outbound_message, conversation=conversation)
    except Exception:
        pass
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
        "transport": dispatch_transport,
    }


def send_no_site_outreach_stage(
    db: Session,
    *,
    prospect: ProspectAccount,
    stage: str,
    actor_id: UUID | None,
    commit: bool = True,
) -> dict:
    stage = str(stage or "").strip()
    if stage not in NO_SITE_OUTREACH_STAGES:
        raise ApiError(status_code=400, code="NO_SITE_OUTREACH_STAGE_INVALID", message="Etapa sem-site invalida.")
    if str(prospect.website or "").strip():
        raise ApiError(
            status_code=409,
            code="NO_SITE_OUTREACH_REQUIRES_WITHOUT_SITE",
            message="Envio sem-site bloqueado: esta clinica ja possui site cadastrado.",
        )
    if prospect.do_not_contact:
        raise ApiError(
            status_code=409,
            code="NO_SITE_OUTREACH_BLOCKED_OPT_OUT",
            message="Envio sem-site bloqueado: a clinica esta marcada como nao contactar.",
        )

    sender_tenant = _sales_outreach_sender_tenant(db)
    conversation = _ensure_outreach_conversation(db, sender_tenant=sender_tenant, prospect=prospect)
    if _latest_sales_outreach_inbound_is_opt_out(db, conversation_id=conversation.id):
        prospect.do_not_contact = True
        prospect.status = "fechado_perdido"
        prospect.opt_out_at = prospect.opt_out_at or _now()
        db.add(prospect)
        db.flush()
        raise ApiError(
            status_code=409,
            code="NO_SITE_OUTREACH_BLOCKED_OPT_OUT",
            message="Envio sem-site bloqueado: a ultima resposta da clinica recusou contato.",
        )

    no_site_snapshot = _no_site_outreach_snapshot(prospect)
    sent_stages = (
        dict(no_site_snapshot.get("sent_stages"))
        if isinstance(no_site_snapshot.get("sent_stages"), dict)
        else {}
    )
    if sent_stages.get(stage):
        raise ApiError(
            status_code=409,
            code="NO_SITE_OUTREACH_STAGE_ALREADY_SENT",
            message=f"{NO_SITE_OUTREACH_STAGE_LABELS[stage]} ja foi enviada para esta clinica.",
        )
    if stage == "second" and not sent_stages.get("first"):
        raise ApiError(
            status_code=409,
            code="NO_SITE_OUTREACH_FIRST_REQUIRED",
            message="Envie a primeira mensagem sem-site antes da segunda.",
        )
    human_reply_received = _sales_outreach_conversation_has_human_reply(db, conversation_id=conversation.id)
    if stage == "third":
        if not sent_stages.get("second"):
            raise ApiError(
                status_code=409,
                code="NO_SITE_OUTREACH_SECOND_REQUIRED",
                message="Envie a segunda mensagem sem-site antes da terceira.",
            )
        if not human_reply_received:
            raise ApiError(
                status_code=409,
                code="NO_SITE_OUTREACH_THIRD_REQUIRES_HUMAN_REPLY",
                message="Terceira mensagem sem-site bloqueada: so envie depois de uma resposta humana da clinica.",
            )

    config = get_no_site_outreach_flow_config(db)
    stage_key = f"{stage}_messages"
    messages = [str(item).strip() for item in config.get(stage_key, []) if str(item).strip()]
    if not messages:
        raise ApiError(
            status_code=422,
            code="NO_SITE_OUTREACH_MESSAGES_EMPTY",
            message="Configure as mensagens sem-site antes de enviar.",
        )
    variant_index = secrets.randbelow(len(messages))
    message_text = messages[variant_index]
    step = NO_SITE_OUTREACH_STAGE_TO_STEP[stage]
    raw_phone, _ = _prospect_outreach_destination(prospect)
    dispatch_transport = resolve_sales_outreach_transport()

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
            "flow": "no_site_outreach",
            "prospect_account_id": str(prospect.id),
            "step": step,
            "no_site_outreach_stage": stage,
            "variant_index": variant_index,
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
            "flow": "no_site_outreach",
            "prospect_account_id": str(prospect.id),
            "step": step,
            "no_site_outreach_stage": stage,
            "variant_index": variant_index,
            "outbound_message_id": str(outbound_message.id),
            "transport": dispatch_transport,
        },
        immediate_dispatch=False if dispatch_transport == WHATSAPP_WEB_BRIDGE_TRANSPORT else None,
        commit=False,
    )

    if outbox.status in {OutboxStatus.FAILED.value, OutboxStatus.DEAD_LETTER.value}:
        failed_at = _now()
        _update_no_site_outreach_snapshot(
            prospect,
            patch={
                "last_stage": stage,
                "last_attempted_at": failed_at.isoformat(),
                "last_dispatch_status": outbox.status,
                "last_dispatch_error": outbox.last_error,
                "last_outbox_id": str(outbox.id),
            },
        )
        db.add(prospect)
        db.commit()
        raise ApiError(
            status_code=400,
            code="NO_SITE_OUTREACH_DISPATCH_FAILED",
            message=outbox.last_error or "Falha ao enviar mensagem sem-site pelo WhatsApp.",
        )

    now_value = _now()
    outbound_message.payload = {
        **(outbound_message.payload if isinstance(outbound_message.payload, dict) else {}),
        "queued_outbox_id": str(outbox.id),
    }
    db.add(outbound_message)

    if not prospect.first_contact_at:
        prospect.first_contact_at = now_value
    if not prospect.first_contact_channel:
        prospect.first_contact_channel = "whatsapp_no_site_outreach"
    if stage == "first" and prospect.status in {"novo", "pesquisado"}:
        prospect.status = "contato_iniciado"
    elif stage in {"second", "third"} and prospect.status in {"novo", "pesquisado", "contato_iniciado"}:
        prospect.status = "followup"
    prospect.last_activity_at = now_value

    sent_stages[stage] = {
        "sent_at": now_value.isoformat(),
        "message_text": message_text,
        "variant_index": variant_index,
        "outbox_id": str(outbox.id),
        "outbound_message_id": str(outbound_message.id),
    }
    _update_no_site_outreach_snapshot(
        prospect,
        patch={
            "last_stage": stage,
            "last_step": step,
            "last_sent_at": now_value.isoformat(),
            "last_message_text": message_text,
            "last_variant_index": variant_index,
            "last_dispatch_status": outbox.status,
            "last_outbox_id": str(outbox.id),
            "sender_tenant_id": str(sender_tenant.id),
            "conversation_id": str(conversation.id),
            "dispatch_transport": dispatch_transport,
            "human_reply_received": human_reply_received,
            "sent_stages": sent_stages,
        },
    )
    _update_outreach_snapshot(
        prospect,
        patch={
            "last_step": step,
            "last_sent_at": now_value.isoformat(),
            "last_outbox_id": str(outbox.id),
            "last_dispatch_status": outbox.status,
            "sender_tenant_id": str(sender_tenant.id),
            "conversation_id": str(conversation.id),
            "dispatch_transport": dispatch_transport,
        },
    )
    add_timeline(
        db,
        prospect,
        event_type=f"prospect.outreach.{step}",
        event_label=f"{NO_SITE_OUTREACH_STAGE_LABELS[stage]} enviada no WhatsApp",
        actor_id=actor_id,
        actor_type="admin",
        payload={
            "destination": raw_phone,
            "sender_tenant_id": str(sender_tenant.id),
            "conversation_id": str(conversation.id),
            "outbox_id": str(outbox.id),
            "message_text": message_text,
            "stage": stage,
            "variant_index": variant_index,
        },
    )
    db.add(prospect)
    _apply_recalculated_score(db, prospect)
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
        "demo_login_url": None,
        "video_url": None,
        "sender_tenant_id": sender_tenant.id,
        "conversation_id": conversation.id,
        "outbound_message_id": outbound_message.id,
        "transport": dispatch_transport,
    }


def claim_prospect_with_affiliate_first_message(
    db: Session,
    *,
    prospect_id: UUID,
    affiliate_user_id: UUID,
    message_index: int,
) -> dict:
    config = get_affiliate_first_message_config(db, user_id=affiliate_user_id)
    messages = list(config.get("messages") or [])
    if message_index < 0 or message_index >= len(messages):
        raise ApiError(
            status_code=422,
            code="AFFILIATE_FIRST_MESSAGE_INDEX_INVALID",
            message="Escolha uma das 5 mensagens iniciais configuradas.",
        )
    message_text = str(messages[message_index] or "").strip()
    if not message_text:
        raise ApiError(
            status_code=422,
            code="AFFILIATE_FIRST_MESSAGE_EMPTY",
            message="A mensagem inicial escolhida esta vazia.",
        )

    prospect = db.scalar(
        select(ProspectAccount)
        .where(ProspectAccount.id == prospect_id)
        .with_for_update()
    )
    if not prospect:
        raise ApiError(status_code=404, code="PROSPECT_NOT_FOUND", message="Clinica nao encontrada.")
    if prospect.affiliate_owner_user_id:
        raise ApiError(
            status_code=409,
            code="AFFILIATE_PROSPECT_ALREADY_CLAIMED",
            message="Esta clinica acabou de ser assumida por outro afiliado. Atualize para receber a proxima.",
        )
    if prospect.first_contact_at or str(prospect.status or "").strip() not in {"novo", "pesquisado"}:
        raise ApiError(
            status_code=409,
            code="AFFILIATE_PROSPECT_ALREADY_USED",
            message="Esta clinica ja teve uso comercial e nao esta mais disponivel para afiliados.",
        )
    if prospect.do_not_contact:
        raise ApiError(
            status_code=409,
            code="AFFILIATE_PROSPECT_DO_NOT_CONTACT",
            message="Esta clinica esta marcada como nao contactar.",
        )

    raw_phone, _ = _prospect_outreach_destination(prospect)
    sender_tenant = _sales_outreach_sender_tenant(db)
    conversation = _ensure_outreach_conversation(db, sender_tenant=sender_tenant, prospect=prospect)
    previous_outbound = db.scalar(
        select(Message.id)
        .where(
            Message.conversation_id == conversation.id,
            Message.direction == MessageDirection.OUTBOUND.value,
        )
        .limit(1)
    )
    if previous_outbound:
        raise ApiError(
            status_code=409,
            code="AFFILIATE_PROSPECT_ALREADY_USED",
            message="Esta clinica ja recebeu contato comercial e nao esta mais disponivel.",
        )

    dispatch_transport = resolve_sales_outreach_transport()
    outbound_message = Message(
        tenant_id=sender_tenant.id,
        conversation_id=conversation.id,
        direction=MessageDirection.OUTBOUND.value,
        channel="whatsapp",
        sender_type="user",
        sender_user_id=affiliate_user_id,
        body=message_text,
        message_type="text",
        payload={
            "source": "sales_outreach",
            "flow": "affiliate_first_contact",
            "prospect_account_id": str(prospect.id),
            "step": "affiliate_first",
            "affiliate_user_id": str(affiliate_user_id),
            "variant_index": message_index,
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
            "flow": "affiliate_first_contact",
            "prospect_account_id": str(prospect.id),
            "step": "affiliate_first",
            "affiliate_user_id": str(affiliate_user_id),
            "variant_index": message_index,
            "outbound_message_id": str(outbound_message.id),
            "transport": dispatch_transport,
        },
        immediate_dispatch=False if dispatch_transport == WHATSAPP_WEB_BRIDGE_TRANSPORT else None,
        commit=False,
    )
    if outbox.status in {OutboxStatus.FAILED.value, OutboxStatus.DEAD_LETTER.value}:
        db.rollback()
        raise ApiError(
            status_code=400,
            code="AFFILIATE_FIRST_MESSAGE_DISPATCH_FAILED",
            message=outbox.last_error or "Nao foi possivel colocar a primeira mensagem na fila do WhatsApp.",
        )

    now_value = _now()
    prospect.affiliate_owner_user_id = affiliate_user_id
    prospect.affiliate_claimed_at = now_value
    prospect.first_contact_at = now_value
    prospect.first_contact_channel = "whatsapp_affiliate_first_contact"
    prospect.status = "contato_iniciado"
    prospect.last_activity_at = now_value
    prospect.updated_by = affiliate_user_id
    snapshot = dict(prospect.proposal_snapshot or {})
    snapshot["affiliate_outreach"] = {
        "affiliate_user_id": str(affiliate_user_id),
        "claimed_at": now_value.isoformat(),
        "first_message_sent_at": now_value.isoformat(),
        "first_message_text": message_text,
        "first_message_index": message_index,
        "conversation_id": str(conversation.id),
        "outbox_id": str(outbox.id),
        "outbound_message_id": str(outbound_message.id),
        "dispatch_transport": dispatch_transport,
    }
    prospect.proposal_snapshot = snapshot
    _update_outreach_snapshot(
        prospect,
        patch={
            "last_step": "affiliate_first",
            "last_sent_at": now_value.isoformat(),
            "last_outbox_id": str(outbox.id),
            "last_dispatch_status": outbox.status,
            "sender_tenant_id": str(sender_tenant.id),
            "conversation_id": str(conversation.id),
            "dispatch_transport": dispatch_transport,
            "affiliate_user_id": str(affiliate_user_id),
        },
    )
    outbound_message.payload = {
        **(outbound_message.payload if isinstance(outbound_message.payload, dict) else {}),
        "queued_outbox_id": str(outbox.id),
    }
    db.add(outbound_message)
    db.add(prospect)
    add_timeline(
        db,
        prospect,
        event_type="prospect.affiliate.claimed",
        event_label="Clinica assumida por afiliado apos primeira mensagem",
        actor_id=affiliate_user_id,
        actor_type="affiliate",
        payload={
            "affiliate_user_id": str(affiliate_user_id),
            "conversation_id": str(conversation.id),
            "outbox_id": str(outbox.id),
            "message_index": message_index,
            "message_text": message_text,
        },
    )
    _apply_recalculated_score(db, prospect)
    db.commit()
    db.refresh(prospect)
    db.refresh(outbound_message)
    return {
        "prospect": serialize_prospect(db, prospect),
        "step": "affiliate_first",
        "destination": raw_phone,
        "message_text": message_text,
        "demo_login_url": None,
        "video_url": None,
        "sender_tenant_id": sender_tenant.id,
        "conversation_id": conversation.id,
        "outbound_message_id": outbound_message.id,
        "transport": dispatch_transport,
    }


def prepare_affiliate_whatsapp_contact(
    db: Session,
    *,
    prospect_id: UUID,
    affiliate_user_id: UUID,
    stage: str,
    message_index: int,
    consent_exclusive: bool,
    consent_responsible_use: bool,
    human_reply_confirmed: bool = False,
) -> dict:
    if not consent_exclusive or not consent_responsible_use:
        raise ApiError(
            status_code=422,
            code="AFFILIATE_CONTACT_CONSENT_REQUIRED",
            message="Confirme os dois combinados antes de abrir o WhatsApp.",
        )
    if stage not in {"first", "second", "third"}:
        raise ApiError(
            status_code=422,
            code="AFFILIATE_CONTACT_STAGE_INVALID",
            message="Escolha o primeiro, segundo ou terceiro contato.",
        )
    if stage == "third" and not human_reply_confirmed:
        raise ApiError(
            status_code=422,
            code="AFFILIATE_THIRD_CONTACT_REPLY_REQUIRED",
            message="O terceiro contato so pode ser usado depois de uma resposta humana da clinica.",
        )

    config = get_affiliate_contact_message_config(db, user_id=affiliate_user_id)
    messages = list(config.get(f"{stage}_messages") or [])
    if message_index < 0 or message_index >= len(messages):
        raise ApiError(
            status_code=422,
            code="AFFILIATE_CONTACT_MESSAGE_INDEX_INVALID",
            message="Escolha uma das 5 mensagens configuradas para este contato.",
        )
    message_text = str(messages[message_index] or "").strip()
    if not message_text:
        raise ApiError(
            status_code=422,
            code="AFFILIATE_CONTACT_MESSAGE_EMPTY",
            message="A mensagem escolhida esta vazia.",
        )

    prospect = db.scalar(
        select(ProspectAccount)
        .where(ProspectAccount.id == prospect_id)
        .with_for_update()
    )
    if not prospect:
        raise ApiError(status_code=404, code="PROSPECT_NOT_FOUND", message="Clinica nao encontrada.")
    if prospect.affiliate_owner_user_id and prospect.affiliate_owner_user_id != affiliate_user_id:
        raise ApiError(
            status_code=409,
            code="AFFILIATE_PROSPECT_ALREADY_CLAIMED",
            message="Esta clinica pertence a outro afiliado e nao esta mais disponivel.",
        )
    if prospect.do_not_contact:
        raise ApiError(
            status_code=409,
            code="AFFILIATE_PROSPECT_DO_NOT_CONTACT",
            message="Esta clinica esta marcada como nao contactar.",
        )

    claimed_now = prospect.affiliate_owner_user_id is None
    if claimed_now:
        if stage != "first":
            raise ApiError(
                status_code=409,
                code="AFFILIATE_FIRST_CONTACT_REQUIRED",
                message="Assuma a clinica com uma mensagem de primeiro contato antes dos acompanhamentos.",
            )
        if prospect.first_contact_at or str(prospect.status or "").strip() not in {"novo", "pesquisado"}:
            raise ApiError(
                status_code=409,
                code="AFFILIATE_PROSPECT_ALREADY_USED",
                message="Esta clinica ja teve uso comercial e nao esta mais disponivel para afiliados.",
            )

    raw_phone, normalized_phone = _prospect_outreach_destination(prospect)
    now_value = _now()
    if claimed_now:
        prospect.affiliate_owner_user_id = affiliate_user_id
        prospect.affiliate_claimed_at = now_value
        prospect.first_contact_at = now_value
        prospect.first_contact_channel = "whatsapp_affiliate_manual"
        prospect.status = "contato_iniciado"

    snapshot = dict(prospect.proposal_snapshot or {})
    affiliate_outreach = (
        dict(snapshot.get("affiliate_outreach") or {})
        if isinstance(snapshot.get("affiliate_outreach"), dict)
        else {}
    )
    history = (
        list(affiliate_outreach.get("contact_history") or [])
        if isinstance(affiliate_outreach.get("contact_history"), list)
        else []
    )
    prepared_entry = {
        "prepared_at": now_value.isoformat(),
        "stage": stage,
        "message_index": message_index,
        "message_text": message_text,
        "human_reply_confirmed": bool(human_reply_confirmed) if stage == "third" else None,
    }
    history.append(prepared_entry)
    affiliate_outreach.update(
        {
            "affiliate_user_id": str(affiliate_user_id),
            "claimed_at": (
                prospect.affiliate_claimed_at.isoformat()
                if prospect.affiliate_claimed_at
                else affiliate_outreach.get("claimed_at")
            ),
            "last_contact_prepared_at": now_value.isoformat(),
            "last_contact_stage": stage,
            "last_message_index": message_index,
            "last_message_text": message_text,
            "contact_history": history[-100:],
        }
    )
    snapshot["affiliate_outreach"] = affiliate_outreach
    prospect.proposal_snapshot = snapshot
    prospect.last_activity_at = now_value
    prospect.updated_by = affiliate_user_id
    _update_outreach_snapshot(
        prospect,
        patch={
            "last_prepared_step": f"affiliate_{stage}",
            "last_prepared_at": now_value.isoformat(),
            "affiliate_user_id": str(affiliate_user_id),
            "dispatch_transport": "whatsapp_deep_link",
        },
    )
    add_timeline(
        db,
        prospect,
        event_type="prospect.affiliate.contact_prepared",
        event_label=f"{humanize_affiliate_contact_stage(stage)} contato preparado no WhatsApp",
        actor_id=affiliate_user_id,
        actor_type="affiliate",
        payload={
            "affiliate_user_id": str(affiliate_user_id),
            "stage": stage,
            "message_index": message_index,
            "message_text": message_text,
            "claimed_now": claimed_now,
            "destination": raw_phone,
        },
    )
    db.add(prospect)
    _apply_recalculated_score(db, prospect)
    whatsapp_url = f"https://api.whatsapp.com/send/?{urlencode({'phone': normalized_phone, 'text': message_text})}"
    db.commit()
    db.refresh(prospect)
    return {
        "prospect": serialize_prospect(db, prospect),
        "stage": stage,
        "message_index": message_index,
        "destination": raw_phone,
        "message_text": message_text,
        "whatsapp_url": whatsapp_url,
        "claimed_now": claimed_now,
    }


def humanize_affiliate_contact_stage(stage: str) -> str:
    return {
        "first": "Primeiro",
        "second": "Segundo",
        "third": "Terceiro",
    }.get(stage, "Contato")


def _no_site_outreach_has_human_reply(db: Session, prospect: ProspectAccount, snapshot: dict) -> bool:
    if bool(snapshot.get("human_reply_received")):
        return True
    conversation_id = _sales_outreach_uuid_from_value(snapshot.get("conversation_id"))
    if not conversation_id:
        return False
    return _sales_outreach_conversation_has_human_reply(db, conversation_id=conversation_id)


def _no_site_outreach_temperature_rank(value: str | None) -> int:
    ranks = {"muito_quente": 4, "quente": 3, "morno": 2, "frio": 1}
    return ranks.get(str(value or "").strip(), 0)


def _no_site_outreach_stage_eligibility(db: Session, prospect: ProspectAccount, *, stage: str) -> tuple[bool, str | None]:
    if stage not in NO_SITE_OUTREACH_STAGES:
        return False, "invalid_stage"
    if str(prospect.website or "").strip():
        return False, "with_site"
    if prospect.do_not_contact:
        return False, "do_not_contact"
    if not normalize_phone(prospect.whatsapp_phone or prospect.phone):
        return False, "phone_invalid"
    if str(prospect.status or "").strip() in {"fechado_ganho", "fechado_perdido"}:
        return False, "closed"

    snapshot = _no_site_outreach_snapshot(prospect)
    sent_stages = dict(snapshot.get("sent_stages") or {}) if isinstance(snapshot.get("sent_stages"), dict) else {}
    if sent_stages.get(stage):
        return False, "stage_already_sent"
    if stage == "first":
        return True, None
    if stage == "second":
        return (True, None) if sent_stages.get("first") else (False, "first_required")
    if stage == "third":
        if not sent_stages.get("second"):
            return False, "second_required"
        if not _no_site_outreach_has_human_reply(db, prospect, snapshot):
            return False, "human_reply_required"
        return True, None
    return False, "invalid_stage"


def list_no_site_outreach_eligible(
    db: Session,
    *,
    stage: str,
    limit: int = 50,
) -> dict:
    stage = str(stage or "").strip()
    if stage not in NO_SITE_OUTREACH_STAGES:
        raise ApiError(status_code=400, code="NO_SITE_OUTREACH_STAGE_INVALID", message="Etapa sem-site invalida.")

    preview_limit = min(max(int(limit or 50), 1), 200)
    prospects = db.execute(
        select(ProspectAccount)
        .where(
            ProspectAccount.do_not_contact.is_(False),
            or_(ProspectAccount.whatsapp_phone.is_not(None), ProspectAccount.phone.is_not(None)),
            or_(ProspectAccount.website.is_(None), func.length(func.trim(ProspectAccount.website)) == 0),
            ProspectAccount.status.not_in(["fechado_ganho", "fechado_perdido"]),
        )
        .order_by(ProspectAccount.score.desc(), ProspectAccount.created_at.asc())
    ).scalars().all()

    eligible: list[ProspectAccount] = []
    blocked_summary: dict[str, int] = {}
    for prospect in prospects:
        is_eligible, reason = _no_site_outreach_stage_eligibility(db, prospect, stage=stage)
        if is_eligible:
            eligible.append(prospect)
            continue
        reason_key = reason or "blocked"
        blocked_summary[reason_key] = blocked_summary.get(reason_key, 0) + 1

    eligible.sort(
        key=lambda item: (_no_site_outreach_temperature_rank(item.temperature), item.score, item.created_at.timestamp()),
        reverse=True,
    )
    return {
        "stage": stage,
        "eligible_count": len(eligible),
        "preview": [serialize_prospect(db, prospect, include_children=False) for prospect in eligible[:preview_limit]],
        "blocked_summary": blocked_summary,
        "limit": preview_limit,
    }


def send_no_site_outreach_bulk(
    db: Session,
    *,
    stage: str,
    actor_id: UUID | None,
    limit: int = 200,
) -> dict:
    stage = str(stage or "").strip()
    if stage not in NO_SITE_OUTREACH_STAGES:
        raise ApiError(status_code=400, code="NO_SITE_OUTREACH_STAGE_INVALID", message="Etapa sem-site invalida.")

    batch_limit = min(max(int(limit or 200), 1), 500)
    eligible_payload = list_no_site_outreach_eligible(db, stage=stage, limit=batch_limit)
    prospects = [
        db.get(ProspectAccount, UUID(str(item["id"])))
        for item in eligible_payload.get("preview", [])
        if item.get("id")
    ]

    queued: list[dict] = []
    errors: list[dict] = []
    for prospect in [item for item in prospects if item is not None]:
        try:
            result = send_no_site_outreach_stage(
                db,
                prospect=prospect,
                stage=stage,
                actor_id=actor_id,
                commit=True,
            )
            queued.append(
                {
                    "prospect": result["prospect"],
                    "step": result["step"],
                    "conversation_id": result["conversation_id"],
                    "outbound_message_id": result["outbound_message_id"],
                    "transport": result.get("transport"),
                }
            )
        except ApiError as exc:
            errors.append(
                {
                    "prospect_id": prospect.id,
                    "clinic_name": prospect.clinic_name,
                    "code": exc.code,
                    "message": exc.message,
                }
            )
        except Exception as exc:
            errors.append(
                {
                    "prospect_id": prospect.id,
                    "clinic_name": prospect.clinic_name,
                    "code": "NO_SITE_OUTREACH_BULK_ITEM_FAILED",
                    "message": str(exc)[:1000],
                }
            )

    return {
        "stage": stage,
        "eligible_count": eligible_payload["eligible_count"],
        "requested_count": min(batch_limit, eligible_payload["eligible_count"]),
        "queued_count": len(queued),
        "skipped_count": max(0, min(batch_limit, eligible_payload["eligible_count"]) - len(queued)),
        "errors": errors,
        "queued": queued,
        "blocked_summary": eligible_payload.get("blocked_summary", {}),
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

    if not prospect.demo_tenant_id or str(prospect.demo_status or "").strip() not in {"criada", "enviada", "acessada"}:
        generate_demo(db, prospect, actor_id=actor_id, base_url=base_url)
        db.refresh(prospect)

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

    outreach = _outreach_snapshot(prospect)
    body_preview = re.sub(r"\s+", " ", str(message.body or "").strip())[:500]
    message_payload = message.payload if isinstance(message.payload, dict) else {}
    shared_contact_name = str(message_payload.get("bridge_shared_contact_name") or "").strip()
    shared_contact_phone = str(message_payload.get("bridge_shared_contact_phone") or "").strip()
    text_forwarded_contact_name, text_forwarded_contact_phone = _extract_forwarded_contact_from_text(body_preview)
    awaiting_contact_handoff = str(outreach.get("automation_stop_reason") or "").strip() == "awaiting_contact_handoff" or str(outreach.get("last_step") or "").strip() == "contact_handoff_ack"
    if not awaiting_contact_handoff and not text_forwarded_contact_phone:
        awaiting_contact_handoff = _conversation_has_recent_contact_handoff_hint(
            db,
            conversation_id=conversation.id,
            current_message_id=message.id,
        )
    if not text_forwarded_contact_phone and awaiting_contact_handoff:
        text_forwarded_contact_name, text_forwarded_contact_phone = _extract_contact_phone_and_name_from_text(body_preview)
    prospect.last_activity_at = _now()
    if prospect.status in {"novo", "pesquisado", "contato_iniciado", "decisor_identificado", "demo_enviada", "followup"}:
        prospect.status = "respondeu"
    flow_config = get_sales_outreach_flow_config(db)
    classification_rules = flow_config.get("classification_rules") if isinstance(flow_config.get("classification_rules"), dict) else None
    class_to_step = flow_config.get("class_to_step") if isinstance(flow_config.get("class_to_step"), dict) else {}
    reply_classification = classify_sales_outreach_reply(body_preview, rules=classification_rules)
    inbound_ai_review = _review_sales_outreach_inbound_with_ai(
        db,
        prospect=prospect,
        conversation=conversation,
        inbound_body=body_preview,
        heuristic_classification=reply_classification,
    )
    if (
        isinstance(inbound_ai_review, dict)
        and str(inbound_ai_review.get("classification") or "").strip() in SALES_OUTREACH_AI_ALLOWED_CLASSES
        and float(inbound_ai_review.get("confidence") or 0.0) >= _sales_outreach_ai_min_confidence()
    ):
        reply_classification = str(inbound_ai_review["classification"]).strip()
    if reply_classification != "automatica" and classify_sales_outreach_reply(body_preview) == "automatica":
        reply_classification = "automatica"
    _update_outreach_snapshot(
        prospect,
        patch={
            "last_reply_at": prospect.last_activity_at.isoformat(),
            "last_reply_preview": body_preview,
            "conversation_id": str(conversation.id),
            "last_reply_classification": reply_classification,
            "last_reply_ai_review": jsonable_encoder(inbound_ai_review) if isinstance(inbound_ai_review, dict) else None,
        },
    )
    no_site_snapshot = _no_site_outreach_snapshot(prospect)
    if no_site_snapshot:
        _update_no_site_outreach_snapshot(
            prospect,
            patch={
                "last_reply_at": prospect.last_activity_at.isoformat(),
                "last_reply_preview": body_preview,
                "last_reply_classification": reply_classification,
                "last_reply_ai_review": jsonable_encoder(inbound_ai_review) if isinstance(inbound_ai_review, dict) else None,
                "human_reply_received": reply_classification != "automatica",
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
            "classification": reply_classification,
            "ai_review": jsonable_encoder(inbound_ai_review) if isinstance(inbound_ai_review, dict) else None,
        },
    )
    if not shared_contact_phone and text_forwarded_contact_phone:
        restart_result = _restart_sales_outreach_for_forwarded_contact(
            db,
            prospect=prospect,
            forwarded_contact_name=text_forwarded_contact_name,
            forwarded_contact_phone=text_forwarded_contact_phone,
        )
        _update_outreach_snapshot(
            prospect,
            patch={
                "shared_contact_name": text_forwarded_contact_name or None,
                "shared_contact_phone": text_forwarded_contact_phone,
                "forwarded_contact_restart": restart_result,
            },
        )
        db.add(prospect)
        db.flush()
        return
    if shared_contact_name or shared_contact_phone:
        _update_outreach_snapshot(
            prospect,
            patch={
                "automation_active": False,
                "automation_stopped_at": prospect.last_activity_at.isoformat(),
                "automation_stop_reason": "contact_shared",
                "shared_contact_name": shared_contact_name or None,
                "shared_contact_phone": shared_contact_phone or None,
            },
        )
        add_timeline(
            db,
            prospect,
            event_type="prospect.outreach.contact_shared",
            event_label="Clinica compartilhou um contato para continuidade",
            actor_type="system",
            payload={
                "conversation_id": str(conversation.id),
                "message_id": str(message.id),
                "shared_contact_name": shared_contact_name or None,
                "shared_contact_phone": shared_contact_phone or None,
                "body_preview": body_preview,
            },
        )
        handoff_result = {}
        if shared_contact_name and shared_contact_phone:
            try:
                handoff_result = _handoff_shared_contact_to_sales_outreach(
                    db,
                    source_prospect=prospect,
                    shared_contact_name=shared_contact_name,
                    shared_contact_phone=shared_contact_phone,
                )
                add_timeline(
                    db,
                    prospect,
                    event_type="prospect.outreach.contact_handoff_started",
                    event_label="Novo contato comercial iniciado a partir do WhatsApp",
                    actor_type="system",
                    payload={
                        "conversation_id": str(conversation.id),
                        "message_id": str(message.id),
                        "shared_contact_name": shared_contact_name or None,
                        "shared_contact_phone": shared_contact_phone or None,
                        "handoff_result": handoff_result,
                        "body_preview": body_preview,
                    },
                )
            except Exception as e:
                logging.warning(
                    "Could not start outreach handoff for shared contact %s from %s: %s",
                    shared_contact_name,
                    prospect.clinic_name,
                    e,
                )
        _update_outreach_snapshot(
            prospect,
            patch={
                "last_reply_at": prospect.last_activity_at.isoformat(),
                "last_reply_preview": body_preview,
                "conversation_id": str(conversation.id),
                "last_reply_classification": reply_classification,
                "last_reply_ai_review": jsonable_encoder(inbound_ai_review) if isinstance(inbound_ai_review, dict) else None,
            },
        )
        _apply_recalculated_score(db, prospect)
        try:
            from app.services.sales_outreach_automation_service import sync_batch_item_for_prospect

            sync_batch_item_for_prospect(db, prospect=prospect, message=message, conversation=conversation)
        except Exception:
            pass
        db.add(prospect)
        return

    if reply_classification == "gestor" and bool(outreach.get("automation_active")):
        prospect.status = "decisor_identificado"
    elif reply_classification == "pediu_tempo" and prospect.status in {"contato_iniciado", "respondeu"}:
        prospect.status = "followup"
    if _looks_like_outreach_opt_out(body_preview):
        prospect.do_not_contact = True
        prospect.status = "fechado_perdido"
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
        _apply_recalculated_score(db, prospect)
        try:
            from app.services.sales_outreach_automation_service import sync_batch_item_for_prospect

            sync_batch_item_for_prospect(db, prospect=prospect, message=message, conversation=conversation)
        except Exception:
            pass
        db.add(prospect)
        return

    if reply_classification == "automatica":
        _update_outreach_snapshot(
            prospect,
            patch={
                "automation_active": False,
                "automation_stopped_at": prospect.last_activity_at.isoformat(),
                "automation_stop_reason": "awaiting_human_reply",
            },
        )
        add_timeline(
            db,
            prospect,
            event_type="prospect.outreach.automation_paused",
            event_label="Automacao comercial pausada por resposta automatica",
            actor_type="system",
            payload={
                "conversation_id": str(conversation.id),
                "classification": reply_classification,
                "stop_reason": "awaiting_human_reply",
            },
        )
        db.add(prospect)
        _apply_recalculated_score(db, prospect)
        try:
            from app.services.sales_outreach_automation_service import sync_batch_item_for_prospect

            sync_batch_item_for_prospect(db, prospect=prospect, message=message, conversation=conversation)
        except Exception:
            pass
        return

    outreach = _outreach_snapshot(prospect)
    last_step = str(outreach.get("last_step") or "").strip()
    should_advance = bool(outreach.get("automation_active")) and last_step in {
        "reception_intro",
        "responsibility_check",
        "reception_triage",
        "reception_cta",
        "clarification_reply",
        "clarification_cta",
        "access_request",
    }
    if should_advance:
        next_step = None
        snapshot_patch: dict[str, object] = {"automation_active": True}
        stop_reason = None
        ambiguous_help_reply = _looks_like_ambiguous_help_reply(body_preview)
        contact_handoff_reply = _looks_like_contact_handoff(body_preview)

        if contact_handoff_reply:
            next_step = "contact_handoff_ack"
            snapshot_patch["automation_active"] = False
            stop_reason = "awaiting_contact_handoff"

        if next_step:
            pass
        elif last_step == "reception_intro":
            if reply_classification in class_to_step and reply_classification != "automatica":
                next_step = str(class_to_step.get(reply_classification) or "").strip() or None
            if reply_classification == "recepcao" and ambiguous_help_reply:
                next_step = "responsibility_check"
            elif reply_classification == "gestor":
                next_step = next_step or "decision_maker_pitch"
            elif reply_classification == "recepcao":
                next_step = next_step or "reception_triage"
            elif reply_classification == "duvida":
                next_step = next_step or "clarification_reply"
            elif reply_classification == "pediu_tempo":
                next_step = next_step or "timing_followup"
                snapshot_patch["automation_active"] = False
                stop_reason = "requested_better_time"
            elif reply_classification == "fora_de_escopo":
                next_step = next_step or "routing_followup"
                snapshot_patch["automation_active"] = False
                stop_reason = "reroute_requested"
            elif reply_classification == "bloqueio_acesso":
                next_step = next_step or "access_request"
                snapshot_patch["automation_active"] = False
                stop_reason = "access_blocked"
            elif reply_classification == "automatica":
                snapshot_patch["automation_active"] = False
                stop_reason = "awaiting_human_reply"
        elif last_step == "responsibility_check":
            if reply_classification == "gestor":
                next_step = "decision_maker_pitch"
            elif reply_classification == "recepcao":
                next_step = "reception_triage"
            elif reply_classification == "duvida":
                next_step = "clarification_reply"
            elif reply_classification == "pediu_tempo":
                next_step = "timing_followup"
                snapshot_patch["automation_active"] = False
                stop_reason = "requested_better_time"
            elif reply_classification == "fora_de_escopo":
                next_step = "routing_followup"
                snapshot_patch["automation_active"] = False
                stop_reason = "reroute_requested"
            elif reply_classification == "bloqueio_acesso":
                next_step = "access_request"
                snapshot_patch["automation_active"] = False
                stop_reason = "access_blocked"
            elif reply_classification == "automatica":
                snapshot_patch["automation_active"] = False
                stop_reason = "awaiting_human_reply"
        elif last_step == "reception_triage":
            if reply_classification == "gestor":
                next_step = "decision_maker_pitch"
            elif reply_classification in {"recepcao", "duvida"}:
                next_step = "reception_cta"
                snapshot_patch["automation_active"] = False
                stop_reason = "awaiting_internal_forward"
            elif reply_classification == "pediu_tempo":
                next_step = "timing_followup"
                snapshot_patch["automation_active"] = False
                stop_reason = "requested_better_time"
            elif reply_classification == "fora_de_escopo":
                next_step = "routing_followup"
                snapshot_patch["automation_active"] = False
                stop_reason = "reroute_requested"
            elif reply_classification == "bloqueio_acesso":
                next_step = "access_request"
                snapshot_patch["automation_active"] = False
                stop_reason = "access_blocked"
            elif reply_classification == "automatica":
                snapshot_patch["automation_active"] = False
                stop_reason = "awaiting_human_reply"
        elif last_step == "clarification_reply":
            if reply_classification == "gestor":
                next_step = "decision_maker_pitch"
            elif reply_classification in {"duvida", "recepcao"}:
                next_step = "clarification_cta"
                snapshot_patch["automation_active"] = False
                stop_reason = "clarification_sent"
            elif reply_classification == "pediu_tempo":
                next_step = "timing_followup"
                snapshot_patch["automation_active"] = False
                stop_reason = "requested_better_time"
            elif reply_classification == "fora_de_escopo":
                next_step = "routing_followup"
                snapshot_patch["automation_active"] = False
                stop_reason = "reroute_requested"
            elif reply_classification == "bloqueio_acesso":
                next_step = "access_request"
                snapshot_patch["automation_active"] = False
                stop_reason = "access_blocked"
            elif reply_classification == "automatica":
                snapshot_patch["automation_active"] = False
                stop_reason = "awaiting_human_reply"
        elif last_step == "access_request":
            if reply_classification == "gestor":
                next_step = "decision_maker_pitch"
            elif reply_classification == "recepcao":
                next_step = "reception_triage"
            elif reply_classification == "duvida":
                next_step = "clarification_reply"
            elif reply_classification == "pediu_tempo":
                next_step = "timing_followup"
                snapshot_patch["automation_active"] = False
                stop_reason = "requested_better_time"
            elif reply_classification == "fora_de_escopo":
                next_step = "routing_followup"
                snapshot_patch["automation_active"] = False
                stop_reason = "reroute_requested"
            elif reply_classification == "bloqueio_acesso":
                next_step = "access_request"
                snapshot_patch["automation_active"] = False
                stop_reason = "access_blocked"
            elif reply_classification == "automatica":
                snapshot_patch["automation_active"] = False
                stop_reason = "awaiting_human_reply"
        elif last_step == "reception_cta":
            if reply_classification == "gestor":
                next_step = "decision_maker_pitch"
            elif reply_classification in {"recepcao", "duvida", "bloqueio_acesso"}:
                next_step = "direct_demo_offer"
                snapshot_patch["automation_active"] = False
                stop_reason = "direct_demo_offered"
            elif reply_classification == "pediu_tempo":
                next_step = "timing_followup"
                snapshot_patch["automation_active"] = False
                stop_reason = "requested_better_time"
            elif reply_classification == "fora_de_escopo":
                next_step = "routing_followup"
                snapshot_patch["automation_active"] = False
                stop_reason = "reroute_requested"
            elif reply_classification == "automatica":
                snapshot_patch["automation_active"] = False
                stop_reason = "awaiting_human_reply"
        elif last_step == "clarification_cta":
            if reply_classification == "gestor":
                next_step = "decision_maker_pitch"
            elif reply_classification in {"recepcao", "duvida", "bloqueio_acesso"}:
                next_step = "direct_demo_offer"
                snapshot_patch["automation_active"] = False
                stop_reason = "direct_demo_offered"
            elif reply_classification == "pediu_tempo":
                next_step = "timing_followup"
                snapshot_patch["automation_active"] = False
                stop_reason = "requested_better_time"
            elif reply_classification == "fora_de_escopo":
                next_step = "routing_followup"
                snapshot_patch["automation_active"] = False
                stop_reason = "reroute_requested"
            elif reply_classification == "automatica":
                snapshot_patch["automation_active"] = False
                stop_reason = "awaiting_human_reply"

        if next_step:
            send_sales_outreach_step(
                db,
                prospect=prospect,
                step=next_step,
                actor_id=None,
                base_url=_default_sales_outreach_base_url(),
                recipient_name=prospect.owner_name or prospect.manager_name,
                commit=False,
                immediate_dispatch=False,
                extra_snapshot_patch=snapshot_patch,
                outbox_metadata_patch={
                    "priority_reason": "inbound_reply",
                    "priority_order_at": (_utc_datetime(message.created_at) or _now()).isoformat(),
                    "trigger_inbound_message_id": str(message.id),
                },
            )
            if next_step == "contact_handoff_ack":
                _update_outreach_snapshot(
                    prospect,
                    patch={
                        "automation_active": False,
                        "automation_stopped_at": prospect.last_activity_at.isoformat(),
                        "automation_stop_reason": "awaiting_contact_handoff",
                    },
                )

        if reply_classification == "gestor" and str(settings.sales_outreach_video_url or "").strip():
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
                outbox_metadata_patch={
                    "priority_reason": "inbound_reply",
                    "priority_order_at": (_utc_datetime(message.created_at) or _now()).isoformat(),
                    "trigger_inbound_message_id": str(message.id),
                },
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
                payload={"conversation_id": str(conversation.id), "classification": reply_classification},
            )
        if stop_reason:
            _update_outreach_snapshot(
                prospect,
                patch={
                    "automation_active": False,
                    "automation_stopped_at": prospect.last_activity_at.isoformat(),
                    "automation_stop_reason": stop_reason,
                },
            )
            add_timeline(
                db,
                prospect,
                event_type="prospect.outreach.automation_paused",
                event_label="Automacao comercial pausada apos classificacao da resposta",
                actor_type="system",
                payload={
                    "conversation_id": str(conversation.id),
                    "classification": reply_classification,
                    "stop_reason": stop_reason,
                },
            )
    db.add(prospect)
    _apply_recalculated_score(db, prospect)
    try:
        from app.services.sales_outreach_automation_service import sync_batch_item_for_prospect

        sync_batch_item_for_prospect(db, prospect=prospect, message=message, conversation=conversation)
    except Exception:
        pass


def create_prospect(
    db: Session,
    payload,
    *,
    actor_id: UUID | None,
    affiliate_owner_user_id: UUID | None = None,
) -> ProspectAccount:
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

    sanitized_snapshot = _sanitize_demo_configuration_snapshot(
        db,
        snapshot=payload.proposal_snapshot,
        current_prospect_id=None,
    )

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
        proposal_snapshot=sanitized_snapshot,
        affiliate_owner_user_id=affiliate_owner_user_id,
        affiliate_claimed_at=_now() if affiliate_owner_user_id else None,
        created_by=actor_id,
        updated_by=actor_id,
        tenant_seed_key=_friendly_prospect_key(
            db,
            clinic_name=payload.clinic_name,
            phone=payload.phone,
            whatsapp_phone=payload.whatsapp_phone,
        ),
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
    services_payload = data.pop("services", None)
    if "proposal_snapshot" in data:
        data["proposal_snapshot"] = _sanitize_demo_configuration_snapshot(
            db,
            snapshot=data.get("proposal_snapshot"),
            current_prospect_id=prospect.id,
        )
    for key, value in data.items():
        if key == "email" and value is not None:
            value = str(value)
        setattr(prospect, key, value)
    prospect.updated_by = actor_id
    db.flush()
    if services_payload is not None:
        db.execute(delete(ProspectService).where(ProspectService.prospect_account_id == prospect.id))
        for service in services_payload:
            service_name = str(service.get("service_name") or "").strip()
            if len(service_name) < 2:
                continue
            db.add(
                ProspectService(
                    prospect_account_id=prospect.id,
                    service_name=service_name,
                    category=str(service.get("category") or "").strip() or None,
                    duration_minutes=max(15, min(int(service.get("duration_minutes") or 60), 480)),
                    price_range=str(service.get("price_range") or "").strip() or None,
                    description=str(service.get("description") or "").strip() or service_name,
                )
            )
        db.flush()
    if prospect.demo_tenant_id:
        if services_payload is not None:
            demo_units = db.execute(select(Unit).where(Unit.tenant_id == prospect.demo_tenant_id)).scalars().all()
            services = _ensure_demo_services(db, prospect)
            _sync_demo_service_catalog(db, tenant_id=prospect.demo_tenant_id, services=services, demo_units=demo_units)
        ensure_demo_intake_config_ready(db, tenant_id=prospect.demo_tenant_id, prospect=prospect)
        ensure_demo_ai_autoresponder_ready(db, tenant_id=prospect.demo_tenant_id, prospect=prospect)
        ensure_demo_branding_ready(db, tenant_id=prospect.demo_tenant_id, prospect=prospect)
    if prospect.do_not_contact and not prospect.opt_out_at:
        prospect.opt_out_at = _now()
    add_timeline(db, prospect, event_type="prospect.updated", event_label="Dados da clinica atualizados", actor_id=actor_id, actor_type="admin", payload=data)
    db.add(prospect)
    db.commit()
    db.refresh(prospect)
    return prospect


def create_or_reuse_public_site_demo(
    db: Session,
    *,
    clinic_name: str,
    owner_name: str,
    phone: str,
    template_slug: str | None = None,
    base_url: str,
) -> dict:
    from app.schemas.admin_sales import ProspectCreate

    normalized_clinic_name = str(clinic_name or "").strip()
    normalized_owner_name = str(owner_name or "").strip()
    normalized_phone = str(phone or "").strip()
    normalized_template_slug = _normalize_site_template_slug(template_slug)
    demo_snapshot = _public_site_demo_snapshot(
        template_slug=normalized_template_slug,
        base_url=base_url,
        clinic_name=normalized_clinic_name,
        whatsapp=normalized_phone,
    )

    prospect = _find_public_site_prospect(
        db,
        clinic_name=normalized_clinic_name,
        phone=normalized_phone,
    )
    status = "reused" if prospect else "created"

    if not prospect:
        payload = ProspectCreate(
            clinic_name=normalized_clinic_name,
            owner_name=normalized_owner_name,
            phone=normalized_phone,
            whatsapp_phone=normalized_phone,
            notes=PUBLIC_SITE_QUICK_DEMO_NOTE,
            lead_source=PUBLIC_SITE_QUICK_DEMO_LEAD_SOURCE,
            first_contact_channel=PUBLIC_SITE_QUICK_DEMO_CHANNEL,
            first_contact_at=_now(),
            uses_whatsapp_heavily=True,
            tags=list(PUBLIC_SITE_QUICK_DEMO_TAGS),
            proposal_snapshot=demo_snapshot,
        )
        prospect = create_prospect(db, payload, actor_id=None)
        add_timeline(
            db,
            prospect,
            event_type="public.quick_demo.requested",
            event_label="Demo rapida solicitada pela home publica",
            actor_type="system",
            payload={"source": "landing_page", "template_slug": normalized_template_slug},
        )
        db.commit()
        db.refresh(prospect)
    else:
        merged_snapshot = {
            **(prospect.proposal_snapshot or {}),
            **demo_snapshot,
        }
        prospect.owner_name = prospect.owner_name or normalized_owner_name
        prospect.phone = prospect.phone or normalized_phone
        prospect.whatsapp_phone = prospect.whatsapp_phone or normalized_phone
        prospect.notes = prospect.notes or PUBLIC_SITE_QUICK_DEMO_NOTE
        prospect.lead_source = prospect.lead_source or PUBLIC_SITE_QUICK_DEMO_LEAD_SOURCE
        prospect.first_contact_channel = prospect.first_contact_channel or PUBLIC_SITE_QUICK_DEMO_CHANNEL
        prospect.first_contact_at = prospect.first_contact_at or _now()
        prospect.uses_whatsapp_heavily = True
        prospect.tags = sorted(set(prospect.tags or []).union(PUBLIC_SITE_QUICK_DEMO_TAGS))
        prospect.proposal_snapshot = _sanitize_demo_configuration_snapshot(
            db,
            snapshot=merged_snapshot,
            current_prospect_id=prospect.id,
        )
        add_timeline(
            db,
            prospect,
            event_type="public.quick_demo.requested",
            event_label="Demo rapida solicitada pela home publica",
            actor_type="system",
            payload={"source": "landing_page", "template_slug": normalized_template_slug},
        )
        db.add(prospect)
        db.commit()
        db.refresh(prospect)

    result = generate_demo(
        db,
        prospect,
        actor_id=None,
        base_url=base_url,
    )
    result["status"] = status
    result["selected_template_slug"] = normalized_template_slug
    result["site_template_preview_url"] = (
        build_site_template_preview_url(
            base_url,
            normalized_template_slug,
            clinic_name=prospect.clinic_name,
            city=prospect.city,
            whatsapp=prospect.whatsapp_phone or prospect.phone,
        )
        if normalized_template_slug
        else None
    )
    return result


def _apply_recalculated_score(db: Session, prospect: ProspectAccount) -> ProspectAccount:
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

    outreach = _outreach_snapshot(prospect)
    last_reply_classification = str(outreach.get("last_reply_classification") or "").strip()
    stop_reason = str(outreach.get("automation_stop_reason") or "").strip()
    if prospect.first_contact_at:
        points["contato_comercial_iniciado"] = max(points.get("contato_comercial_iniciado", 0), 5)
    if prospect.status == "respondeu":
        points["respondeu_no_whatsapp"] = 12
    elif prospect.status == "decisor_identificado":
        points["decisor_identificado"] = 22
    elif prospect.status == "demo_enviada":
        points["demo_enviada_status"] = 28
    elif prospect.status == "demo_acessada":
        points["demo_acessada_status"] = 45
    elif prospect.status == "followup":
        points["followup_comercial"] = 34
    elif prospect.status == "reuniao_marcada":
        points["reuniao_marcada"] = 58

    if prospect.demo_tenant_id:
        points["demo_gerada"] = 10
    if prospect.demo_status == "enviada":
        points["demo_enviada"] = max(points.get("demo_enviada", 0), 18)
    elif prospect.demo_status == "acessada":
        points["demo_acessada"] = max(points.get("demo_acessada", 0), 40)

    if last_reply_classification == "gestor":
        points["reply_gestor"] = 18
    elif last_reply_classification == "recepcao":
        points["reply_recepcao"] = 8
    elif last_reply_classification == "duvida":
        points["reply_duvida"] = 9
    elif last_reply_classification == "pediu_tempo":
        points["reply_pediu_tempo"] = 6

    if stop_reason == "sequence_completed":
        points["fluxo_completo"] = 16
    if prospect.do_not_contact:
        points["opt_out"] = -25

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
    return prospect


def recalculate_score(db: Session, prospect: ProspectAccount) -> ProspectAccount:
    _apply_recalculated_score(db, prospect)
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
        "Gere um rascunho JSON para configurar uma demo de SaaS para clinicas. "
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
    service_names = [service.service_name for service in services] or ["Avaliacao inicial", "Consulta de retorno", "Procedimento estetico"]
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
        ("Avaliacao inicial", "Consulta", 45),
        ("Consulta de retorno", "Retorno", 30),
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


def _upsert_setting(db: Session, *, tenant_id: UUID, key: str, value) -> None:
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
    demo_background = _demo_background_settings(prospect)
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
        "branding.theme": {
            **DEMO_BRANDING_THEME_DEFAULTS,
            "demo_background_image_url": demo_background["background_image_url"],
            "demo_background_opacity": demo_background["background_image_opacity"],
        },
        "branding.logo_data_url": None,
        "intake.config": _demo_intake_settings(db, prospect),
    }
    for key, value in settings_payloads.items():
        _upsert_setting(db, tenant_id=tenant_id, key=key, value=value)


def ensure_demo_ai_autoresponder_ready(
    db: Session,
    *,
    tenant_id: UUID,
    prospect: ProspectAccount | None = None,
) -> bool:
    linked_prospect = prospect or db.scalar(
        select(ProspectAccount).where(ProspectAccount.demo_tenant_id == tenant_id).limit(1)
    )
    desired_demo_ai = _demo_ai_settings(linked_prospect) if linked_prospect else dict(DEMO_AI_DEFAULT_SETTINGS)

    config_item = db.scalar(select(Setting).where(Setting.tenant_id == tenant_id, Setting.key == "ai_autoresponder.global"))
    current_config = dict(config_item.value) if config_item and isinstance(config_item.value, dict) else {}
    channels = current_config.get("channels")
    if not isinstance(channels, dict):
        channels = {}

    desired_enabled = bool(desired_demo_ai["enabled"])
    desired_whatsapp_enabled = bool(desired_demo_ai["whatsapp_enabled"])
    desired_max_consecutive = int(
        desired_demo_ai["max_consecutive_auto_replies"] or DEMO_AI_DEFAULT_SETTINGS["max_consecutive_auto_replies"]
    )
    config_changed = bool(
        config_item is None
        or bool(current_config.get("enabled")) != desired_enabled
        or bool(channels.get("whatsapp", False)) != desired_whatsapp_enabled
        or int(current_config.get("max_consecutive_auto_replies") or DEMO_AI_DEFAULT_SETTINGS["max_consecutive_auto_replies"])
        != desired_max_consecutive
    )
    if config_changed:
        merged_config = {
            **current_config,
            "enabled": desired_enabled,
            "channels": {**channels, "whatsapp": desired_whatsapp_enabled},
            "max_consecutive_auto_replies": desired_max_consecutive,
        }
        _upsert_setting(db, tenant_id=tenant_id, key="ai_autoresponder.global", value=merged_config)

    desired_conversation_state = desired_enabled and desired_whatsapp_enabled
    conversations_changed = False
    demo_conversations = db.execute(
        select(Conversation).where(
            Conversation.tenant_id == tenant_id,
            Conversation.channel == "whatsapp",
        )
    ).scalars().all()
    for conversation in demo_conversations:
        if conversation.ai_autoresponder_enabled is not desired_conversation_state:
            conversation.ai_autoresponder_enabled = desired_conversation_state
            db.add(conversation)
            conversations_changed = True

    return config_changed or conversations_changed


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
    ensure_demo_ai_autoresponder_ready(db, tenant_id=prospect.demo_tenant_id, prospect=prospect)
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
    if prospect.demo_tenant_id and _demo_has_expired(prospect):
        cleanup_demo_resources(
            db,
            prospect=prospect,
            reason="expired",
            actor_id=actor_id,
        )

    if prospect.demo_tenant_id:
        services = _ensure_demo_services(db, prospect)
        demo_tenant = db.get(Tenant, prospect.demo_tenant_id)
        demo_units = db.execute(select(Unit).where(Unit.tenant_id == prospect.demo_tenant_id)).scalars().all()
        demo_user = db.get(User, prospect.demo_user_id) if prospect.demo_user_id else None
        professionals = db.execute(select(Professional).where(Professional.tenant_id == prospect.demo_tenant_id)).scalars().all()
        _sync_demo_service_catalog(db, tenant_id=prospect.demo_tenant_id, services=services, demo_units=demo_units)
        ensure_demo_intake_config_ready(db, tenant_id=prospect.demo_tenant_id, prospect=prospect)
        ensure_demo_ai_autoresponder_ready(db, tenant_id=prospect.demo_tenant_id, prospect=prospect)
        ensure_demo_branding_ready(db, tenant_id=prospect.demo_tenant_id, prospect=prospect)
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
            checklist["branding_applied"] = True
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
        demo_booking_slug = _resolve_demo_booking_slug(db, prospect=prospect)
        return {
            "prospect": prospect,
            "access_token": raw_token,
            "demo_login_url": build_demo_login_url(base_url, raw_token),
            "demo_booking_path": build_demo_booking_path(demo_booking_slug) if demo_booking_slug else None,
            "demo_booking_url": build_demo_booking_url(base_url, demo_booking_slug) if demo_booking_slug else None,
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
        demo_email = f"demo+{slug_candidate}@demo.clinicfluxai.com.br"
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
    ensure_demo_intake_config_ready(db, tenant_id=tenant.id, prospect=prospect)
    ensure_demo_ai_autoresponder_ready(db, tenant_id=tenant.id, prospect=prospect)
    ensure_demo_branding_ready(db, tenant_id=tenant.id, prospect=prospect)
    add_timeline(db, prospect, event_type="demo.created", event_label="Demo personalizada gerada", actor_id=actor_id, actor_type="admin", payload={"tenant_id": str(tenant.id)})
    db.add(prospect)
    db.commit()
    db.refresh(prospect)
    raw_token = issue_demo_access(db, prospect, actor_id=actor_id)
    demo_booking_slug = _resolve_demo_booking_slug(db, prospect=prospect)
    return {
        "prospect": prospect,
        "access_token": raw_token,
        "demo_login_url": build_demo_login_url(base_url, raw_token),
        "demo_booking_path": build_demo_booking_path(demo_booking_slug) if demo_booking_slug else None,
        "demo_booking_url": build_demo_booking_url(base_url, demo_booking_slug) if demo_booking_slug else None,
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
    service_names = [service.service_name for service in services] or ["Avaliacao inicial"]
    unit_professionals = [professional for professional in professionals if professional.unit_id == unit.id] or professionals
    tenant_timezone = _resolve_demo_timezone(tenant.timezone)
    showcase_week_start = _next_demo_showcase_week_start(_now().astimezone(tenant_timezone))
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
        starts_at = _build_demo_showcase_slot_start(
            showcase_day_local=showcase_day,
            preferred_time_text=str(spec["time"]),
            tenant_timezone=tenant_timezone,
            unit=unit,
            professional=professional,
        )
        ends_at = starts_at + timedelta(minutes=60)
        starts_at_local = starts_at.astimezone(tenant_timezone)
        weekday_label = weekday_labels[starts_at_local.weekday()]
        date_label = starts_at_local.strftime("%d/%m/%Y")
        time_label = starts_at_local.strftime("%H:%M")

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
    if _demo_has_expired(prospect):
        cleanup_demo_resources(
            db,
            prospect=prospect,
            reason="expired",
            actor_id=actor_id,
        )
        db.commit()
        raise ApiError(
            status_code=400,
            code="DEMO_EXPIRED",
            message="Esta demo expirou e foi removida. Gere uma nova demo para continuar.",
        )
    if not prospect.demo_tenant_id or not prospect.demo_user_id:
        raise ApiError(status_code=400, code="DEMO_NOT_CREATED", message="Gere a demo antes de emitir acesso")
    raw_token = _friendly_demo_access_token(db, prospect)
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


def _resolve_demo_whatsapp_link(db: Session, *, tenant_id: UUID) -> str | None:
    account = resolve_demo_assigned_platform_account(db, tenant_id=tenant_id)
    if not account:
        account = db.scalar(
            select(WhatsAppAccount)
            .where(
                WhatsAppAccount.tenant_id == tenant_id,
                WhatsAppAccount.is_active.is_(True),
            )
            .order_by(WhatsAppAccount.created_at.desc())
            .limit(1)
        )
    if account:
        phone_number_id = str(account.phone_number_id or "").strip()
        if not phone_number_id.startswith("demo_virtual_"):
            link = _build_demo_whatsapp_link(account.display_phone or phone_number_id)
            if link:
                return link

    prospect = db.scalar(select(ProspectAccount).where(ProspectAccount.demo_tenant_id == tenant_id).limit(1))
    if not prospect:
        return None
    return _build_demo_whatsapp_link(prospect.test_phone_number)


def _resolve_demo_entry_metadata(db: Session, *, prospect: ProspectAccount) -> dict[str, str | None]:
    intake_settings = _demo_intake_settings(db, prospect)
    link_flow = intake_settings.get("link_flow") if isinstance(intake_settings.get("link_flow"), dict) else {}
    cta_mode = str(link_flow.get("cta_mode") or "whatsapp_redirect").strip()
    mode = str(intake_settings.get("mode") or "official_api").strip()
    tenant = db.get(Tenant, prospect.demo_tenant_id) if prospect.demo_tenant_id else None

    if mode in {"link_flow", "hybrid"} and cta_mode == "webchat" and tenant and tenant.slug:
        return {
            "entry_channel": "webchat",
            "public_entry_path": f"/agendar/{tenant.slug}",
        }

    return {
        "entry_channel": "whatsapp",
        "public_entry_path": None,
    }


def resolve_demo_runtime_entry_context(
    db: Session,
    *,
    tenant_id: UUID | None,
) -> dict[str, str | None]:
    empty_context = {
        "demo_test_phone_number": None,
        "demo_whatsapp_link": None,
        "demo_entry_channel": None,
        "demo_public_entry_path": None,
    }
    if not tenant_id:
        return empty_context

    prospect = db.scalar(select(ProspectAccount).where(ProspectAccount.demo_tenant_id == tenant_id).limit(1))
    if not prospect:
        return empty_context

    desired_config = _demo_intake_settings(db, prospect)
    existing_setting = db.scalar(
        select(Setting).where(
            Setting.tenant_id == tenant_id,
            Setting.key == "intake.config",
        )
    )
    existing_value = existing_setting.value if existing_setting and isinstance(existing_setting.value, dict) else None
    desired_background = _demo_background_settings(prospect)
    existing_theme = db.scalar(
        select(Setting).where(
            Setting.tenant_id == tenant_id,
            Setting.key == "branding.theme",
        )
    )
    current_background = _current_demo_background_from_theme(
        existing_theme.value if existing_theme and isinstance(existing_theme.value, dict) else None
    )
    needs_commit = False
    if existing_value != desired_config:
        _upsert_setting(db, tenant_id=tenant_id, key="intake.config", value=desired_config)
        needs_commit = True
    if current_background != desired_background:
        ensure_demo_branding_ready(db, tenant_id=tenant_id, prospect=prospect)
        needs_commit = True
    if needs_commit:
        db.commit()

    entry_metadata = _resolve_demo_entry_metadata(db, prospect=prospect)
    return {
        "demo_test_phone_number": prospect.test_phone_number,
        "demo_whatsapp_link": _resolve_demo_whatsapp_link(db, tenant_id=tenant_id),
        "demo_entry_channel": entry_metadata["entry_channel"],
        "demo_public_entry_path": entry_metadata["public_entry_path"],
    }


def redeem_demo_token(db: Session, *, token: str, session_id: str | None = None) -> dict:
    token_hash = sha256_text(token)
    prospect = db.scalar(select(ProspectAccount).where(ProspectAccount.demo_access_token_hash == token_hash))
    if not prospect or not prospect.demo_user_id or not prospect.demo_tenant_id:
        raise ApiError(status_code=401, code="DEMO_TOKEN_INVALID", message="Acesso de demo invalido")
    if prospect.demo_access_revoked_at:
        raise ApiError(status_code=401, code="DEMO_TOKEN_REVOKED", message="Acesso de demo revogado")
    if _demo_has_expired(prospect):
        cleanup_demo_resources(
            db,
            prospect=prospect,
            reason="expired",
            actor_id=None,
        )
        db.commit()
        raise ApiError(
            status_code=401,
            code="DEMO_EXPIRED",
            message="Esta demo expirou e foi removida automaticamente.",
        )
    if prospect.demo_access_token_expires_at and prospect.demo_access_token_expires_at < _now():
        prospect.demo_access_revoked_at = _now()
        db.add(prospect)
        db.commit()
        raise ApiError(
            status_code=401,
            code="DEMO_TOKEN_EXPIRED",
            message="O link de acesso da demo expirou. Gere um novo link para continuar.",
        )

    user = db.get(User, prospect.demo_user_id)
    if not user or not user.is_active:
        raise ApiError(status_code=401, code="DEMO_USER_INVALID", message="Usuario de demo invalido")
    ensure_demo_intake_config_ready(db, tenant_id=prospect.demo_tenant_id, prospect=prospect)
    ensure_demo_ai_autoresponder_ready(db, tenant_id=prospect.demo_tenant_id, prospect=prospect)
    ensure_demo_branding_ready(db, tenant_id=prospect.demo_tenant_id, prospect=prospect)
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
    entry_metadata = _resolve_demo_entry_metadata(db, prospect=prospect)
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "expires_in": settings.api_access_token_expire_minutes * 60,
        "demo_test_phone_number": prospect.test_phone_number,
        "demo_whatsapp_link": _resolve_demo_whatsapp_link(db, tenant_id=prospect.demo_tenant_id),
        "demo_target_path": "/conversas",
        "demo_entry_channel": entry_metadata["entry_channel"],
        "demo_public_entry_path": entry_metadata["public_entry_path"],
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
    normalized_email = email.lower().strip()
    user = db.scalar(select(User).where(User.email == normalized_email))
    if not user or not verify_password(password, user.hashed_password):
        raise ApiError(status_code=401, code="AUTH_INVALID_CREDENTIALS", message="Credenciais invalidas")
    if not user.is_active:
        raise ApiError(status_code=403, code="AUTH_USER_DISABLED", message="Usuario inativo")
    roles = _user_role_names(db, user.id)
    if _adm_bootstrap_credentials_configured():
        bootstrap_email = settings.adm_bootstrap_email.lower().strip()
        if normalized_email != bootstrap_email and ADM_AFFILIATE_ROLE_NAME not in set(roles):
            raise ApiError(status_code=401, code="AUTH_INVALID_CREDENTIALS", message="Credenciais invalidas")
    if not {"admin_platform", "sales_admin", "sales_viewer", ADM_AFFILIATE_ROLE_NAME}.intersection(set(roles)):
        raise ApiError(status_code=403, code="ADM_FORBIDDEN", message="Usuario sem permissao para /adm")
    user.last_login_at = _now()
    db.add(user)
    db.commit()
    return build_admin_auth_payload(user=user, roles=roles)


def change_initial_admin_password(db: Session, *, user: User, current_password: str, new_password: str) -> None:
    managed_email = (settings.adm_bootstrap_email or "").lower().strip()
    if _adm_bootstrap_credentials_configured() and user.email.lower().strip() == managed_email:
        raise ApiError(
            status_code=400,
            code="ADM_ENV_MANAGED_CREDENTIALS",
            message="As credenciais do /adm sao gerenciadas por ADM_BOOTSTRAP_EMAIL e ADM_BOOTSTRAP_PASSWORD",
        )
    if not verify_password(current_password, user.hashed_password):
        raise ApiError(status_code=401, code="AUTH_INVALID_CREDENTIALS", message="Senha atual invalida")
    validate_password_strength(new_password)
    permissions = dict(user.page_permissions or {})
    permissions.pop("adm_initial_password", None)
    user.page_permissions = permissions
    user.hashed_password = hash_password(new_password)
    db.add(user)
    db.commit()


def overview(db: Session, *, affiliate_owner_user_id: UUID | None = None) -> dict:
    owner_filter = (
        [ProspectAccount.affiliate_owner_user_id == affiliate_owner_user_id]
        if affiliate_owner_user_id
        else []
    )
    total = db.scalar(select(func.count(ProspectAccount.id)).where(*owner_filter)) or 0
    demos_created = db.scalar(
        select(func.count(ProspectAccount.id)).where(
            *owner_filter,
            ProspectAccount.demo_tenant_id.is_not(None),
        )
    ) or 0
    demos_accessed = db.scalar(
        select(func.count(ProspectAccount.id)).where(
            *owner_filter,
            ProspectAccount.demo_first_login_at.is_not(None),
        )
    ) or 0
    hot_leads = db.scalar(
        select(func.count(ProspectAccount.id)).where(
            *owner_filter,
            ProspectAccount.temperature.in_(["quente", "muito_quente"]),
        )
    ) or 0
    meetings = db.scalar(
        select(func.count(ProspectAccount.id)).where(
            *owner_filter,
            ProspectAccount.status == "reuniao_marcada",
        )
    ) or 0
    won = db.scalar(
        select(func.count(ProspectAccount.id)).where(
            *owner_filter,
            ProspectAccount.status == "fechado_ganho",
        )
    ) or 0
    recent_query = select(ProspectTimelineEvent)
    if affiliate_owner_user_id:
        recent_query = recent_query.join(
            ProspectAccount,
            ProspectAccount.id == ProspectTimelineEvent.prospect_account_id,
        ).where(ProspectAccount.affiliate_owner_user_id == affiliate_owner_user_id)
    recent = db.execute(
        recent_query.order_by(ProspectTimelineEvent.created_at.desc()).limit(12)
    ).scalars().all()
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

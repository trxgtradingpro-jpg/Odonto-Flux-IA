from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models import (
    Appointment,
    AppointmentEvent,
    AuditLog,
    Automation,
    Campaign,
    Conversation,
    Document,
    DocumentVersion,
    Lead,
    LeadSource,
    Message,
    Patient,
    PatientTag,
    Role,
    Tenant,
    TenantPlan,
    Unit,
    User,
    UserRole,
    WhatsAppAccount,
    WhatsAppTemplate,
)
from app.models.enums import MessageDirection

ROLE_PERMISSIONS = {
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
    "manager": [
        "dashboard.read",
        "patients.manage",
        "leads.manage",
        "conversations.manage",
        "appointments.manage",
        "automations.manage",
        "campaigns.manage",
        "documents.manage",
        "audit.read",
    ],
    "receptionist": [
        "dashboard.read",
        "patients.manage",
        "leads.manage",
        "conversations.manage",
        "appointments.manage",
        "documents.read",
    ],
    "analyst": [
        "dashboard.read",
        "leads.manage",
        "campaigns.manage",
        "automations.read",
    ],
    "admin_platform": [
        "platform.admin",
        "tenants.manage",
        "plans.manage",
        "feature_flags.manage",
    ],
}


def upsert_roles(db):
    role_map = {}
    for role_name, permissions in ROLE_PERMISSIONS.items():
        item = db.scalar(select(Role).where(Role.name == role_name))
        scope = "platform" if role_name == "admin_platform" else "tenant"
        if not item:
            item = Role(name=role_name, description=f"Role {role_name}", scope=scope, permissions=permissions)
            db.add(item)
        else:
            item.permissions = permissions
            item.scope = scope
            db.add(item)
        db.flush()
        role_map[role_name] = item
    return role_map


def upsert_plans(db):
    plans = {
        "starter": {"name": "Starter", "max_users": 8, "max_units": 2, "max_monthly_messages": 4000, "price_cents": 39900},
        "growth": {"name": "Growth", "max_users": 30, "max_units": 10, "max_monthly_messages": 20000, "price_cents": 129900},
        "enterprise": {"name": "Enterprise", "max_users": 200, "max_units": 80, "max_monthly_messages": 200000, "price_cents": 499900},
    }
    plan_map = {}
    for code, data in plans.items():
        item = db.scalar(select(TenantPlan).where(TenantPlan.code == code))
        if not item:
            item = TenantPlan(code=code, currency="BRL", features={"billing_placeholder": True}, **data)
            db.add(item)
        else:
            for key, value in data.items():
                setattr(item, key, value)
            item.features = {"billing_placeholder": True}
            db.add(item)
        db.flush()
        plan_map[code] = item
    return plan_map


def create_tenant_if_missing(db, *, slug: str, legal_name: str, trade_name: str, plan_id):
    item = db.scalar(select(Tenant).where(Tenant.slug == slug))
    if not item:
        item = Tenant(
            slug=slug,
            legal_name=legal_name,
            trade_name=trade_name,
            plan_id=plan_id,
            subscription_status="active",
            trial_ends_at=datetime.now(UTC) + timedelta(days=14),
        )
        db.add(item)
        db.flush()
    return item


def create_unit_if_missing(db, tenant_id, code, name, phone):
    item = db.scalar(select(Unit).where(Unit.tenant_id == tenant_id, Unit.code == code))
    if not item:
        item = Unit(
            tenant_id=tenant_id,
            code=code,
            name=name,
            phone=phone,
            email=f"{code.lower()}@clinic.com",
            address={"city": "Sao Paulo", "state": "SP"},
            working_hours={"seg-sex": "08:00-18:00", "sab": "08:00-12:00"},
        )
        db.add(item)
        db.flush()
    return item


def create_user_if_missing(db, *, tenant_id, email, full_name, role_names, role_map):
    user = db.scalar(select(User).where(User.email == email))
    if not user:
        user = User(
            tenant_id=tenant_id,
            email=email,
            full_name=full_name,
            phone="5511999999999",
            hashed_password=hash_password("Odonto@123"),
            is_active=True,
        )
        db.add(user)
        db.flush()
    else:
        user.tenant_id = tenant_id
        user.full_name = full_name
        user.phone = "5511999999999"
        user.is_active = True
        db.add(user)
        db.flush()

    existing = db.execute(select(UserRole).where(UserRole.user_id == user.id)).scalars().all()
    for item in existing:
        db.delete(item)
    db.flush()

    for role_name in role_names:
        db.add(UserRole(tenant_id=tenant_id, user_id=user.id, role_id=role_map[role_name].id))

    db.flush()
    return user


def create_sample_data_for_tenant(db, tenant, unit_a, unit_b, owner_user):
    existing_patient = db.scalar(select(Patient).where(Patient.tenant_id == tenant.id))
    if existing_patient:
        return

    source_whatsapp = db.scalar(
        select(LeadSource).where(LeadSource.tenant_id == tenant.id, LeadSource.name == "WhatsApp")
    )
    if not source_whatsapp:
        source_whatsapp = LeadSource(tenant_id=tenant.id, name="WhatsApp", description="Entrada via WhatsApp")
        db.add(source_whatsapp)
        db.flush()

    names_by_tenant = {
        "sorriso-sul": [
            "Ana Paula Souza",
            "Rodrigo Lima",
            "Fernanda Oliveira",
            "Camila Martins",
            "Gustavo Nunes",
            "Patrícia Almeida",
        ],
        "odonto-prime-osasco": [
            "Carlos Henrique Dias",
            "Marina Teixeira",
            "Julio Cesar Prado",
            "Beatriz Moraes",
            "Renata Cardoso",
            "Thiago Freitas",
        ],
        "implantacare-paulista": [
            "Helena Barbosa",
            "Eduardo Silveira",
            "Vanessa Ribeiro",
            "Marcelo Tavares",
            "Lívia Santana",
            "Leonardo Pires",
        ],
    }
    phone_prefix_by_tenant = {
        "sorriso-sul": "55119101",
        "odonto-prime-osasco": "55119102",
        "implantacare-paulista": "55119103",
    }
    patient_tags = [["vip"], ["ortodontia"], ["rotina"], ["implante"], ["retorno"], ["estetica"]]

    patient_names = names_by_tenant.get(tenant.slug, names_by_tenant["sorriso-sul"])
    phone_prefix = phone_prefix_by_tenant.get(tenant.slug, "55119109")

    patients = []
    for idx, full_name in enumerate(patient_names, start=1):
        phone = f"{phone_prefix}{idx:04d}"
        patient = Patient(
            tenant_id=tenant.id,
            unit_id=unit_a.id if idx <= 3 else unit_b.id,
            lead_source_id=source_whatsapp.id,
            full_name=full_name,
            phone=phone,
            normalized_phone=phone,
            email=f"paciente{idx}.{tenant.slug.replace('-', '')}@odonto.demo",
            status="ativo" if idx != 6 else "inativo",
            origin="whatsapp",
            operational_notes="Paciente prefere comunicação por WhatsApp no horário comercial.",
            lgpd_consent=True,
            marketing_opt_in=idx % 2 == 0,
            tags_cache=patient_tags[idx - 1],
        )
        db.add(patient)
        db.flush()
        for tag in patient.tags_cache:
            db.add(PatientTag(tenant_id=tenant.id, patient_id=patient.id, tag=tag))
        patients.append(patient)

    lead_profiles = [
        {
            "interest": "avaliação ortodôntica",
            "stage": "novo",
            "temperature": "morno",
            "score": 58,
            "name": "Lead interessado em avaliação ortodôntica",
        },
        {
            "interest": "implante dentário",
            "stage": "qualificado",
            "temperature": "quente",
            "score": 85,
            "name": "Lead interessado em implante",
        },
        {
            "interest": "limpeza e profilaxia",
            "stage": "em_contato",
            "temperature": "morno",
            "score": 67,
            "name": "Lead interessado em limpeza",
        },
        {
            "interest": "lente de contato dental",
            "stage": "orcamento_enviado",
            "temperature": "quente",
            "score": 88,
            "name": "Follow-up avaliação estética",
        },
        {
            "interest": "clareamento",
            "stage": "agendado",
            "temperature": "quente",
            "score": 92,
            "name": "Lead com agendamento confirmado",
        },
        {
            "interest": "check-up",
            "stage": "perdido",
            "temperature": "frio",
            "score": 35,
            "name": "Lead sem resposta após orçamento",
        },
    ]

    leads = []
    for idx, profile in enumerate(lead_profiles, start=1):
        patient = patients[idx - 1]
        lead = Lead(
            tenant_id=tenant.id,
            patient_id=patient.id,
            owner_user_id=owner_user.id,
            name=profile["name"],
            phone=patient.phone,
            email=patient.email,
            origin="whatsapp",
            interest=profile["interest"],
            stage=profile["stage"],
            score=profile["score"],
            temperature=profile["temperature"],
            status="ativo",
            notes="Registro comercial criado para demo operacional.",
        )
        db.add(lead)
        db.flush()
        leads.append(lead)

    inbound_messages = [
        "Oi, quero agendar uma avaliação ainda esta semana.",
        "Tenho interesse em implante, vocês parcelam?",
        "Consegue me mandar valores para limpeza?",
        "Vi o anúncio no Instagram e gostaria de orçamento.",
    ]
    outbound_messages = [
        "Perfeito! Tenho horários amanhã às 10h e 14h. Qual você prefere?",
        "Sim, parcelamos em até 10x. Posso te explicar as opções por mensagem.",
        "Claro! Posso te enviar o valor e já deixar uma data reservada.",
        "Ótimo, vamos te ajudar com isso. Posso confirmar alguns dados?",
    ]

    for idx, patient in enumerate(patients[:4], start=1):
        conversation = Conversation(
            tenant_id=tenant.id,
            unit_id=unit_a.id if idx % 2 == 0 else unit_b.id,
            patient_id=patient.id,
            lead_id=leads[idx - 1].id if idx <= len(leads) else None,
            channel="whatsapp",
            status="aberta" if idx == 1 else "aguardando" if idx in (2, 3) else "finalizada",
            assigned_user_id=owner_user.id,
            tags=["triagem"],
            ai_summary="Paciente com interesse comercial ativo e necessidade de retorno da equipe.",
            last_message_at=datetime.now(UTC) - timedelta(minutes=idx * 12),
        )
        db.add(conversation)
        db.flush()

        db.add(
            Message(
                tenant_id=tenant.id,
                conversation_id=conversation.id,
                direction=MessageDirection.INBOUND.value,
                channel="whatsapp",
                sender_type="patient",
                body=inbound_messages[idx - 1],
                message_type="text",
                status="received",
            )
        )
        db.add(
            Message(
                tenant_id=tenant.id,
                conversation_id=conversation.id,
                direction=MessageDirection.OUTBOUND.value,
                channel="whatsapp",
                sender_type="user",
                sender_user_id=owner_user.id,
                body=outbound_messages[idx - 1],
                message_type="text",
                status="sent",
            )
        )

    appointment_profiles = [
        ("agendada", "pendente", 1),
        ("confirmada", "confirmada", 2),
        ("agendada", "pendente", 3),
        ("falta", "nao_confirmada", 4),
        ("cancelada", "nao_confirmada", 5),
        ("agendada", "pendente", 6),
    ]
    for idx, patient in enumerate(patients, start=1):
        starts = datetime.now(UTC) + timedelta(days=idx)
        status, confirmation_status, _ = appointment_profiles[idx - 1]

        appointment = Appointment(
            tenant_id=tenant.id,
            patient_id=patient.id,
            unit_id=unit_a.id if idx % 2 == 0 else unit_b.id,
            procedure_type="Avaliação inicial" if idx <= 3 else "Retorno clínico",
            starts_at=starts,
            status=status,
            confirmation_status=confirmation_status,
            origin="whatsapp",
            notes="Fluxo operacional preparado para demonstração comercial.",
        )
        db.add(appointment)
        db.flush()
        db.add(
            AppointmentEvent(
                tenant_id=tenant.id,
                appointment_id=appointment.id,
                event_type="seed_created",
                to_status=status,
                metadata_json={"from_seed": True},
                created_by_user_id=owner_user.id,
            )
        )

    campaigns = [
        ("Reativação ortodontia abril", "Trazer pacientes inativos para nova avaliação", "agendada"),
        ("Follow-up avaliação estética", "Converter orçamentos pendentes em consulta", "em_execucao"),
        ("Retorno de profilaxia", "Aumentar recorrência de limpeza semestral", "rascunho"),
    ]
    for campaign_name, objective, status in campaigns:
        db.add(
            Campaign(
                tenant_id=tenant.id,
                name=campaign_name,
                objective=objective,
                status=status,
                segment_filter={"tenant": tenant.slug},
                scheduled_at=datetime.now(UTC) + timedelta(days=2),
                created_by_user_id=owner_user.id,
            )
        )

    automations = [
        Automation(
            tenant_id=tenant.id,
            name="Confirmação 24h antes",
            description="Envia lembrete 24h antes da consulta",
            trigger_type="time",
            trigger_key="consulta_24h",
            conditions={"window_minutes": 120},
            actions=[
                {
                    "type": "send_message",
                    "params": {
                        "body": "Lembrete: sua consulta e amanha. Responda CONFIRMO para confirmar.",
                    },
                },
            ],
            retry_policy={"max_attempts": 3},
            is_active=True,
        ),
        Automation(
            tenant_id=tenant.id,
            name="Lembrete 2h antes",
            description="Envia lembrete 2h antes para consultas pendentes",
            trigger_type="time",
            trigger_key="consulta_2h",
            conditions={"status": "pendente"},
            actions=[{"type": "send_message", "params": {"body": "Sua consulta está próxima. Responda CONFIRMO para validar."}}],
            retry_policy={"max_attempts": 3},
            is_active=True,
        ),
        Automation(
            tenant_id=tenant.id,
            name="Segunda tentativa sem resposta",
            description="Se não responder lembrete, envia nova tentativa e direciona para fila humana",
            trigger_type="event",
            trigger_key="consulta_sem_confirmacao",
            conditions={"status": "pendente"},
            actions=[
                {
                    "type": "send_message",
                    "params": {"body": "Ainda aguardamos sua confirmacao. Podemos ajudar com reagendamento?"},
                },
                {"type": "fila_humana", "params": {}},
            ],
            retry_policy={"max_attempts": 4},
            is_active=True,
        ),
        Automation(
            tenant_id=tenant.id,
            name="Recuperação de faltas",
            description="Contato automático quando paciente falta",
            trigger_type="event",
            trigger_key="paciente_faltou",
            conditions={},
            actions=[
                {"type": "send_message", "params": {"body": "Sentimos sua falta hoje. Quer reagendar para um novo horario?"}},
                {"type": "add_tag", "params": {"tag": "faltou"}},
            ],
            retry_policy={"max_attempts": 3},
            is_active=True,
        ),
        Automation(
            tenant_id=tenant.id,
            name="Follow-up orçamento em 2 dias",
            description="Retoma contato com orçamento pendente após 2 dias",
            trigger_type="event",
            trigger_key="orcamento_pendente_2d",
            conditions={},
            actions=[{"type": "send_message", "params": {"body": "Passando para confirmar se você conseguiu analisar o orçamento."}}],
            retry_policy={"max_attempts": 3},
            is_active=True,
        ),
        Automation(
            tenant_id=tenant.id,
            name="Follow-up orçamento em 7 dias",
            description="Última tentativa automática para orçamento pendente",
            trigger_type="event",
            trigger_key="orcamento_pendente_7d",
            conditions={},
            actions=[{"type": "send_message", "params": {"body": "Ainda conseguimos manter condições especiais esta semana."}}],
            retry_policy={"max_attempts": 2},
            is_active=True,
        ),
        Automation(
            tenant_id=tenant.id,
            name="Reativação de pacientes inativos",
            description="Seleciona pacientes sem retorno e envia convite de retomada",
            trigger_type="event",
            trigger_key="paciente_inativo",
            conditions={"inactive_days": 180},
            actions=[{"type": "send_message", "params": {"body": "Estamos com agenda aberta para retomada do seu tratamento."}}],
            retry_policy={"max_attempts": 2},
            is_active=True,
        ),
        Automation(
            tenant_id=tenant.id,
            name="Triagem inicial no WhatsApp",
            description="Qualifica interesse inicial e direciona para o time",
            trigger_type="event",
            trigger_key="lead_whatsapp_entrada",
            conditions={},
            actions=[{"type": "classify_intent", "params": {}}, {"type": "fila_humana", "params": {}}],
            retry_policy={"max_attempts": 3},
            is_active=True,
        ),
    ]
    for automation in automations:
        db.add(automation)

    document = Document(
        tenant_id=tenant.id,
        patient_id=patients[0].id,
        unit_id=unit_a.id,
        created_by_user_id=owner_user.id,
        document_type="consentimento_operacional",
        title="Termo de consentimento de comunicação",
        description="Consentimento para mensagens e lembretes operacionais.",
        storage_provider="local",
        is_sensitive=True,
    )
    db.add(document)
    db.flush()

    version = DocumentVersion(
        tenant_id=tenant.id,
        document_id=document.id,
        uploaded_by_user_id=owner_user.id,
        version_number=1,
        file_path=f"/storage/{tenant.slug}/documents/{document.id}/v1.txt",
        file_name="consentimento-comunicacao.txt",
        mime_type="text/plain",
        size_bytes=820,
        checksum="seed-checksum-001",
        metadata_json={"seed": True},
    )
    db.add(version)
    db.flush()
    document.current_version_id = version.id
    db.add(document)

    account = WhatsAppAccount(
        tenant_id=tenant.id,
        unit_id=unit_a.id,
        provider_name="meta_cloud",
        phone_number_id=f"phone_{tenant.slug}",
        business_account_id=f"biz_{tenant.slug}",
        display_phone="+55 11 98888-7766",
        access_token_encrypted="mock_access_token",
        verify_token="verify-token-dev",
        webhook_secret="mock_secret",
        is_active=True,
    )
    db.add(account)
    db.flush()

    db.add(
        WhatsAppTemplate(
            tenant_id=tenant.id,
            whatsapp_account_id=account.id,
            name="lembrete_consulta_24h",
            language="pt_BR",
            category="UTILITY",
            content={"body": "Lembrete de consulta para {{1}} em {{2}}."},
            status="APPROVED",
        )
    )

    db.add(
        AuditLog(
            tenant_id=tenant.id,
            user_id=owner_user.id,
            action="seed.init",
            entity_type="tenant",
            entity_id=str(tenant.id),
            metadata_json={"message": "Dados de demonstração premium gerados"},
            ip_address="127.0.0.1",
            user_agent="seed-script",
        )
    )


def run_seed() -> None:
    db = SessionLocal()
    try:
        role_map = upsert_roles(db)
        plan_map = upsert_plans(db)

        tenant_a = create_tenant_if_missing(
            db,
            slug="sorriso-sul",
            legal_name="Sorriso Sul Clínica Odontológica LTDA",
            trade_name="Clínica Sorriso Sul",
            plan_id=plan_map["growth"].id,
        )
        tenant_b = create_tenant_if_missing(
            db,
            slug="odonto-prime-osasco",
            legal_name="Odonto Prime Osasco Serviços Odontológicos LTDA",
            trade_name="Odonto Prime Osasco",
            plan_id=plan_map["starter"].id,
        )
        tenant_c = create_tenant_if_missing(
            db,
            slug="implantacare-paulista",
            legal_name="ImplantaCare Paulista Odontologia LTDA",
            trade_name="ImplantaCare Paulista",
            plan_id=plan_map["growth"].id,
        )

        unit_a1 = create_unit_if_missing(db, tenant_a.id, "SP-CENTRO", "Unidade Centro", "+55 11 3333-0001")
        unit_a2 = create_unit_if_missing(db, tenant_a.id, "SP-PAULISTA", "Unidade Paulista", "+55 11 3333-0002")
        unit_b1 = create_unit_if_missing(db, tenant_b.id, "OS-CENTRO", "Unidade Centro", "+55 11 3333-1001")
        unit_b2 = create_unit_if_missing(db, tenant_b.id, "OS-VILA-YARA", "Unidade Vila Yara", "+55 11 3333-1002")
        unit_c1 = create_unit_if_missing(db, tenant_c.id, "SP-PAULISTA", "Unidade Paulista", "+55 11 3333-2001")
        unit_c2 = create_unit_if_missing(db, tenant_c.id, "SP-CENTRO", "Unidade Centro", "+55 11 3333-2002")

        owner_a = create_user_if_missing(
            db,
            tenant_id=tenant_a.id,
            email="owner@sorrisosul.com",
            full_name="Juliana Ramos",
            role_names=["owner"],
            role_map=role_map,
        )
        create_user_if_missing(
            db,
            tenant_id=tenant_a.id,
            email="reception@sorrisosul.com",
            full_name="Mariana Costa",
            role_names=["receptionist"],
            role_map=role_map,
        )
        create_user_if_missing(
            db,
            tenant_id=tenant_a.id,
            email="analyst@sorrisosul.com",
            full_name="Bruno Martins",
            role_names=["analyst"],
            role_map=role_map,
        )
        owner_b = create_user_if_missing(
            db,
            tenant_id=tenant_b.id,
            email="manager@oralprime.com",
            full_name="Dr. Felipe Azevedo",
            role_names=["manager"],
            role_map=role_map,
        )
        create_user_if_missing(
            db,
            tenant_id=tenant_b.id,
            email="analyst@oralprime.com",
            full_name="Bruno Martins",
            role_names=["analyst"],
            role_map=role_map,
        )
        owner_c = create_user_if_missing(
            db,
            tenant_id=tenant_c.id,
            email="owner@implantacare.com",
            full_name="Renata Moura",
            role_names=["owner"],
            role_map=role_map,
        )
        create_user_if_missing(
            db,
            tenant_id=None,
            email="admin@odontoflux.com",
            full_name="Admin Plataforma",
            role_names=["admin_platform"],
            role_map=role_map,
        )

        create_sample_data_for_tenant(db, tenant_a, unit_a1, unit_a2, owner_a)
        create_sample_data_for_tenant(db, tenant_b, unit_b1, unit_b2, owner_b)
        create_sample_data_for_tenant(db, tenant_c, unit_c1, unit_c2, owner_c)

        db.commit()
        print("Seed executado com sucesso.")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    run_seed()

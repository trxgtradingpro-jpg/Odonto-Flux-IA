from sqlalchemy import select

from app.core.config import settings
from app.models import (
    AIAutoresponderDecision,
    Conversation,
    Lead,
    Message,
    OutboxMessage,
    Patient,
    ProspectAccount,
    Setting,
    WebhookInbox,
    WhatsAppAccount,
)
from app.services.whatsapp_service import process_outbox_batch, queue_outbound_message


def test_meta_webhook_verification_returns_plain_challenge_for_env_token(client, monkeypatch):
    monkeypatch.setattr(settings, 'whatsapp_verify_token', 'env-token-123')

    response = client.get(
        '/api/v1/webhooks/whatsapp',
        params={
            'hub.mode': 'subscribe',
            'hub.verify_token': 'env-token-123',
            'hub.challenge': 'challenge-abc',
        },
    )

    assert response.status_code == 200
    assert response.text == 'challenge-abc'
    assert response.headers['content-type'].startswith('text/plain')


def test_meta_webhook_verification_accepts_active_account_verify_token(client, seeded_db, monkeypatch):
    monkeypatch.setattr(settings, 'whatsapp_verify_token', 'different-env-token')

    response = client.get(
        '/api/v1/webhooks/whatsapp',
        params={
            'hub.mode': 'subscribe',
            'hub.verify_token': 'verify-token-dev',
            'hub.challenge': '123456',
        },
    )

    assert response.status_code == 200
    assert response.text == '123456'
    assert response.headers['content-type'].startswith('text/plain')


def test_whatsapp_webhook_creates_lead_conversation_and_message(client, auth_headers, seeded_db, db_session):
    payload = {
        'entry': [
            {
                'changes': [
                    {
                        'value': {
                            'metadata': {'phone_number_id': 'phone_tenant_a'},
                            'messages': [
                                {
                                    'id': 'wamid.msg.001',
                                    'from': '11999991111',
                                    'timestamp': '1712518000',
                                    'text': {'body': 'Oi, quero agendar uma avaliacao.'},
                                    'type': 'text',
                                }
                            ],
                        }
                    }
                ]
            }
        ]
    }

    response = client.post('/api/v1/webhooks/whatsapp', json=payload)
    assert response.status_code == 200

    patient = db_session.scalar(select(Patient).where(Patient.normalized_phone == '5511999991111'))
    assert patient is not None

    lead = db_session.scalar(select(Lead).where(Lead.patient_id == patient.id))
    assert lead is not None

    conversation = db_session.scalar(select(Conversation).where(Conversation.patient_id == patient.id))
    assert conversation is not None

    message = db_session.scalar(select(Message).where(Message.conversation_id == conversation.id))
    assert message is not None
    assert 'agendar' in message.body



def test_meta_webhook_interactive_list_reply_creates_inbound_message(client, auth_headers, seeded_db, db_session):
    payload = {
        'entry': [
            {
                'changes': [
                    {
                        'value': {
                            'metadata': {'phone_number_id': 'phone_tenant_a'},
                            'messages': [
                                {
                                    'id': 'wamid.interactive.001',
                                    'from': '11999994444',
                                    'timestamp': '1712518003',
                                    'type': 'interactive',
                                    'interactive': {
                                        'type': 'list_reply',
                                        'list_reply': {
                                            'id': 'slot_3',
                                            'title': 'Opção 3',
                                            'description': 'quinta-feira, 16/04 às 15:00',
                                        },
                                    },
                                }
                            ],
                        }
                    }
                ]
            }
        ]
    }

    response = client.post('/api/v1/webhooks/whatsapp', json=payload)
    assert response.status_code == 200

    patient = db_session.scalar(select(Patient).where(Patient.normalized_phone == '5511999994444'))
    assert patient is not None

    message = db_session.scalar(
        select(Message)
        .where(
            Message.tenant_id == seeded_db['tenant_a'].id,
            Message.direction == 'inbound',
            Message.provider_message_id == 'wamid.interactive.001',
        )
        .order_by(Message.created_at.desc())
    )
    assert message is not None
    assert message.message_type == 'interactive_list_reply'
    assert message.body == 'Opção 3'
    assert (message.payload or {}).get('interactive_reply', {}).get('id') == 'slot_3'


def test_meta_audio_webhook_transcribes_inbound_message(client, auth_headers, seeded_db, db_session, monkeypatch):
    from app.services import whatsapp_service

    def _fake_download_whatsapp_audio_bytes(*, account, media):
        return (
            b'fake-audio-meta',
            {
                'content_type': 'audio/ogg',
                'content_length': '15',
                'resolved_url': 'https://media.example/meta-audio.ogg',
            },
        )

    def _fake_transcribe_audio_bytes(content, *, mime_type=None, file_name=None):
        assert content == b'fake-audio-meta'
        assert mime_type == 'audio/ogg'
        return {
            'text': 'Preciso remarcar minha consulta para amanha cedo.',
            'language': 'pt',
            'language_probability': 0.99,
            'duration_seconds': 6.4,
            'model': 'base',
        }

    monkeypatch.setattr(whatsapp_service, '_download_whatsapp_audio_bytes', _fake_download_whatsapp_audio_bytes)
    monkeypatch.setattr(whatsapp_service, 'transcribe_audio_bytes', _fake_transcribe_audio_bytes)

    payload = {
        'entry': [
            {
                'changes': [
                    {
                        'value': {
                            'metadata': {'phone_number_id': 'phone_tenant_a'},
                            'messages': [
                                {
                                    'id': 'wamid.audio.001',
                                    'from': '11999995555',
                                    'timestamp': '1712518004',
                                    'type': 'audio',
                                    'audio': {
                                        'id': 'media.audio.001',
                                        'mime_type': 'audio/ogg',
                                        'sha256': 'abc123',
                                        'voice': True,
                                    },
                                }
                            ],
                        }
                    }
                ]
            }
        ]
    }

    response = client.post('/api/v1/webhooks/whatsapp', json=payload)
    assert response.status_code == 200

    patient = db_session.scalar(select(Patient).where(Patient.normalized_phone == '5511999995555'))
    assert patient is not None

    message = db_session.scalar(
        select(Message)
        .where(
            Message.tenant_id == seeded_db['tenant_a'].id,
            Message.direction == 'inbound',
            Message.provider_message_id == 'wamid.audio.001',
        )
        .order_by(Message.created_at.desc())
    )
    assert message is not None
    assert message.message_type == 'audio'
    assert message.body == 'Preciso remarcar minha consulta para amanha cedo.'
    assert (message.payload or {}).get('audio_transcription', {}).get('status') == 'completed'
    assert (message.payload or {}).get('media', {}).get('media_id') == 'media.audio.001'


def test_messages_endpoint_returns_most_recent_page(client, auth_headers, seeded_db, db_session):
    payload = {
        'entry': [
            {
                'changes': [
                    {
                        'value': {
                            'metadata': {'phone_number_id': 'phone_tenant_a'},
                            'messages': [
                                {
                                    'id': 'wamid.msg.recent.001',
                                    'from': '11988887777',
                                    'timestamp': '1712518010',
                                    'text': {'body': 'Oi, conversa para teste de paginação.'},
                                    'type': 'text',
                                }
                            ],
                        }
                    }
                ]
            }
        ]
    }

    response = client.post('/api/v1/webhooks/whatsapp', json=payload)
    assert response.status_code == 200

    patient = db_session.scalar(select(Patient).where(Patient.normalized_phone == '5511988887777'))
    assert patient is not None
    conversation = db_session.scalar(select(Conversation).where(Conversation.patient_id == patient.id))
    assert conversation is not None

    for index in range(230):
        db_session.add(
            Message(
                tenant_id=seeded_db['tenant_a'].id,
                conversation_id=conversation.id,
                direction='outbound',
                channel='whatsapp',
                sender_type='ai',
                body=f'bulk-{index}',
                message_type='text',
                payload={},
                status='sent',
            )
        )
    db_session.commit()

    list_response = client.get(
        '/api/v1/messages',
        params={'conversation_id': str(conversation.id), 'limit': 200, 'offset': 0},
        headers=auth_headers['owner_a'],
    )
    assert list_response.status_code == 200
    data = list_response.json()['data']
    assert len(data) == 200
    bodies = [item['body'] for item in data]
    assert 'bulk-229' in bodies
    assert 'bulk-0' not in bodies


def test_tenant_isolation_on_patient_list(client, auth_headers):
    payload_a = {'full_name': 'Paciente A', 'phone': '11990000001'}
    payload_b = {'full_name': 'Paciente B', 'phone': '11990000002'}

    resp_a_create = client.post('/api/v1/patients', json=payload_a, headers=auth_headers['owner_a'])
    assert resp_a_create.status_code == 200
    resp_b_create = client.post('/api/v1/patients', json=payload_b, headers=auth_headers['owner_b'])
    assert resp_b_create.status_code == 200

    resp_a_list = client.get('/api/v1/patients', headers=auth_headers['owner_a'])
    assert resp_a_list.status_code == 200
    names_a = [item['full_name'] for item in resp_a_list.json()['data']]
    assert 'Paciente A' in names_a
    assert 'Paciente B' not in names_a



def test_platform_admin_endpoint_requires_role(client, auth_headers):
    forbidden = client.get('/api/v1/admin/platform/metrics', headers=auth_headers['owner_a'])
    assert forbidden.status_code == 403

    allowed = client.get('/api/v1/admin/platform/metrics', headers=auth_headers['admin'])
    assert allowed.status_code == 200
    assert 'total_tenants' in allowed.json()


def test_platform_admin_lists_implementation_catalog(client, auth_headers):
    response = client.get('/api/v1/admin/platform/implementations', headers=auth_headers['admin'])
    assert response.status_code == 200
    payload = response.json()
    assert payload['summary']['total'] >= 5
    keys = {item['key'] for item in payload['items']}
    assert 'implementation.public_booking_webchat' in keys
    assert 'implementation.adm_implementation_control_center' in keys


def test_platform_admin_toggles_implementation_flag(client, auth_headers):
    toggled = client.patch(
        '/api/v1/admin/platform/implementations/implementation.sales_outreach_automation',
        json={'enabled': True},
        headers=auth_headers['admin'],
    )
    assert toggled.status_code == 200
    assert toggled.json()['enabled'] is True
    assert toggled.json()['key'] == 'implementation.sales_outreach_automation'

    listed = client.get('/api/v1/admin/platform/implementations', headers=auth_headers['admin'])
    assert listed.status_code == 200
    item = next(entry for entry in listed.json()['items'] if entry['key'] == 'implementation.sales_outreach_automation')
    assert item['enabled'] is True


def test_platform_admin_whatsapp_settings_use_system_sender_tenant(client, auth_headers, monkeypatch):
    from app.api.v1.endpoints import admin_platform
    from app.services import sales_demo_service

    monkeypatch.setattr(sales_demo_service.settings, 'sales_outreach_sender_tenant_slug', '')
    monkeypatch.setattr(admin_platform.settings, 'sales_outreach_sender_tenant_slug', '')

    context = client.get('/api/v1/admin/platform/whatsapp/context', headers=auth_headers['admin'])
    assert context.status_code == 200
    context_payload = context.json()
    assert context_payload['tenant_slug'] == sales_demo_service.DEFAULT_SALES_OUTREACH_SENDER_TENANT_SLUG
    assert context_payload['uses_default_sender_slug'] is True

    created = client.post(
        '/api/v1/admin/platform/whatsapp/accounts',
        json={
            'provider_name': 'meta_cloud',
            'phone_number_id': '1101713436353674',
            'business_account_id': '936994182588219',
            'access_token': 'EAAa' + ('x' * 60),
            'display_phone': '+55 11 4000-4000',
        },
        headers=auth_headers['admin'],
    )
    assert created.status_code == 200
    assert created.json()['is_active'] is True

    accounts = client.get('/api/v1/admin/platform/whatsapp/accounts', headers=auth_headers['admin'])
    assert accounts.status_code == 200
    assert len(accounts.json()['data']) == 1
    assert accounts.json()['data'][0]['display_phone'] == '+55 11 4000-4000'

    health = client.get('/api/v1/admin/platform/whatsapp/health', headers=auth_headers['admin'])
    assert health.status_code == 200
    assert health.json()['status'] == 'ok'
    assert health.json()['active_account']['phone_number_id'] == '1101713436353674'


def test_platform_admin_can_delete_system_whatsapp_account_and_clear_demo_assignment(
    client,
    auth_headers,
    seeded_db,
    db_session,
    monkeypatch,
):
    from app.api.v1.endpoints import admin_platform
    from app.services import sales_demo_service

    monkeypatch.setattr(sales_demo_service.settings, 'sales_outreach_sender_tenant_slug', '')
    monkeypatch.setattr(admin_platform.settings, 'sales_outreach_sender_tenant_slug', '')

    created = client.post(
        '/api/v1/admin/platform/whatsapp/accounts',
        json={
            'provider_name': 'meta_cloud',
            'phone_number_id': '1101713436353674',
            'business_account_id': '936994182588219',
            'access_token': 'EAAa' + ('x' * 60),
            'display_phone': '+55 11 4000-4000',
        },
        headers=auth_headers['admin'],
    )
    assert created.status_code == 200
    account_id = created.json()['id']

    prospect = ProspectAccount(
        clinic_name='Clinica Demo Vinculada',
        proposal_snapshot={'demo_whatsapp': {'account_id': account_id}},
    )
    db_session.add(prospect)
    db_session.commit()

    deleted = client.delete(
        f'/api/v1/admin/platform/whatsapp/accounts/{account_id}',
        headers=auth_headers['admin'],
    )
    assert deleted.status_code == 200
    assert deleted.json()['status'] == 'deleted'
    assert deleted.json()['removed_active_account'] is True
    assert deleted.json()['cleared_demo_assignments'] == 1

    accounts = client.get('/api/v1/admin/platform/whatsapp/accounts', headers=auth_headers['admin'])
    assert accounts.status_code == 200
    assert accounts.json()['data'] == []

    health = client.get('/api/v1/admin/platform/whatsapp/health', headers=auth_headers['admin'])
    assert health.status_code == 200
    assert health.json()['active_account'] is None

    refreshed_prospect = db_session.get(ProspectAccount, prospect.id)
    assert refreshed_prospect is not None
    assert ((refreshed_prospect.proposal_snapshot or {}).get('demo_whatsapp') or {}).get('account_id') is None


def test_webhook_inbound_triggers_ai_decision_and_outbox_dispatch(
    client,
    auth_headers,
    seeded_db,
    db_session,
    monkeypatch,
):
    tenant_id = seeded_db['tenant_a'].id
    account = db_session.scalar(select(WhatsAppAccount).where(WhatsAppAccount.tenant_id == tenant_id))
    account.phone_number_id = '1101713436353674'
    account.business_account_id = '936994182588219'
    account.access_token_encrypted = 'EAAb' + ('y' * 70)
    db_session.add(account)

    db_session.add(
        Setting(
            tenant_id=tenant_id,
            key='ai_autoresponder.global',
            value={
                'enabled': True,
                'channels': {'whatsapp': True},
                'business_hours': {'timezone': 'America/Sao_Paulo', 'weekdays': [0, 1, 2, 3, 4, 5, 6], 'start': '00:00', 'end': '23:59'},
                'outside_business_hours_mode': 'allow',
                'max_consecutive_auto_replies': 3,
                'confidence_threshold': 0.5,
                'human_queue_tag': 'fila_humana_ia',
                'tone': 'profissional',
            },
            is_secret=False,
        )
    )
    db_session.commit()

    payload = {
        'entry': [
            {
                'changes': [
                    {
                        'value': {
                            'metadata': {'phone_number_id': '1101713436353674'},
                            'messages': [
                                {
                                    'id': 'wamid.msg.ai.001',
                                    'from': '11999992222',
                                    'timestamp': '1712518001',
                                    'text': {'body': 'Oi, quero agendar uma avaliacao para essa semana.'},
                                    'type': 'text',
                                }
                            ],
                        }
                    }
                ]
            }
        ]
    }

    response = client.post('/api/v1/webhooks/whatsapp', json=payload)
    assert response.status_code == 200

    decision = db_session.scalar(select(AIAutoresponderDecision).where(AIAutoresponderDecision.tenant_id == tenant_id))
    assert decision is not None
    assert decision.final_decision == 'responded'

    outbox = db_session.scalar(select(OutboxMessage).where(OutboxMessage.tenant_id == tenant_id))
    assert outbox is not None
    assert outbox.status == 'pending'
    assert (outbox.payload.get('metadata') or {}).get('source') == 'ai_autoresponder'

    from app.integrations.whatsapp.cloud_api import WhatsAppCloudProvider

    def _fake_send_text_message(self, *, phone_number_id, access_token, to, body):
        return {'messages': [{'id': 'wamid.out.ai.001'}], 'contacts': [{'wa_id': to}]}

    def _fake_send_interactive_list_message(
        self,
        *,
        phone_number_id,
        access_token,
        to,
        body,
        button_title,
        rows,
        section_title=None,
        header_text=None,
        footer_text=None,
    ):
        return {'messages': [{'id': 'wamid.out.ai.001'}], 'contacts': [{'wa_id': to}]}

    monkeypatch.setattr(WhatsAppCloudProvider, 'send_text_message', _fake_send_text_message)
    monkeypatch.setattr(WhatsAppCloudProvider, 'send_interactive_list_message', _fake_send_interactive_list_message)

    result = process_outbox_batch(db_session, batch_size=20)
    assert result['sent'] >= 1

    outbound_message = db_session.scalar(
        select(Message).where(
            Message.tenant_id == tenant_id,
            Message.direction == 'outbound',
            Message.sender_type == 'ai',
        )
    )
    assert outbound_message is not None
    assert outbound_message.status == 'sent'
    assert outbound_message.provider_message_id == 'wamid.out.ai.001'


def test_infobip_account_dispatches_outbox(client, auth_headers, seeded_db, db_session, monkeypatch):
    tenant_id = seeded_db['tenant_a'].id
    account = db_session.scalar(select(WhatsAppAccount).where(WhatsAppAccount.tenant_id == tenant_id))
    account.provider_name = 'infobip'
    account.phone_number_id = '5511940431906'
    account.business_account_id = '3dd13w.api.infobip.com'
    account.access_token_encrypted = 'infobip-app-key-' + ('x' * 40)
    db_session.add(account)
    db_session.commit()

    outbox = queue_outbound_message(
        db_session,
        tenant_id=tenant_id,
        conversation_id=None,
        to='5511999990001',
        body='Teste Infobip',
        message_type='text',
    )

    from app.integrations.whatsapp.infobip import InfobipWhatsAppProvider

    def _fake_send_text_message(self, *, phone_number_id, access_token, to, body):
        return {'messages': [{'messageId': 'ib-msg-001'}]}

    monkeypatch.setattr(InfobipWhatsAppProvider, 'send_text_message', _fake_send_text_message)

    result = process_outbox_batch(db_session, batch_size=20)
    assert result['sent'] >= 1

    refreshed = db_session.get(OutboxMessage, outbox.id)
    assert refreshed is not None
    assert refreshed.status == 'sent'


def test_infobip_account_dispatches_interactive_list_outbox(client, auth_headers, seeded_db, db_session, monkeypatch):
    tenant_id = seeded_db['tenant_a'].id
    account = db_session.scalar(select(WhatsAppAccount).where(WhatsAppAccount.tenant_id == tenant_id))
    account.provider_name = 'infobip'
    account.phone_number_id = '5511940431906'
    account.business_account_id = '3dd13w.api.infobip.com'
    account.access_token_encrypted = 'infobip-app-key-' + ('x' * 40)
    db_session.add(account)
    db_session.commit()

    outbox = queue_outbound_message(
        db_session,
        tenant_id=tenant_id,
        conversation_id=None,
        to='5511999990001',
        body='Selecione uma opção para confirmar.',
        message_type='interactive_list',
        interactive={
            'button_title': 'Opções',
            'section_title': 'Horários',
            'rows': [
                {'id': 'slot_1', 'title': 'Opção 1', 'description': 'quinta-feira, 16/04 às 13:00'},
                {'id': 'slot_2', 'title': 'Opção 2', 'description': 'quinta-feira, 16/04 às 14:00'},
            ],
        },
    )

    from app.integrations.whatsapp.infobip import InfobipWhatsAppProvider

    called = {'interactive': False}

    def _fake_send_interactive_list_message(
        self,
        *,
        phone_number_id,
        access_token,
        to,
        body,
        button_title,
        rows,
        section_title=None,
        header_text=None,
        footer_text=None,
    ):
        called['interactive'] = True
        return {'messages': [{'messageId': 'ib-msg-interactive-001'}]}

    monkeypatch.setattr(InfobipWhatsAppProvider, 'send_interactive_list_message', _fake_send_interactive_list_message)

    result = process_outbox_batch(db_session, batch_size=20)
    assert result['sent'] >= 1
    assert called['interactive'] is True

    refreshed = db_session.get(OutboxMessage, outbox.id)
    assert refreshed is not None
    assert refreshed.status == 'sent'


def test_infobip_webhook_with_long_event_id_is_stored_safely(client, auth_headers, seeded_db, db_session):
    tenant_id = seeded_db['tenant_a'].id
    account = db_session.scalar(select(WhatsAppAccount).where(WhatsAppAccount.tenant_id == tenant_id))
    account.provider_name = 'infobip'
    account.phone_number_id = '447860042894'
    account.business_account_id = '3dd13w.api.infobip.com'
    account.access_token_encrypted = 'infobip-app-key-' + ('x' * 40)
    db_session.add(account)
    db_session.commit()

    payload = {
        'results': [
            {
                'from': '5511940431906',
                'to': '447860042894',
                'integrationType': 'WHATSAPP',
                'receivedAt': '2026-04-14T23:20:08.000+0000',
                'messageId': 'E_BLzsUdUY8I3ZuTBMC3lYflob3uPB3DE8_e04FfUur-7KhboQqzWKosGt4y2lT5-dmB9JwzhlB2SUlG1ldODoCrFJXRE_LOM0_34hlSq6NQA',
                'message': {'text': 'Oi', 'type': 'TEXT'},
                'contact': {'name': 'Guilherme Gomes'},
            }
        ]
    }

    response = client.post('/api/v1/webhooks/whatsapp', json=payload)
    assert response.status_code == 200
    assert response.json()['result']['processed'] == 1

    inbox_event = db_session.scalar(
        select(WebhookInbox)
        .where(
            WebhookInbox.tenant_id == tenant_id,
            WebhookInbox.provider == 'infobip_whatsapp',
        )
        .order_by(WebhookInbox.created_at.desc())
    )
    assert inbox_event is not None
    assert len(inbox_event.event_id) <= 120

    patient = db_session.scalar(select(Patient).where(Patient.normalized_phone == '5511940431906'))
    assert patient is not None

    message = db_session.scalar(
        select(Message)
        .where(
            Message.tenant_id == tenant_id,
            Message.direction == 'inbound',
            Message.channel == 'whatsapp',
        )
        .order_by(Message.created_at.desc())
    )
    assert message is not None
    assert message.body == 'Oi'


def test_infobip_webhook_interactive_list_reply_creates_inbound_message(client, auth_headers, seeded_db, db_session):
    tenant_id = seeded_db['tenant_a'].id
    account = db_session.scalar(select(WhatsAppAccount).where(WhatsAppAccount.tenant_id == tenant_id))
    account.provider_name = 'infobip'
    account.phone_number_id = '447860042894'
    account.business_account_id = '3dd13w.api.infobip.com'
    account.access_token_encrypted = 'infobip-app-key-' + ('x' * 40)
    db_session.add(account)
    db_session.commit()

    payload = {
        'results': [
            {
                'from': '5511940431906',
                'to': '447860042894',
                'integrationType': 'WHATSAPP',
                'receivedAt': '2026-04-14T23:20:08.000+0000',
                'messageId': 'ib-interactive-in-001',
                'pairedMessageId': 'ib-outbound-001',
                'message': {
                    'id': 'slot_2',
                    'title': 'Opção 2',
                    'description': 'quinta-feira, 16/04 às 14:00',
                    'type': 'INTERACTIVE_LIST_REPLY',
                },
                'contact': {'name': 'Guilherme Gomes'},
            }
        ]
    }

    response = client.post('/api/v1/webhooks/whatsapp', json=payload)
    assert response.status_code == 200
    assert response.json()['result']['processed'] == 1

    message = db_session.scalar(
        select(Message)
        .where(
            Message.tenant_id == tenant_id,
            Message.direction == 'inbound',
            Message.channel == 'whatsapp',
            Message.provider_message_id == 'ib-interactive-in-001',
        )
        .order_by(Message.created_at.desc())
    )
    assert message is not None
    assert message.message_type == 'interactive_list_reply'
    assert message.body == 'Opção 2'
    assert (message.payload or {}).get('interactive_reply', {}).get('id') == 'slot_2'


def test_twilio_account_dispatches_outbox(client, auth_headers, seeded_db, db_session, monkeypatch):
    tenant_id = seeded_db['tenant_a'].id
    account = db_session.scalar(select(WhatsAppAccount).where(WhatsAppAccount.tenant_id == tenant_id))
    account.provider_name = 'twilio'
    account.phone_number_id = 'whatsapp:+447860088970'
    account.business_account_id = 'AC' + ('1' * 32)
    account.access_token_encrypted = 'twilio-token-' + ('x' * 24)
    db_session.add(account)
    db_session.commit()

    outbox = queue_outbound_message(
        db_session,
        tenant_id=tenant_id,
        conversation_id=None,
        to='5511999990001',
        body='Teste Twilio',
        message_type='text',
    )

    from app.integrations.whatsapp.twilio import TwilioWhatsAppProvider

    def _fake_send_text_message(self, *, phone_number_id, access_token, to, body):
        return {'sid': 'SMtwilio001'}

    monkeypatch.setattr(TwilioWhatsAppProvider, 'send_text_message', _fake_send_text_message)

    result = process_outbox_batch(db_session, batch_size=20)
    assert result['sent'] >= 1

    refreshed = db_session.get(OutboxMessage, outbox.id)
    assert refreshed is not None
    assert refreshed.status == 'sent'


def test_twilio_webhook_creates_inbound_message(client, auth_headers, seeded_db, db_session):
    tenant_id = seeded_db['tenant_a'].id
    account = db_session.scalar(select(WhatsAppAccount).where(WhatsAppAccount.tenant_id == tenant_id))
    account.provider_name = 'twilio'
    account.phone_number_id = 'whatsapp:+447860088970'
    account.business_account_id = 'AC' + ('2' * 32)
    account.access_token_encrypted = 'twilio-token-' + ('x' * 24)
    db_session.add(account)
    db_session.commit()

    payload = {
        'MessageSid': 'SMtwilio-in-001',
        'From': 'whatsapp:+5511999991111',
        'To': 'whatsapp:+447860088970',
        'Body': 'Oi, quero agendar via Twilio',
        'MessageStatus': 'received',
        'SmsStatus': 'received',
    }

    response = client.post('/api/v1/webhooks/whatsapp', json=payload)
    assert response.status_code == 200

    patient = db_session.scalar(select(Patient).where(Patient.normalized_phone == '5511999991111'))
    assert patient is not None

    conversation = db_session.scalar(select(Conversation).where(Conversation.patient_id == patient.id))
    assert conversation is not None

    message = db_session.scalar(select(Message).where(Message.conversation_id == conversation.id))
    assert message is not None
    assert 'Twilio' in message.body


def test_twilio_audio_webhook_transcribes_inbound_message(client, auth_headers, seeded_db, db_session, monkeypatch):
    from app.services import whatsapp_service

    tenant_id = seeded_db['tenant_a'].id
    account = db_session.scalar(select(WhatsAppAccount).where(WhatsAppAccount.tenant_id == tenant_id))
    account.provider_name = 'twilio'
    account.phone_number_id = 'whatsapp:+447860088970'
    account.business_account_id = 'AC' + ('3' * 32)
    account.access_token_encrypted = 'twilio-token-' + ('x' * 24)
    db_session.add(account)
    db_session.commit()

    def _fake_download_whatsapp_audio_bytes(*, account, media):
        assert media.get('media_url') == 'https://api.twilio.com/2010-04-01/Accounts/ACtest/Messages/MMtest/Media/MEaudio001'
        return (
            b'fake-audio-twilio',
            {
                'content_type': 'audio/ogg',
                'content_length': '17',
                'resolved_url': media.get('media_url'),
            },
        )

    def _fake_transcribe_audio_bytes(content, *, mime_type=None, file_name=None):
        assert content == b'fake-audio-twilio'
        assert mime_type == 'audio/ogg'
        return {
            'text': 'Quero confirmar o horario das nove horas.',
            'language': 'pt',
            'language_probability': 0.98,
            'duration_seconds': 4.2,
            'model': 'base',
        }

    monkeypatch.setattr(whatsapp_service, '_download_whatsapp_audio_bytes', _fake_download_whatsapp_audio_bytes)
    monkeypatch.setattr(whatsapp_service, 'transcribe_audio_bytes', _fake_transcribe_audio_bytes)

    payload = {
        'MessageSid': 'SMtwilio-audio-001',
        'From': 'whatsapp:+5511999991212',
        'To': 'whatsapp:+447860088970',
        'Body': '',
        'MessageStatus': 'received',
        'SmsStatus': 'received',
        'NumMedia': '1',
        'MediaUrl0': 'https://api.twilio.com/2010-04-01/Accounts/ACtest/Messages/MMtest/Media/MEaudio001',
        'MediaContentType0': 'audio/ogg',
    }

    response = client.post('/api/v1/webhooks/whatsapp', json=payload)
    assert response.status_code == 200

    patient = db_session.scalar(select(Patient).where(Patient.normalized_phone == '5511999991212'))
    assert patient is not None

    message = db_session.scalar(
        select(Message)
        .where(
            Message.tenant_id == tenant_id,
            Message.direction == 'inbound',
            Message.provider_message_id == 'SMtwilio-audio-001',
        )
        .order_by(Message.created_at.desc())
    )
    assert message is not None
    assert message.message_type == 'audio'
    assert message.body == 'Quero confirmar o horario das nove horas.'
    assert (message.payload or {}).get('audio_transcription', {}).get('status') == 'completed'

from sqlalchemy import select

from app.models import (
    AIAutoresponderDecision,
    Conversation,
    Lead,
    Message,
    OutboxMessage,
    Patient,
    Setting,
    WhatsAppAccount,
)
from app.services.whatsapp_service import process_outbox_batch, queue_outbound_message


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

    monkeypatch.setattr(WhatsAppCloudProvider, 'send_text_message', _fake_send_text_message)

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

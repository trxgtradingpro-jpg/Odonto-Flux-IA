from datetime import UTC, datetime
from time import perf_counter
from uuid import UUID

from sqlalchemy.orm import Session

from app.integrations.llm.provider_factory import LLMProviderFactory, apply_guardrails
from app.models import LLMInteraction


def run_llm_task(
    db: Session,
    *,
    tenant_id: UUID | None,
    conversation_id: UUID | None,
    task: str,
    prompt: str,
) -> dict:
    provider = LLMProviderFactory.create()
    start = perf_counter()
    response = provider.complete(task=task, prompt=prompt)
    latency_ms = int((perf_counter() - start) * 1000)

    raw_output = response['output']
    # O auto-responder ja possui guardrails proprios no fluxo de decisao.
    # Evitamos sobrescrever a resposta com fallback global aqui.
    safe_output = raw_output if task == 'auto_responder' else apply_guardrails(raw_output)

    interaction = LLMInteraction(
        tenant_id=tenant_id,
        conversation_id=conversation_id,
        provider=response.get('metadata', {}).get('provider', 'unknown'),
        task=task,
        prompt=prompt,
        response=safe_output,
        metadata_json=response.get('metadata', {}),
        latency_ms=latency_ms,
    )
    db.add(interaction)
    db.commit()

    return {
        'output': safe_output,
        'metadata': {
            **response.get('metadata', {}),
            'latency_ms': latency_ms,
            'logged_at': datetime.now(UTC).isoformat(),
        },
    }


def classify_intent(db: Session, *, tenant_id: UUID, conversation_id: UUID | None, message: str) -> dict:
    prompt = (
        'Classifique a intencao operacional da mensagem em JSON com campos intent e confidence. '
        f'Mensagem: {message}'
    )
    return run_llm_task(
        db,
        tenant_id=tenant_id,
        conversation_id=conversation_id,
        task='classify_intent',
        prompt=prompt,
    )


def summarize_conversation(
    db: Session,
    *,
    tenant_id: UUID,
    conversation_id: UUID,
    transcript: str,
) -> dict:
    prompt = (
        'Resuma em portugues foco operacional: status, proximo passo, pendencias e riscos. '
        f'Historico: {transcript}'
    )
    return run_llm_task(
        db,
        tenant_id=tenant_id,
        conversation_id=conversation_id,
        task='summarize',
        prompt=prompt,
    )


def suggest_reply(
    db: Session,
    *,
    tenant_id: UUID,
    conversation_id: UUID,
    context: str,
) -> dict:
    prompt = (
        'Sugira resposta profissional em pt-BR para recepcao odontologica sem orientacao clinica. '
        f'Contexto: {context}'
    )
    return run_llm_task(
        db,
        tenant_id=tenant_id,
        conversation_id=conversation_id,
        task='suggest_reply',
        prompt=prompt,
    )


def classify_lead_temperature(db: Session, *, tenant_id: UUID, message: str) -> dict:
    prompt = f'Classifique lead em quente/morno/frio com JSON. Mensagem: {message}'
    return run_llm_task(
        db,
        tenant_id=tenant_id,
        conversation_id=None,
        task='lead_temperature',
        prompt=prompt,
    )

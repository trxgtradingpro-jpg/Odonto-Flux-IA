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
    model_override: str | None = None,
) -> dict:
    provider = LLMProviderFactory.create()
    start = perf_counter()
    response = provider.complete(task=task, prompt=prompt, model=model_override)
    latency_ms = int((perf_counter() - start) * 1000)

    raw_output = response['output']
    # O auto-responder ja possui guardrails proprios no fluxo de decisao.
    # Evitamos sobrescrever a resposta com fallback global aqui.
    safe_output = (
        raw_output
        if task in {'auto_responder', 'auto_responder_structured_extract', 'auto_responder_structured_reply'}
        else apply_guardrails(raw_output)
    )

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
    additional_context: str | None = None,
) -> dict:
    additional_context_text = str(additional_context or "").strip()
    prompt_parts = [
        "Resuma em portugues foco operacional: status, proximo passo, pendencias e riscos.",
    ]
    if additional_context_text:
        prompt_parts.append(f"Considere tambem este contexto adicional do atendente: {additional_context_text}")
    prompt_parts.append(f"Historico: {transcript}")
    prompt = " ".join(prompt_parts)
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
        'Sugira resposta profissional em pt-BR para recepcao de clinicas sem orientacao clinica. '
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

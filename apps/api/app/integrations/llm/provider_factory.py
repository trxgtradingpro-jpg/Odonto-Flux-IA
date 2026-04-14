
from app.core.config import settings
from app.integrations.llm.base import LLMProvider
from app.integrations.llm.mock_provider import MockLLMProvider
from app.integrations.llm.openai_provider import OpenAILLMProvider


class LLMProviderFactory:
    @staticmethod
    def create() -> LLMProvider:
        provider = (settings.llm_provider or 'mock').strip().lower()
        if provider in {'openai', 'openai_chat', 'openai_api'}:
            return OpenAILLMProvider()
        if provider == 'mock':
            return MockLLMProvider()
        return MockLLMProvider()


BLOCKED_CLINICAL_TERMS = [
    'diagnostico',
    'laudo',
    'prescricao',
    'tratamento indicado',
    'protocolo clinico',
]



def apply_guardrails(text: str) -> str:
    lowered = text.lower()
    for term in BLOCKED_CLINICAL_TERMS:
        if term in lowered:
            return (
                'Nao posso fornecer recomendacao clinica. Vou encaminhar para atendimento humano '
                'e seguir apenas com orientacoes operacionais.'
            )
    return text

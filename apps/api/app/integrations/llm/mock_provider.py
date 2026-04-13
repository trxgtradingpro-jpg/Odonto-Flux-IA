import json

from app.integrations.llm.base import LLMProvider


class MockLLMProvider(LLMProvider):
    def complete(self, *, task: str, prompt: str) -> dict:
        lower_prompt = prompt.lower()
        if task == 'classify_intent':
            intent = 'agendamento'
            if 'cancel' in lower_prompt:
                intent = 'cancelamento'
            elif 'reagend' in lower_prompt:
                intent = 'reagendamento'
            elif 'orcamento' in lower_prompt:
                intent = 'orcamento'
            return {
                'output': json.dumps({'intent': intent, 'confidence': 0.81}),
                'metadata': {'provider': 'mock', 'task': task},
            }

        if task == 'lead_temperature':
            temperature = 'morno'
            if 'urgente' in lower_prompt or 'fechar hoje' in lower_prompt:
                temperature = 'quente'
            elif 'depois vejo' in lower_prompt:
                temperature = 'frio'
            return {
                'output': json.dumps({'temperature': temperature, 'confidence': 0.76}),
                'metadata': {'provider': 'mock', 'task': task},
            }

        summary = prompt[:300]
        return {
            'output': f'Resumo operacional: {summary}',
            'metadata': {'provider': 'mock', 'task': task},
        }

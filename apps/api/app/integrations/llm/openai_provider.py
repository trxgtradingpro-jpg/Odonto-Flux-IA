import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import settings
from app.integrations.llm.base import LLMProvider


class OpenAILLMProvider(LLMProvider):
    def __init__(self) -> None:
        self.api_key = (settings.llm_api_key or '').strip()
        self.model = (settings.llm_model or 'gpt-4.1-mini').strip()
        self.timeout = max(int(settings.llm_timeout_seconds or 20), 5)
        self.base_url = 'https://api.openai.com/v1'

    @staticmethod
    def _extract_error_detail(response: httpx.Response) -> str:
        try:
            payload = response.json()
            return str(payload)[:600]
        except ValueError:
            return response.text[:600] if response.text else response.reason_phrase

    @staticmethod
    def _normalize_content(content: object) -> str:
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, str):
                    parts.append(item)
                    continue
                if isinstance(item, dict):
                    text = item.get('text')
                    if isinstance(text, str):
                        parts.append(text)
            return '\n'.join(part for part in parts if part).strip()
        return ''

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=6), reraise=True)
    def _post(self, payload: dict) -> tuple[dict, str | None]:
        response = httpx.post(
            f'{self.base_url}/chat/completions',
            json=payload,
            headers={
                'Authorization': f'Bearer {self.api_key}',
                'Content-Type': 'application/json',
            },
            timeout=self.timeout,
        )
        request_id = response.headers.get('x-request-id')
        if response.is_error:
            detail = self._extract_error_detail(response)
            raise httpx.HTTPStatusError(
                f'OpenAI request failed ({response.status_code}): {detail}',
                request=response.request,
                response=response,
            )
        return (response.json() if response.content else {}), request_id

    def complete(self, *, task: str, prompt: str) -> dict:
        if not self.api_key:
            raise RuntimeError('LLM_API_KEY ausente para provider openai.')

        payload: dict = {
            'model': self.model,
            'messages': [
                {
                    'role': 'system',
                    'content': (
                        'Você é um assistente operacional de recepção odontológica. '
                        'Siga estritamente as instruções do prompt do usuário.'
                    ),
                },
                {'role': 'user', 'content': prompt},
            ],
            'temperature': 0.2,
        }

        if task in {'classify_intent', 'lead_temperature'}:
            payload['response_format'] = {'type': 'json_object'}

        data, request_id = self._post(payload)

        choices = data.get('choices') if isinstance(data, dict) else None
        output = ''
        if isinstance(choices, list) and choices:
            first = choices[0] if isinstance(choices[0], dict) else {}
            message = first.get('message') if isinstance(first, dict) else {}
            if isinstance(message, dict):
                output = self._normalize_content(message.get('content'))

        if not output:
            raise RuntimeError('OpenAI retornou resposta vazia.')

        usage = data.get('usage') if isinstance(data, dict) and isinstance(data.get('usage'), dict) else {}
        prompt_tokens = usage.get('prompt_tokens')
        completion_tokens = usage.get('completion_tokens')
        total_tokens = usage.get('total_tokens')

        return {
            'output': output,
            'metadata': {
                'provider': 'openai',
                'model': data.get('model') if isinstance(data, dict) else self.model,
                'task': task,
                'request_id': request_id,
                'prompt_tokens': prompt_tokens if isinstance(prompt_tokens, int) else None,
                'completion_tokens': completion_tokens if isinstance(completion_tokens, int) else None,
                'total_tokens': total_tokens if isinstance(total_tokens, int) else None,
            },
        }

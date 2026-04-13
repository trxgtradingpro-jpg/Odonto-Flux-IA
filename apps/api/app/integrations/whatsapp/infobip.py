import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from app.integrations.whatsapp.base import WhatsAppProvider


class InfobipWhatsAppProvider(WhatsAppProvider):
    def __init__(self, *, base_url: str) -> None:
        raw_base = (base_url or '').strip()
        if raw_base.startswith('http://') or raw_base.startswith('https://'):
            self.base_url = raw_base.rstrip('/')
        else:
            self.base_url = f'https://{raw_base.rstrip("/")}'

    @staticmethod
    def _extract_error_detail(response: httpx.Response) -> str:
        try:
            payload = response.json()
            return str(payload)[:400]
        except ValueError:
            if response.text:
                return response.text[:400]
            return response.reason_phrase

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8), reraise=True)
    def _post(self, *, path: str, api_key: str, payload: dict) -> dict:
        response = httpx.post(
            f'{self.base_url}{path}',
            json=payload,
            headers={
                'Authorization': f'App {api_key}',
                'Content-Type': 'application/json',
                'Accept': 'application/json',
            },
            timeout=20,
        )
        if response.is_error:
            detail = self._extract_error_detail(response)
            raise httpx.HTTPStatusError(
                f'Infobip WhatsApp request failed ({response.status_code}): {detail}',
                request=response.request,
                response=response,
            )
        return response.json() if response.content else {}

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=1, max=4), reraise=True)
    def _get(self, *, path: str, api_key: str) -> dict:
        response = httpx.get(
            f'{self.base_url}{path}',
            headers={
                'Authorization': f'App {api_key}',
                'Accept': 'application/json',
            },
            timeout=15,
        )
        if response.status_code in {404, 405}:
            return {'reachable': True, 'status_code': response.status_code}
        if response.is_error:
            detail = self._extract_error_detail(response)
            raise httpx.HTTPStatusError(
                f'Infobip WhatsApp request failed ({response.status_code}): {detail}',
                request=response.request,
                response=response,
            )
        return response.json() if response.content else {'reachable': True}

    def send_text_message(self, *, phone_number_id: str, access_token: str, to: str, body: str) -> dict:
        payload = {
            'from': phone_number_id,
            'to': to,
            'content': {'text': body},
        }
        try:
            return self._post(path='/whatsapp/1/message/text', api_key=access_token, payload=payload)
        except httpx.HTTPStatusError as exc:
            if exc.response is not None and exc.response.status_code == 400:
                return self._post(
                    path='/whatsapp/1/message/text',
                    api_key=access_token,
                    payload={'messages': [payload]},
                )
            raise

    def send_template_message(
        self,
        *,
        phone_number_id: str,
        access_token: str,
        to: str,
        template_name: str,
        language: str = 'pt_BR',
        components: list[dict] | None = None,
    ) -> dict:
        placeholder_values: list[str] = []
        for component in components or []:
            if not isinstance(component, dict):
                continue
            parameters = component.get('parameters') if isinstance(component.get('parameters'), list) else []
            for parameter in parameters:
                if not isinstance(parameter, dict):
                    continue
                value = parameter.get('text')
                if value:
                    placeholder_values.append(str(value))

        payload = {
            'messages': [
                {
                    'from': phone_number_id,
                    'to': to,
                    'content': {
                        'templateName': template_name,
                        'language': language,
                        'templateData': {
                            'body': {
                                'placeholders': placeholder_values,
                            }
                        },
                    },
                }
            ]
        }
        return self._post(path='/whatsapp/1/message/template', api_key=access_token, payload=payload)

    def test_connection(
        self,
        *,
        phone_number_id: str,
        business_account_id: str | None,
        access_token: str,
    ) -> dict:
        result = self._get(path='/whatsapp/1/senders', api_key=access_token)
        return {
            'reachable': True,
            'sender': phone_number_id,
            'base_url': self.base_url,
            'details': result,
        }

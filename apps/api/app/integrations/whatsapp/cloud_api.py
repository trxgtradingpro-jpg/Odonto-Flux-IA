import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import settings
from app.integrations.whatsapp.base import WhatsAppProvider


class WhatsAppCloudProvider(WhatsAppProvider):
    def __init__(self) -> None:
        self.base_url = settings.whatsapp_api_base_url.rstrip('/')

    @staticmethod
    def _extract_error_detail(response: httpx.Response) -> str:
        try:
            payload = response.json()
        except ValueError:
            return response.text[:300] if response.text else response.reason_phrase

        if isinstance(payload, dict):
            error = payload.get('error')
            if isinstance(error, dict):
                message = str(error.get('message') or '').strip()
                code = error.get('code')
                subcode = error.get('error_subcode')
                parts = []
                if code is not None:
                    parts.append(f'code={code}')
                if subcode is not None:
                    parts.append(f'subcode={subcode}')
                if message:
                    parts.append(message)
                if parts:
                    return ' | '.join(parts)

        return str(payload)[:300]

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8), reraise=True)
    def _post(self, *, url: str, access_token: str, payload: dict) -> dict:
        headers = {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json',
        }
        response = httpx.post(url, json=payload, headers=headers, timeout=20)
        if response.is_error:
            detail = self._extract_error_detail(response)
            raise httpx.HTTPStatusError(
                f'WhatsApp API request failed ({response.status_code}): {detail}',
                request=response.request,
                response=response,
            )
        return response.json()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8), reraise=True)
    def _get(self, *, url: str, access_token: str, params: dict | None = None) -> dict:
        headers = {
            'Authorization': f'Bearer {access_token}',
        }
        response = httpx.get(url, params=params, headers=headers, timeout=20)
        if response.is_error:
            detail = self._extract_error_detail(response)
            raise httpx.HTTPStatusError(
                f'WhatsApp API request failed ({response.status_code}): {detail}',
                request=response.request,
                response=response,
            )
        return response.json()

    def send_text_message(self, *, phone_number_id: str, access_token: str, to: str, body: str) -> dict:
        payload = {
            'messaging_product': 'whatsapp',
            'to': to,
            'type': 'text',
            'text': {'body': body},
        }
        url = f'{self.base_url}/{phone_number_id}/messages'
        return self._post(url=url, access_token=access_token, payload=payload)

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
        payload = {
            'messaging_product': 'whatsapp',
            'to': to,
            'type': 'template',
            'template': {
                'name': template_name,
                'language': {'code': language},
                'components': components or [],
            },
        }
        url = f'{self.base_url}/{phone_number_id}/messages'
        return self._post(url=url, access_token=access_token, payload=payload)

    def test_connection(
        self,
        *,
        phone_number_id: str,
        business_account_id: str | None,
        access_token: str,
    ) -> dict:
        phone_data = self._get(
            url=f'{self.base_url}/{phone_number_id}',
            access_token=access_token,
            params={'fields': 'id,display_phone_number,verified_name'},
        )
        business_data = None
        if business_account_id:
            business_data = self._get(
                url=f'{self.base_url}/{business_account_id}',
                access_token=access_token,
                params={'fields': 'id,name'},
            )
        return {'phone': phone_data, 'business': business_data}

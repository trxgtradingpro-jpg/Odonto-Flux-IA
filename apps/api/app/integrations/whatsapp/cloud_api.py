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

    def send_interactive_list_message(
        self,
        *,
        phone_number_id: str,
        access_token: str,
        to: str,
        body: str,
        button_title: str,
        rows: list[dict],
        section_title: str | None = None,
        header_text: str | None = None,
        footer_text: str | None = None,
    ) -> dict:
        normalized_rows: list[dict] = []
        for index, row in enumerate(rows or [], start=1):
            row_id = str((row or {}).get('id') or f'slot_{index}')[:200]
            title = str((row or {}).get('title') or f'Opção {index}')[:24]
            description = str((row or {}).get('description') or '').strip()[:72]
            item = {'id': row_id, 'title': title}
            if description:
                item['description'] = description
            normalized_rows.append(item)
            if len(normalized_rows) >= 10:
                break

        if not normalized_rows:
            return self.send_text_message(
                phone_number_id=phone_number_id,
                access_token=access_token,
                to=to,
                body=body,
            )

        interactive_payload: dict = {
            'type': 'list',
            'body': {'text': body[:1024]},
            'action': {
                'button': (button_title or 'Opções')[:20],
                'sections': [
                    {
                        'title': (section_title or 'Escolha uma opção')[:24],
                        'rows': normalized_rows,
                    }
                ],
            },
        }
        if header_text:
            interactive_payload['header'] = {'type': 'text', 'text': str(header_text)[:60]}
        if footer_text:
            interactive_payload['footer'] = {'text': str(footer_text)[:60]}

        payload = {
            'messaging_product': 'whatsapp',
            'to': to,
            'type': 'interactive',
            'interactive': interactive_payload,
        }
        url = f'{self.base_url}/{phone_number_id}/messages'
        return self._post(url=url, access_token=access_token, payload=payload)

    def send_interactive_buttons_message(
        self,
        *,
        phone_number_id: str,
        access_token: str,
        to: str,
        body: str,
        buttons: list[dict],
        header_text: str | None = None,
        footer_text: str | None = None,
    ) -> dict:
        normalized_buttons: list[dict] = []
        for index, button in enumerate(buttons or [], start=1):
            button_id = str((button or {}).get('id') or f'btn_{index}')[:200]
            button_title = str((button or {}).get('title') or f'Opção {index}')[:20]
            if not button_id or not button_title:
                continue
            normalized_buttons.append(
                {
                    'type': 'reply',
                    'reply': {
                        'id': button_id,
                        'title': button_title,
                    },
                }
            )
            if len(normalized_buttons) >= 3:
                break

        if not normalized_buttons:
            return self.send_text_message(
                phone_number_id=phone_number_id,
                access_token=access_token,
                to=to,
                body=body,
            )

        interactive_payload: dict = {
            'type': 'button',
            'body': {'text': body[:1024]},
            'action': {'buttons': normalized_buttons},
        }
        if header_text:
            interactive_payload['header'] = {'type': 'text', 'text': str(header_text)[:60]}
        if footer_text:
            interactive_payload['footer'] = {'text': str(footer_text)[:60]}

        payload = {
            'messaging_product': 'whatsapp',
            'to': to,
            'type': 'interactive',
            'interactive': interactive_payload,
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

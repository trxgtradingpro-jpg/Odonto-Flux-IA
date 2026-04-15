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

        content: dict = {
            'body': {'text': body[:1024]},
            'action': {
                'title': (button_title or 'Opções')[:20],
                'sections': [
                    {
                        'title': (section_title or 'Escolha uma opção')[:24],
                        'rows': normalized_rows,
                    }
                ],
            },
        }
        if header_text:
            content['header'] = {'type': 'TEXT', 'text': str(header_text)[:60]}
        if footer_text:
            content['footer'] = {'text': str(footer_text)[:60]}

        payload = {
            'from': phone_number_id,
            'to': to,
            'content': content,
        }
        return self._post(path='/whatsapp/1/message/interactive/list', api_key=access_token, payload=payload)

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
            normalized_buttons.append({'id': button_id, 'title': button_title})
            if len(normalized_buttons) >= 3:
                break

        if not normalized_buttons:
            return self.send_text_message(
                phone_number_id=phone_number_id,
                access_token=access_token,
                to=to,
                body=body,
            )

        content: dict = {
            'body': {'text': body[:1024]},
            'action': {'buttons': normalized_buttons},
        }
        if header_text:
            content['header'] = {'type': 'TEXT', 'text': str(header_text)[:60]}
        if footer_text:
            content['footer'] = {'text': str(footer_text)[:60]}

        payload = {
            'from': phone_number_id,
            'to': to,
            'content': content,
        }
        try:
            return self._post(path='/whatsapp/1/message/interactive/buttons', api_key=access_token, payload=payload)
        except httpx.HTTPStatusError as exc:
            # Fallback defensivo: alguns tenants podem não ter endpoint de buttons habilitado.
            if exc.response is not None and exc.response.status_code in {400, 404, 405}:
                rows = [
                    {
                        'id': item['id'],
                        'title': item['title'],
                        'description': '',
                    }
                    for item in normalized_buttons
                ]
                return self.send_interactive_list_message(
                    phone_number_id=phone_number_id,
                    access_token=access_token,
                    to=to,
                    body=body,
                    button_title='Confirmar',
                    rows=rows,
                    section_title='Confirmação',
                    header_text=header_text,
                    footer_text=footer_text,
                )
            raise

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

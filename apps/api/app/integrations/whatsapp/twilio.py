import json

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from app.integrations.whatsapp.base import WhatsAppProvider


class TwilioWhatsAppProvider(WhatsAppProvider):
    def __init__(self, *, account_sid: str, base_url: str = 'https://api.twilio.com') -> None:
        self.account_sid = (account_sid or '').strip()
        self.base_url = base_url.rstrip('/')

    @staticmethod
    def _extract_error_detail(response: httpx.Response) -> str:
        try:
            payload = response.json()
            return str(payload)[:400]
        except ValueError:
            if response.text:
                return response.text[:400]
            return response.reason_phrase

    @staticmethod
    def _format_whatsapp_number(raw_phone: str) -> str:
        value = (raw_phone or '').strip()
        if not value:
            return value
        if value.lower().startswith('whatsapp:'):
            return value

        digits = ''.join(char for char in value if char.isdigit())
        if not digits:
            return value
        return f'whatsapp:+{digits}'

    @staticmethod
    def _build_template_fallback(template_name: str, components: list[dict] | None) -> str:
        placeholder_values: list[str] = []
        for component in components or []:
            if not isinstance(component, dict):
                continue
            parameters = component.get('parameters') if isinstance(component.get('parameters'), list) else []
            for parameter in parameters:
                if not isinstance(parameter, dict):
                    continue
                value = parameter.get('text')
                if value is not None:
                    placeholder_values.append(str(value))

        if placeholder_values:
            return f'Template {template_name}: {" | ".join(placeholder_values)}'
        return f'Template {template_name}'

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8), reraise=True)
    def _post(self, *, access_token: str, data: dict) -> dict:
        url = f'{self.base_url}/2010-04-01/Accounts/{self.account_sid}/Messages.json'
        response = httpx.post(
            url,
            data=data,
            auth=(self.account_sid, access_token),
            timeout=20,
        )
        if response.is_error:
            detail = self._extract_error_detail(response)
            raise httpx.HTTPStatusError(
                f'Twilio WhatsApp request failed ({response.status_code}): {detail}',
                request=response.request,
                response=response,
            )
        return response.json() if response.content else {}

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=1, max=4), reraise=True)
    def _get(self, *, access_token: str, path: str) -> dict:
        url = f'{self.base_url}{path}'
        response = httpx.get(
            url,
            auth=(self.account_sid, access_token),
            timeout=15,
        )
        if response.is_error:
            detail = self._extract_error_detail(response)
            raise httpx.HTTPStatusError(
                f'Twilio WhatsApp request failed ({response.status_code}): {detail}',
                request=response.request,
                response=response,
            )
        return response.json() if response.content else {}

    def send_text_message(self, *, phone_number_id: str, access_token: str, to: str, body: str) -> dict:
        payload = {
            'From': self._format_whatsapp_number(phone_number_id),
            'To': self._format_whatsapp_number(to),
            'Body': body,
        }
        return self._post(access_token=access_token, data=payload)

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
            'From': self._format_whatsapp_number(phone_number_id),
            'To': self._format_whatsapp_number(to),
        }

        template_name_normalized = (template_name or '').strip()
        if template_name_normalized.upper().startswith('HX'):
            payload['ContentSid'] = template_name_normalized

            variables: dict[str, str] = {}
            index = 1
            for component in components or []:
                if not isinstance(component, dict):
                    continue
                parameters = component.get('parameters') if isinstance(component.get('parameters'), list) else []
                for parameter in parameters:
                    if not isinstance(parameter, dict):
                        continue
                    value = parameter.get('text')
                    if value is None:
                        continue
                    variables[str(index)] = str(value)
                    index += 1

            if variables:
                payload['ContentVariables'] = json.dumps(variables)
        else:
            payload['Body'] = self._build_template_fallback(template_name_normalized or language, components)

        return self._post(access_token=access_token, data=payload)

    def test_connection(
        self,
        *,
        phone_number_id: str,
        business_account_id: str | None,
        access_token: str,
    ) -> dict:
        account_data = self._get(
            access_token=access_token,
            path=f'/2010-04-01/Accounts/{self.account_sid}.json',
        )
        return {
            'reachable': True,
            'sender': phone_number_id,
            'account': account_data,
        }

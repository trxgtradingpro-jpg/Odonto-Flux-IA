from abc import ABC, abstractmethod


class WhatsAppProvider(ABC):
    @abstractmethod
    def send_text_message(self, *, phone_number_id: str, access_token: str, to: str, body: str) -> dict:
        raise NotImplementedError

    @abstractmethod
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
        raise NotImplementedError

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
        # Fallback padrão para providers sem suporte nativo: envia texto simples.
        return self.send_text_message(
            phone_number_id=phone_number_id,
            access_token=access_token,
            to=to,
            body=body,
        )

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
        # Fallback padrão para providers sem suporte nativo: envia texto simples.
        return self.send_text_message(
            phone_number_id=phone_number_id,
            access_token=access_token,
            to=to,
            body=body,
        )

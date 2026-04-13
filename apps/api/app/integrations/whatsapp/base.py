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

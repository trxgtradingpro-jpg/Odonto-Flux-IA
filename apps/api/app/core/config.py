from functools import lru_cache
from typing import Any

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8', case_sensitive=False)

    app_env: str = 'local'
    app_name: str = 'ClinicFlux AI'
    app_timezone: str = 'America/Sao_Paulo'
    default_locale: str = 'pt-BR'
    default_currency: str = 'BRL'
    sentry_dsn: str | None = None

    postgres_db: str = 'odontoflux'
    postgres_user: str = 'odontoflux'
    postgres_password: str = 'odontoflux'
    postgres_host: str = 'postgres'
    postgres_port: int = 5432
    database_url_override: str | None = Field(default=None, validation_alias='DATABASE_URL')

    redis_host: str = 'redis'
    redis_port: int = 6379
    redis_db: int = 0

    api_host: str = '0.0.0.0'
    api_port: int = 8000
    api_cors_origins: list[str] = ['http://localhost:3000']
    api_secret_key: str = 'change_me_super_secret'
    api_access_token_expire_minutes: int = 60 * 8
    api_refresh_token_expire_minutes: int = 60 * 24 * 30
    api_rate_limit_per_minute: int = 120

    celery_broker_url: str = 'redis://redis:6379/0'
    celery_result_backend: str = 'redis://redis:6379/0'

    whatsapp_verify_token: str = 'verify-token-dev'
    whatsapp_access_token: str = ''
    whatsapp_phone_number_id: str = ''
    whatsapp_business_account_id: str = ''
    whatsapp_api_base_url: str = 'https://graph.facebook.com/v19.0'
    whatsapp_inline_dispatch_on_queue: bool = False

    llm_provider: str = 'mock'
    llm_api_key: str | None = None
    llm_model: str = 'gpt-4.1-mini'
    llm_timeout_seconds: int = 20
    ai_autoresponder_prompt_path: str | None = '/app/prompt_editavel.txt'
    audio_transcription_enabled: bool = True
    audio_transcription_model: str = 'base'
    audio_transcription_refined_model: str = 'medium'
    audio_transcription_language: str | None = 'pt'
    audio_transcription_device: str = 'cpu'
    audio_transcription_compute_type: str = 'int8'
    audio_transcription_beam_size: int = 1
    audio_transcription_refined_beam_size: int = 5
    audio_transcription_refined_enabled: bool = True
    audio_transcription_refined_preprocess_enabled: bool = True
    audio_transcription_initial_prompt: str | None = 'Mensagem de voz em portugues do Brasil enviada pelo WhatsApp.'
    audio_transcription_refined_filter: str = 'highpass=f=120, lowpass=f=3800, loudnorm'

    storage_provider: str = 'local'
    storage_base_path: str = '/storage'

    billing_provider: str = 'manual'
    billing_success_url: str = 'http://localhost:3000/faturamento?checkout=success'
    billing_cancel_url: str = 'http://localhost:3000/faturamento?checkout=cancel'
    billing_manual_checkout_url: str = 'https://billing.clinicfluxai.com.br/checkout'
    billing_cycle_days: int = 30
    billing_overdue_grace_days: int = 5
    stripe_secret_key: str | None = None
    stripe_publishable_key: str | None = None
    stripe_webhook_secret: str | None = None

    monitoring_failed_jobs_threshold: int = 5
    monitoring_alert_channels: list[str] = ['email:suporte@clinicfluxai.com.br']

    adm_bootstrap_email: str | None = None
    adm_bootstrap_password: str | None = None
    adm_bootstrap_version: str = '1'
    adm_login_rate_limit_per_minute: int = 8
    demo_access_token_expire_hours: int = 72
    demo_default_expire_days: int = 21
    sales_outreach_sender_tenant_slug: str | None = None
    sales_outreach_display_name: str = 'Time ClinicFlux AI'
    sales_outreach_video_url: str | None = None
    google_places_api_key: str | None = None
    google_places_timeout_seconds: int = 12

    @property
    def database_url(self) -> str:
        if self.database_url_override:
            database_url = self.database_url_override
            if database_url.startswith('postgres://'):
                return f'postgresql+psycopg2://{database_url.removeprefix("postgres://")}'
            if database_url.startswith('postgresql://'):
                return f'postgresql+psycopg2://{database_url.removeprefix("postgresql://")}'
            return database_url
        return (
            f'postgresql+psycopg2://{self.postgres_user}:{self.postgres_password}'
            f'@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}'
        )

    @property
    def redis_url(self) -> str:
        return f'redis://{self.redis_host}:{self.redis_port}/{self.redis_db}'

    @field_validator('api_cors_origins', 'monitoring_alert_channels', mode='before')
    @classmethod
    def _parse_cors(cls, value: Any) -> list[str]:
        if isinstance(value, str):
            return [item.strip() for item in value.split(',') if item.strip()]
        if isinstance(value, list):
            return value
        return []


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

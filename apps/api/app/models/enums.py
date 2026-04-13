from enum import StrEnum


class Scope(StrEnum):
    TENANT = 'tenant'
    PLATFORM = 'platform'


class ConversationStatus(StrEnum):
    OPEN = 'aberta'
    PENDING = 'aguardando'
    CLOSED = 'finalizada'


class MessageDirection(StrEnum):
    INBOUND = 'inbound'
    OUTBOUND = 'outbound'


class MessageStatus(StrEnum):
    QUEUED = 'queued'
    SENT = 'sent'
    DELIVERED = 'delivered'
    READ = 'read'
    FAILED = 'failed'
    RECEIVED = 'received'


class LeadStage(StrEnum):
    NEW = 'novo'
    QUALIFIED = 'qualificado'
    NEGOTIATION = 'negociacao'
    WON = 'ganho'
    LOST = 'perdido'


class LeadTemperature(StrEnum):
    HOT = 'quente'
    WARM = 'morno'
    COLD = 'frio'


class AppointmentStatus(StrEnum):
    SCHEDULED = 'agendada'
    CONFIRMED = 'confirmada'
    RESCHEDULED = 'reagendada'
    CANCELED = 'cancelada'
    NO_SHOW = 'falta'
    COMPLETED = 'concluida'


class AutomationTriggerType(StrEnum):
    EVENT = 'event'
    TIME = 'time'


class RunStatus(StrEnum):
    PENDING = 'pending'
    RUNNING = 'running'
    SUCCESS = 'success'
    FAILED = 'failed'


class CampaignStatus(StrEnum):
    DRAFT = 'rascunho'
    SCHEDULED = 'agendada'
    RUNNING = 'em_execucao'
    PAUSED = 'pausada'
    COMPLETED = 'concluida'


class ConsentStatus(StrEnum):
    GRANTED = 'concedido'
    REVOKED = 'revogado'
    PENDING = 'pendente'


class JobStatus(StrEnum):
    PENDING = 'pending'
    RUNNING = 'running'
    SUCCESS = 'success'
    FAILED = 'failed'


class OutboxStatus(StrEnum):
    PENDING = 'pending'
    PROCESSING = 'processing'
    SENT = 'sent'
    FAILED = 'failed'
    DEAD_LETTER = 'dead_letter'

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class ProfessionalCreate(BaseModel):
    unit_id: UUID | None = None
    full_name: str = Field(min_length=2, max_length=180)
    cro_number: str | None = Field(default=None, max_length=80)
    specialty: str | None = Field(default=None, max_length=120)
    working_days: list[int] = Field(default_factory=lambda: [0, 1, 2, 3, 4])
    shift_start: str = "08:00"
    shift_end: str = "18:00"
    procedures: list[str] = Field(default_factory=list)
    is_active: bool = True

    @field_validator("working_days")
    @classmethod
    def validate_working_days(cls, value: list[int]) -> list[int]:
        cleaned = sorted({int(day) for day in value if 0 <= int(day) <= 6})
        return cleaned or [0, 1, 2, 3, 4]

    @field_validator("shift_start", "shift_end")
    @classmethod
    def validate_shift_time(cls, value: str) -> str:
        text = (value or "").strip()
        parts = text.split(":")
        if len(parts) != 2:
            raise ValueError("Formato de horario invalido. Use HH:MM.")
        hour = int(parts[0])
        minute = int(parts[1])
        if hour < 0 or hour > 23 or minute < 0 or minute > 59:
            raise ValueError("Horario fora do intervalo permitido.")
        return f"{hour:02d}:{minute:02d}"

    @field_validator("procedures")
    @classmethod
    def validate_procedures(cls, value: list[str]) -> list[str]:
        output: list[str] = []
        for item in value:
            text = (item or "").strip()
            if text and text not in output:
                output.append(text[:120])
        return output


class ProfessionalUpdate(BaseModel):
    unit_id: UUID | None = None
    full_name: str | None = Field(default=None, min_length=2, max_length=180)
    cro_number: str | None = Field(default=None, max_length=80)
    specialty: str | None = Field(default=None, max_length=120)
    working_days: list[int] | None = None
    shift_start: str | None = None
    shift_end: str | None = None
    procedures: list[str] | None = None
    is_active: bool | None = None

    @field_validator("working_days")
    @classmethod
    def validate_working_days(cls, value: list[int] | None) -> list[int] | None:
        if value is None:
            return None
        cleaned = sorted({int(day) for day in value if 0 <= int(day) <= 6})
        return cleaned or [0, 1, 2, 3, 4]

    @field_validator("shift_start", "shift_end")
    @classmethod
    def validate_shift_time(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = value.strip()
        parts = text.split(":")
        if len(parts) != 2:
            raise ValueError("Formato de horario invalido. Use HH:MM.")
        hour = int(parts[0])
        minute = int(parts[1])
        if hour < 0 or hour > 23 or minute < 0 or minute > 59:
            raise ValueError("Horario fora do intervalo permitido.")
        return f"{hour:02d}:{minute:02d}"

    @field_validator("procedures")
    @classmethod
    def validate_procedures(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        output: list[str] = []
        for item in value:
            text = (item or "").strip()
            if text and text not in output:
                output.append(text[:120])
        return output


class ProfessionalOutput(BaseModel):
    id: UUID
    tenant_id: UUID
    unit_id: UUID | None
    full_name: str
    cro_number: str | None
    specialty: str | None
    working_days: list[int]
    shift_start: str
    shift_end: str
    procedures: list[str]
    is_active: bool
    created_at: datetime

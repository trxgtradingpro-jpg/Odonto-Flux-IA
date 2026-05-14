from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session
from starlette.responses import FileResponse

from app.api.deps import Principal, get_current_principal, get_tenant_id
from app.core.exceptions import ApiError
from app.db.session import get_db
from app.services.audit_service import record_audit
from app.services.backup_service import (
    BACKUP_SCOPES,
    backup_summary,
    get_backup_file_path,
    run_backup,
    set_backup_config,
)

router = APIRouter(prefix="/backups", tags=["backups"])


class BackupConfigInput(BaseModel):
    enabled: bool = False
    frequency: str = Field(default="daily")
    run_time: str = Field(default="03:00")
    retention_days: int = Field(default=30, ge=1, le=365)
    automatic_scopes: list[str] = Field(default_factory=lambda: ["full"])

    @field_validator("frequency")
    @classmethod
    def _validate_frequency(cls, value: str) -> str:
        value = (value or "daily").strip().lower()
        if value not in {"daily", "weekly", "monthly"}:
            raise ValueError("Frequencia invalida")
        return value

    @field_validator("run_time")
    @classmethod
    def _validate_run_time(cls, value: str) -> str:
        value = (value or "03:00").strip()
        if len(value) != 5 or value[2] != ":":
            raise ValueError("Horario deve estar no formato HH:MM")
        hour, minute = value.split(":", 1)
        if not hour.isdigit() or not minute.isdigit() or int(hour) > 23 or int(minute) > 59:
            raise ValueError("Horario invalido")
        return value

    @field_validator("automatic_scopes")
    @classmethod
    def _validate_scopes(cls, value: list[str]) -> list[str]:
        scopes = [scope for scope in value if scope in BACKUP_SCOPES]
        return scopes or ["full"]


class BackupRunInput(BaseModel):
    scope: str = Field(default="full")

    @field_validator("scope")
    @classmethod
    def _validate_scope(cls, value: str) -> str:
        value = (value or "full").strip()
        if value not in BACKUP_SCOPES:
            raise ValueError("Escopo de backup invalido")
        return value


def _ensure_backup_access(principal: Principal) -> None:
    if {"owner", "manager", "admin_platform"}.intersection(set(principal.roles)):
        return
    raise ApiError(
        status_code=403,
        code="BACKUP_FORBIDDEN",
        message="Acesso ao backup restrito a proprietarios e gestores.",
    )


@router.get("")
def get_backups_dashboard(
    db: Session = Depends(get_db),
    tenant_id=Depends(get_tenant_id),
    principal: Principal = Depends(get_current_principal),
):
    _ensure_backup_access(principal)
    return backup_summary(db, tenant_id=tenant_id)


@router.put("/config")
def update_backup_config(
    payload: BackupConfigInput,
    db: Session = Depends(get_db),
    tenant_id=Depends(get_tenant_id),
    principal: Principal = Depends(get_current_principal),
):
    _ensure_backup_access(principal)
    config = set_backup_config(db, tenant_id=tenant_id, payload=payload.model_dump())
    record_audit(
        db,
        action="backup.config.update",
        entity_type="backup_config",
        entity_id=None,
        tenant_id=tenant_id,
        user_id=principal.user.id,
        metadata={
            "enabled": config.get("enabled"),
            "frequency": config.get("frequency"),
            "automatic_scopes": config.get("automatic_scopes"),
        },
    )
    return config


@router.post("/run")
def run_manual_backup(
    payload: BackupRunInput,
    db: Session = Depends(get_db),
    tenant_id=Depends(get_tenant_id),
    principal: Principal = Depends(get_current_principal),
):
    _ensure_backup_access(principal)
    result = run_backup(
        db,
        tenant_id=tenant_id,
        scope=payload.scope,
        trigger="manual",
        requested_by_user_id=principal.user.id,
    )
    record_audit(
        db,
        action="backup.manual.run",
        entity_type="backup",
        entity_id=result.get("id"),
        tenant_id=tenant_id,
        user_id=principal.user.id,
        metadata={
            "scope": result.get("scope"),
            "status": result.get("status"),
            "size_bytes": result.get("size_bytes"),
            "file_count": result.get("file_count"),
        },
    )
    return result


@router.get("/{backup_id}/download")
def download_backup(
    backup_id: str,
    db: Session = Depends(get_db),
    tenant_id=Depends(get_tenant_id),
    principal: Principal = Depends(get_current_principal),
):
    _ensure_backup_access(principal)
    path = get_backup_file_path(db, tenant_id=tenant_id, backup_id=backup_id)
    record_audit(
        db,
        action="backup.download",
        entity_type="backup",
        entity_id=backup_id,
        tenant_id=tenant_id,
        user_id=principal.user.id,
        metadata={"filename": path.name},
    )
    return FileResponse(path, media_type="application/zip", filename=path.name)

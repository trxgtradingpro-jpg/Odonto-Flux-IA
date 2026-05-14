from __future__ import annotations

from contextlib import contextmanager
import hashlib
import io
import json
import re
import unicodedata
import zipfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from fastapi.encoders import jsonable_encoder
from sqlalchemy import inspect as sa_inspect
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import ApiError
from app.models import (
    AIAutoresponderDecision,
    Appointment,
    AppointmentEvent,
    Automation,
    AutomationRun,
    Campaign,
    CampaignAudience,
    CampaignMessage,
    Consent,
    Conversation,
    ConversationParticipant,
    Document,
    DocumentVersion,
    Lead,
    LeadSource,
    Message,
    MessageEvent,
    OutboxMessage,
    Patient,
    PatientContact,
    PatientTag,
    Professional,
    Setting,
    Tenant,
    Unit,
    User,
    UserRole,
    WhatsAppAccount,
    WhatsAppTemplate,
)
from app.services.storage_service import StorageProviderFactory

BACKUP_CONFIG_KEY = "backup.config"
BACKUP_HISTORY_KEY = "backup.history"
BACKUP_HISTORY_LIMIT = 80
MUTATION_BACKUP_SCOPE = "mutation"
MUTATION_BACKUP_SCOPE_LABEL = "Backup automatico de alteracao"
MUTATION_BACKUP_FORMAT = "odontoflux-mutation-backup-v1"
SKIP_MUTATION_TRACKING_INFO_KEY = "skip_mutation_tracking"


BACKUP_SCOPES: dict[str, dict] = {
    "full": {
        "label": "Backup completo",
        "description": "Dados operacionais, configuracoes, documentos e arquivos do tenant.",
        "models": "all",
        "include_document_files": True,
        "include_storage_files": True,
    },
    "clinic": {
        "label": "Clinica e equipe",
        "description": "Tenant, unidades, profissionais, usuarios, WhatsApp e configuracoes.",
        "models": [Tenant, Unit, Professional, User, UserRole, Setting, WhatsAppAccount, WhatsAppTemplate],
    },
    "patients": {
        "label": "Pacientes e LGPD",
        "description": "Pacientes, contatos, tags, consentimentos e origens.",
        "models": [LeadSource, Patient, PatientContact, PatientTag, Consent],
    },
    "appointments": {
        "label": "Agenda",
        "description": "Consultas, status, confirmacoes e eventos de agenda.",
        "models": [Appointment, AppointmentEvent],
    },
    "conversations": {
        "label": "WhatsApp e IA",
        "description": "Atendimentos do WhatsApp, mensagens, eventos e decisoes do auto-responder.",
        "models": [Conversation, ConversationParticipant, Message, MessageEvent, AIAutoresponderDecision, OutboxMessage],
    },
    "commercial": {
        "label": "Leads e campanhas",
        "description": "Leads, campanhas, automacoes e execucoes comerciais.",
        "models": [Lead, Campaign, CampaignAudience, CampaignMessage, Automation, AutomationRun],
    },
    "documents": {
        "label": "Documentos",
        "description": "Metadados e arquivos anexados aos documentos.",
        "models": [Document, DocumentVersion, Consent],
        "include_document_files": True,
    },
    "files": {
        "label": "Arquivos do storage",
        "description": "Arquivos do tenant no storage local, sem incluir backups antigos.",
        "models": [DocumentVersion],
        "include_storage_files": True,
    },
}

ALL_BACKUP_MODELS = [
    Tenant,
    Unit,
    Professional,
    User,
    UserRole,
    Setting,
    WhatsAppAccount,
    WhatsAppTemplate,
    LeadSource,
    Patient,
    PatientContact,
    PatientTag,
    Lead,
    Conversation,
    ConversationParticipant,
    Message,
    MessageEvent,
    AIAutoresponderDecision,
    OutboxMessage,
    Appointment,
    AppointmentEvent,
    Campaign,
    CampaignAudience,
    CampaignMessage,
    Automation,
    AutomationRun,
    Document,
    DocumentVersion,
    Consent,
]


DEFAULT_BACKUP_CONFIG = {
    "enabled": False,
    "frequency": "daily",
    "run_time": "03:00",
    "retention_days": 30,
    "automatic_scopes": ["full"],
    "last_run_at": None,
    "next_run_at": None,
}


def _setting(db: Session, *, tenant_id: UUID, key: str) -> Setting | None:
    return db.scalar(select(Setting).where(Setting.tenant_id == tenant_id, Setting.key == key))


def _upsert_setting(db: Session, *, tenant_id: UUID, key: str, value: dict, is_secret: bool = False) -> Setting:
    row = _setting(db, tenant_id=tenant_id, key=key)
    if not row:
        row = Setting(tenant_id=tenant_id, key=key, value=value, is_secret=is_secret)
    else:
        row.value = value
        row.is_secret = is_secret
    db.add(row)
    return row


@contextmanager
def _mutation_tracking_disabled(db: Session):
    previous = bool(db.info.get(SKIP_MUTATION_TRACKING_INFO_KEY))
    db.info[SKIP_MUTATION_TRACKING_INFO_KEY] = True
    try:
        yield
    finally:
        if previous:
            db.info[SKIP_MUTATION_TRACKING_INFO_KEY] = True
        else:
            db.info.pop(SKIP_MUTATION_TRACKING_INFO_KEY, None)


def _safe_config(raw: object) -> dict:
    config = dict(DEFAULT_BACKUP_CONFIG)
    if isinstance(raw, dict):
        config.update(raw)

    frequency = str(config.get("frequency") or "daily").strip().lower()
    config["frequency"] = frequency if frequency in {"daily", "weekly", "monthly"} else "daily"

    run_time = str(config.get("run_time") or "03:00").strip()
    if len(run_time) != 5 or run_time[2] != ":":
        run_time = "03:00"
    config["run_time"] = run_time

    try:
        retention_days = int(config.get("retention_days") or 30)
    except (TypeError, ValueError):
        retention_days = 30
    config["retention_days"] = max(1, min(retention_days, 365))

    scopes = config.get("automatic_scopes")
    if not isinstance(scopes, list):
        scopes = ["full"]
    config["automatic_scopes"] = [scope for scope in scopes if scope in BACKUP_SCOPES] or ["full"]
    config["enabled"] = bool(config.get("enabled"))
    return config


def _parse_time(value: str) -> tuple[int, int]:
    try:
        hour, minute = value.split(":", 1)
        return max(0, min(int(hour), 23)), max(0, min(int(minute), 59))
    except (ValueError, TypeError):
        return 3, 0


def calculate_next_run_at(config: dict, *, timezone: str = "America/Sao_Paulo", from_dt: datetime | None = None) -> str | None:
    if not config.get("enabled"):
        return None

    now_utc = from_dt or datetime.now(UTC)
    try:
        tz = ZoneInfo(timezone)
    except Exception:
        tz = ZoneInfo("America/Sao_Paulo")

    local_now = now_utc.astimezone(tz)
    hour, minute = _parse_time(str(config.get("run_time") or "03:00"))
    candidate = local_now.replace(hour=hour, minute=minute, second=0, microsecond=0)

    frequency = str(config.get("frequency") or "daily")
    if candidate <= local_now:
        if frequency == "weekly":
            candidate += timedelta(days=7)
        elif frequency == "monthly":
            candidate += timedelta(days=30)
        else:
            candidate += timedelta(days=1)

    return candidate.astimezone(UTC).isoformat()


def get_backup_config(db: Session, *, tenant_id: UUID) -> dict:
    row = _setting(db, tenant_id=tenant_id, key=BACKUP_CONFIG_KEY)
    return _safe_config(row.value if row else None)


def set_backup_config(db: Session, *, tenant_id: UUID, payload: dict) -> dict:
    tenant = db.get(Tenant, tenant_id)
    config = _safe_config(payload)
    config["next_run_at"] = calculate_next_run_at(config, timezone=tenant.timezone if tenant else "America/Sao_Paulo")
    existing = get_backup_config(db, tenant_id=tenant_id)
    config["last_run_at"] = existing.get("last_run_at")
    _upsert_setting(db, tenant_id=tenant_id, key=BACKUP_CONFIG_KEY, value=config)
    db.commit()
    return config


def list_backup_history(db: Session, *, tenant_id: UUID) -> list[dict]:
    row = _setting(db, tenant_id=tenant_id, key=BACKUP_HISTORY_KEY)
    if not row or not isinstance(row.value, dict):
        return []
    entries = row.value.get("entries")
    return entries if isinstance(entries, list) else []


def _save_backup_history(db: Session, *, tenant_id: UUID, entries: list[dict]) -> None:
    with _mutation_tracking_disabled(db):
        _upsert_setting(
            db,
            tenant_id=tenant_id,
            key=BACKUP_HISTORY_KEY,
            value={"entries": entries[:BACKUP_HISTORY_LIMIT], "updated_at": datetime.now(UTC).isoformat()},
        )
        db.commit()


def _serialize_model_rows(db: Session, *, tenant_id: UUID, model) -> tuple[list[dict], int]:
    if model is Tenant:
        rows = db.execute(select(Tenant).where(Tenant.id == tenant_id)).scalars().all()
    elif hasattr(model, "tenant_id"):
        rows = db.execute(select(model).where(model.tenant_id == tenant_id)).scalars().all()
    else:
        rows = []

    serialized: list[dict] = []
    for row in rows:
        item: dict = {}
        for attr in sa_inspect(model).mapper.column_attrs:
            item[attr.key] = getattr(row, attr.key)
        serialized.append(jsonable_encoder(item))
    return serialized, len(serialized)


def _backup_models_for_scope(scope: str) -> list:
    scope_config = BACKUP_SCOPES[scope]
    models = scope_config.get("models")
    if models == "all":
        return ALL_BACKUP_MODELS
    return list(models or [])


def _storage_base_path() -> Path:
    return Path(settings.storage_base_path).resolve()


def _is_path_inside(candidate: Path, base: Path) -> bool:
    try:
        candidate.resolve().relative_to(base)
        return True
    except ValueError:
        return False


def _add_document_files_to_zip(db: Session, *, tenant_id: UUID, archive: zipfile.ZipFile) -> int:
    base = _storage_base_path()
    versions = db.execute(select(DocumentVersion).where(DocumentVersion.tenant_id == tenant_id)).scalars().all()
    added = 0
    seen: set[Path] = set()
    for version in versions:
        candidate = Path(version.file_path)
        if not candidate.is_absolute():
            candidate = base / candidate
        if not candidate.exists() or not candidate.is_file():
            continue
        resolved = candidate.resolve()
        if resolved in seen or not _is_path_inside(resolved, base):
            continue
        seen.add(resolved)
        archive.write(resolved, f"files/documents/{version.id}_{version.file_name}")
        added += 1
    return added


def _add_tenant_storage_files_to_zip(*, tenant_slug: str, archive: zipfile.ZipFile) -> int:
    base = _storage_base_path()
    tenant_base = (base / tenant_slug).resolve()
    if not tenant_base.exists() or not tenant_base.is_dir() or not _is_path_inside(tenant_base, base):
        return 0

    added = 0
    for path in tenant_base.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(tenant_base)
        if relative.parts and relative.parts[0] == "backups":
            continue
        archive.write(path, f"files/storage/{relative.as_posix()}")
        added += 1
    return added


def _append_history_entry(db: Session, *, tenant_id: UUID, entry: dict) -> None:
    entries = list_backup_history(db, tenant_id=tenant_id)
    entries.insert(0, entry)
    _save_backup_history(db, tenant_id=tenant_id, entries=entries)


def _slugify_backup_part(value: object, *, fallback: str) -> str:
    text = str(value or "").strip()
    if not text:
        return fallback
    normalized = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "-", normalized).strip("-").lower()
    if not cleaned:
        return fallback
    return cleaned[:72]


def _first_present(mapping: dict | None, keys: list[str]) -> str | None:
    if not isinstance(mapping, dict):
        return None
    for key in keys:
        value = mapping.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None


def _mutation_subject_label(*, tracked_items: list[dict], metadata: dict | None, entity_type: str) -> str:
    candidate_keys = [
        "full_name",
        "name",
        "title",
        "key",
        "code",
        "email",
        "file_name",
        "trade_name",
        "legal_name",
        "slug",
        "procedure_type",
        "channel",
        "starts_at",
        "status",
    ]

    for item in tracked_items:
        after_label = _first_present(item.get("after"), candidate_keys)
        if after_label:
            return after_label
        before_label = _first_present(item.get("before"), candidate_keys)
        if before_label:
            return before_label

    metadata_label = _first_present(metadata, candidate_keys)
    if metadata_label:
        return metadata_label
    return entity_type


def _mutation_changed_fields(tracked_items: list[dict], metadata: dict | None) -> list[str]:
    fields: list[str] = []
    for item in tracked_items:
        for field in item.get("changed_fields") or []:
            field_name = str(field).strip()
            if field_name and field_name not in fields:
                fields.append(field_name)

    if not fields and isinstance(metadata, dict):
        changes = metadata.get("changes")
        if isinstance(changes, dict):
            for field in changes.keys():
                field_name = str(field).strip()
                if field_name and field_name not in fields:
                    fields.append(field_name)

    return fields


def _mutation_operation(action: str, tracked_items: list[dict]) -> str:
    if any(item.get("operation") == "delete" for item in tracked_items):
        return "delete"
    if action.endswith(".delete"):
        return "delete"
    return "update"


def _mutation_summary_label(*, action: str, entity_type: str, tracked_items: list[dict], metadata: dict | None) -> str:
    operation = _mutation_operation(action, tracked_items)
    verb = "Excluido" if operation == "delete" else "Alterado"
    subject = _mutation_subject_label(tracked_items=tracked_items, metadata=metadata, entity_type=entity_type)
    changed_fields = _mutation_changed_fields(tracked_items, metadata)
    if operation == "update" and changed_fields:
        return f"{verb}: {entity_type} {subject} ({', '.join(changed_fields[:3])})"
    return f"{verb}: {entity_type} {subject}"


def _mutation_backup_filename(*, started_at: datetime, action: str, entity_type: str, tracked_items: list[dict], metadata: dict | None, backup_id: str) -> str:
    operation = "excluido" if _mutation_operation(action, tracked_items) == "delete" else "alterado"
    subject = _mutation_subject_label(tracked_items=tracked_items, metadata=metadata, entity_type=entity_type)
    changed_fields = _mutation_changed_fields(tracked_items, metadata)

    parts = [
        started_at.strftime("%Y%m%d-%H%M%S"),
        "backup-auto",
        operation,
        _slugify_backup_part(entity_type, fallback="registro"),
        _slugify_backup_part(subject, fallback="item"),
    ]
    if operation == "alterado" and changed_fields:
        parts.append(_slugify_backup_part("-".join(changed_fields[:3]), fallback="mudancas"))
    parts.append(backup_id[:8])
    return f"{'-'.join(part for part in parts if part)}.zip"


def cleanup_expired_backups(db: Session, *, tenant_id: UUID, retention_days: int) -> int:
    cutoff = datetime.now(UTC) - timedelta(days=retention_days)
    entries = list_backup_history(db, tenant_id=tenant_id)
    kept: list[dict] = []
    removed = 0
    base = _storage_base_path()

    for entry in entries:
        finished_at = str(entry.get("finished_at") or entry.get("started_at") or "")
        try:
            finished_dt = datetime.fromisoformat(finished_at.replace("Z", "+00:00"))
        except ValueError:
            kept.append(entry)
            continue

        if finished_dt >= cutoff:
            kept.append(entry)
            continue

        path_text = str(entry.get("path") or "")
        if path_text:
            candidate = Path(path_text)
            try:
                if candidate.exists() and _is_path_inside(candidate, base):
                    candidate.unlink()
            except OSError:
                pass
        removed += 1

    if removed:
        _save_backup_history(db, tenant_id=tenant_id, entries=kept)
    return removed


def run_backup(db: Session, *, tenant_id: UUID, scope: str, trigger: str, requested_by_user_id: UUID | None = None) -> dict:
    if scope not in BACKUP_SCOPES:
        raise ApiError(status_code=400, code="BACKUP_INVALID_SCOPE", message="Escopo de backup invalido.")

    tenant = db.get(Tenant, tenant_id)
    if not tenant:
        raise ApiError(status_code=404, code="TENANT_NOT_FOUND", message="Clinica nao encontrada.")

    started_at = datetime.now(UTC)
    backup_id = str(uuid4())
    row_counts: dict[str, int] = {}
    data: dict[str, list[dict]] = {}
    file_count = 0

    try:
        for model in _backup_models_for_scope(scope):
            rows, count = _serialize_model_rows(db, tenant_id=tenant_id, model=model)
            data[model.__tablename__] = rows
            row_counts[model.__tablename__] = count

        manifest = {
            "id": backup_id,
            "tenant_id": str(tenant_id),
            "tenant_slug": tenant.slug,
            "tenant_name": tenant.trade_name,
            "scope": scope,
            "scope_label": BACKUP_SCOPES[scope]["label"],
            "trigger": trigger,
            "created_at": started_at.isoformat(),
            "format": "odontoflux-backup-v1",
            "row_counts": row_counts,
            "contains_sensitive_data": True,
            "notes": "Arquivo gerado localmente para restauracao/diagnostico controlado do tenant.",
        }

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("manifest.json", json.dumps(jsonable_encoder(manifest), ensure_ascii=False, indent=2))
            archive.writestr("data.json", json.dumps(jsonable_encoder(data), ensure_ascii=False, indent=2))
            if BACKUP_SCOPES[scope].get("include_document_files"):
                file_count += _add_document_files_to_zip(db, tenant_id=tenant_id, archive=archive)
            if BACKUP_SCOPES[scope].get("include_storage_files"):
                file_count += _add_tenant_storage_files_to_zip(tenant_slug=tenant.slug, archive=archive)

        content = buffer.getvalue()
        if not content or len(content) <= 22:
            raise RuntimeError("Backup gerado vazio. Nenhum arquivo foi salvo.")
        if not zipfile.is_zipfile(io.BytesIO(content)):
            raise RuntimeError("Backup gerado nao e um ZIP valido.")
        checksum = hashlib.sha256(content).hexdigest()
        filename = f"{started_at.strftime('%Y%m%d-%H%M%S')}-{scope}-{backup_id[:8]}.zip"
        storage_result = StorageProviderFactory.create().save_bytes(
            tenant_slug=tenant.slug,
            relative_path=f"backups/{filename}",
            content=content,
        )

        finished_at = datetime.now(UTC)
        entry = {
            "id": backup_id,
            "scope": scope,
            "scope_label": BACKUP_SCOPES[scope]["label"],
            "trigger": trigger,
            "status": "success",
            "started_at": started_at.isoformat(),
            "finished_at": finished_at.isoformat(),
            "path": storage_result["path"],
            "filename": filename,
            "size_bytes": storage_result["size_bytes"],
            "checksum": checksum,
            "row_counts": row_counts,
            "file_count": file_count,
            "requested_by_user_id": str(requested_by_user_id) if requested_by_user_id else None,
            "error_message": None,
        }
        _append_history_entry(db, tenant_id=tenant_id, entry=entry)
        return entry
    except Exception as exc:
        entry = {
            "id": backup_id,
            "scope": scope,
            "scope_label": BACKUP_SCOPES[scope]["label"],
            "trigger": trigger,
            "status": "failed",
            "started_at": started_at.isoformat(),
            "finished_at": datetime.now(UTC).isoformat(),
            "path": None,
            "filename": None,
            "size_bytes": 0,
            "checksum": None,
            "row_counts": row_counts,
            "file_count": file_count,
            "requested_by_user_id": str(requested_by_user_id) if requested_by_user_id else None,
            "error_message": str(exc),
        }
        _append_history_entry(db, tenant_id=tenant_id, entry=entry)
        raise


def record_mutation_backup(
    db: Session,
    *,
    tenant_id: UUID | None,
    action: str,
    entity_type: str,
    entity_id: str | None,
    metadata: dict | None,
    tracked_items: list[dict] | None,
    requested_by_user_id: UUID | None = None,
    audit_log_id: UUID | None = None,
) -> dict | None:
    if not tenant_id:
        return None

    tenant = db.get(Tenant, tenant_id)
    if not tenant:
        return None

    tracked_payload = tracked_items or []
    normalized_metadata = jsonable_encoder(metadata or {})
    started_at = datetime.now(UTC)
    backup_id = str(uuid4())
    summary_label = _mutation_summary_label(
        action=action,
        entity_type=entity_type,
        tracked_items=tracked_payload,
        metadata=normalized_metadata,
    )
    filename = _mutation_backup_filename(
        started_at=started_at,
        action=action,
        entity_type=entity_type,
        tracked_items=tracked_payload,
        metadata=normalized_metadata,
        backup_id=backup_id,
    )

    payload = {
        "action": action,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "summary_label": summary_label,
        "metadata": normalized_metadata,
        "tracked_items": tracked_payload,
    }
    if audit_log_id:
        payload["audit_log_id"] = str(audit_log_id)

    manifest = {
        "id": backup_id,
        "tenant_id": str(tenant_id),
        "tenant_slug": tenant.slug,
        "tenant_name": tenant.trade_name,
        "scope": MUTATION_BACKUP_SCOPE,
        "scope_label": MUTATION_BACKUP_SCOPE_LABEL,
        "trigger": action,
        "created_at": started_at.isoformat(),
        "format": MUTATION_BACKUP_FORMAT,
        "contains_sensitive_data": True,
        "notes": summary_label,
        "mutation": {
            "operation": _mutation_operation(action, tracked_payload),
            "entity_type": entity_type,
            "entity_id": entity_id,
            "tracked_items_count": len(tracked_payload),
        },
    }

    try:
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("manifest.json", json.dumps(jsonable_encoder(manifest), ensure_ascii=False, indent=2))
            archive.writestr("data.json", json.dumps(jsonable_encoder(payload), ensure_ascii=False, indent=2))

        content = buffer.getvalue()
        if not content or len(content) <= 22 or not zipfile.is_zipfile(io.BytesIO(content)):
            raise RuntimeError("Backup automatico da alteracao ficou vazio ou invalido.")

        checksum = hashlib.sha256(content).hexdigest()
        storage_result = StorageProviderFactory.create().save_bytes(
            tenant_slug=tenant.slug,
            relative_path=f"backups/{filename}",
            content=content,
        )

        entry = {
            "id": backup_id,
            "scope": MUTATION_BACKUP_SCOPE,
            "scope_label": MUTATION_BACKUP_SCOPE_LABEL,
            "trigger": action,
            "status": "success",
            "started_at": started_at.isoformat(),
            "finished_at": datetime.now(UTC).isoformat(),
            "path": storage_result["path"],
            "filename": filename,
            "size_bytes": storage_result["size_bytes"],
            "checksum": checksum,
            "row_counts": {},
            "file_count": 0,
            "requested_by_user_id": str(requested_by_user_id) if requested_by_user_id else None,
            "error_message": None,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "summary_label": summary_label,
        }
        _append_history_entry(db, tenant_id=tenant_id, entry=entry)
        return entry
    except Exception as exc:
        entry = {
            "id": backup_id,
            "scope": MUTATION_BACKUP_SCOPE,
            "scope_label": MUTATION_BACKUP_SCOPE_LABEL,
            "trigger": action,
            "status": "failed",
            "started_at": started_at.isoformat(),
            "finished_at": datetime.now(UTC).isoformat(),
            "path": None,
            "filename": filename,
            "size_bytes": 0,
            "checksum": None,
            "row_counts": {},
            "file_count": 0,
            "requested_by_user_id": str(requested_by_user_id) if requested_by_user_id else None,
            "error_message": str(exc),
            "entity_type": entity_type,
            "entity_id": entity_id,
            "summary_label": summary_label,
        }
        _append_history_entry(db, tenant_id=tenant_id, entry=entry)
        raise


def get_backup_file_path(db: Session, *, tenant_id: UUID, backup_id: str) -> Path:
    entry = next((item for item in list_backup_history(db, tenant_id=tenant_id) if item.get("id") == backup_id), None)
    if not entry or entry.get("status") != "success":
        raise ApiError(status_code=404, code="BACKUP_NOT_FOUND", message="Backup nao encontrado.")

    path_text = str(entry.get("path") or "")
    path = Path(path_text)
    base = _storage_base_path()
    if not path.exists() or not path.is_file() or not _is_path_inside(path, base):
        raise ApiError(status_code=404, code="BACKUP_FILE_NOT_FOUND", message="Arquivo do backup nao encontrado.")
    if path.stat().st_size <= 22 or not zipfile.is_zipfile(path):
        raise ApiError(
            status_code=409,
            code="BACKUP_FILE_INVALID",
            message="Arquivo do backup esta vazio ou invalido. Gere um novo backup.",
        )
    return path


def backup_summary(db: Session, *, tenant_id: UUID) -> dict:
    config = get_backup_config(db, tenant_id=tenant_id)
    history = list_backup_history(db, tenant_id=tenant_id)
    latest_success = next((item for item in history if item.get("status") == "success"), None)
    total_size = sum(int(item.get("size_bytes") or 0) for item in history if item.get("status") == "success")
    return {
        "config": config,
        "history": history,
        "scopes": [
            {"key": key, **{field: value for field, value in scope.items() if field in {"label", "description"}}}
            for key, scope in BACKUP_SCOPES.items()
        ]
        + [
            {
                "key": MUTATION_BACKUP_SCOPE,
                "label": MUTATION_BACKUP_SCOPE_LABEL,
                "description": "Backups pequenos gerados automaticamente antes de exclusoes e alteracoes auditadas.",
            }
        ],
        "summary": {
            "total_backups": len(history),
            "successful_backups": len([item for item in history if item.get("status") == "success"]),
            "failed_backups": len([item for item in history if item.get("status") == "failed"]),
            "latest_success_at": latest_success.get("finished_at") if latest_success else None,
            "latest_scope": latest_success.get("scope") if latest_success else None,
            "stored_size_bytes": total_size,
        },
    }


def run_due_automatic_backups(db: Session) -> dict:
    now = datetime.now(UTC)
    rows = db.execute(select(Setting).where(Setting.key == BACKUP_CONFIG_KEY)).scalars().all()
    processed = 0
    skipped = 0
    failed = 0

    for row in rows:
        config = _safe_config(row.value)
        if not config.get("enabled"):
            skipped += 1
            continue
        next_run_at = config.get("next_run_at")
        if next_run_at:
            try:
                next_dt = datetime.fromisoformat(str(next_run_at).replace("Z", "+00:00"))
            except ValueError:
                next_dt = now
            if next_dt > now:
                skipped += 1
                continue

        tenant = db.get(Tenant, row.tenant_id)
        for scope in config.get("automatic_scopes") or ["full"]:
            try:
                run_backup(db, tenant_id=row.tenant_id, scope=scope, trigger="automatic")
                processed += 1
            except Exception:
                failed += 1

        config["last_run_at"] = now.isoformat()
        config["next_run_at"] = calculate_next_run_at(config, timezone=tenant.timezone if tenant else "America/Sao_Paulo", from_dt=now)
        _upsert_setting(db, tenant_id=row.tenant_id, key=BACKUP_CONFIG_KEY, value=config)
        cleanup_expired_backups(db, tenant_id=row.tenant_id, retention_days=int(config.get("retention_days") or 30))
        db.commit()

    return {"processed": processed, "skipped": skipped, "failed": failed}

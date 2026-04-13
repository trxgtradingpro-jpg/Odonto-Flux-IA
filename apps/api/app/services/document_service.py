from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import ApiError
from app.models import Document, DocumentVersion, Tenant
from app.services.storage_service import StorageProviderFactory


def create_document(
    db: Session,
    *,
    tenant_id: UUID,
    title: str,
    document_type: str,
    description: str | None,
    patient_id: UUID | None,
    unit_id: UUID | None,
    created_by_user_id: UUID,
    is_sensitive: bool,
) -> Document:
    document = Document(
        tenant_id=tenant_id,
        title=title,
        document_type=document_type,
        description=description,
        patient_id=patient_id,
        unit_id=unit_id,
        created_by_user_id=created_by_user_id,
        storage_provider='local',
        is_sensitive=is_sensitive,
    )
    db.add(document)
    db.commit()
    db.refresh(document)
    return document



def upload_document_version(
    db: Session,
    *,
    tenant_id: UUID,
    document_id: UUID,
    file_name: str,
    mime_type: str,
    content: bytes,
    uploaded_by_user_id: UUID,
    metadata: dict | None = None,
) -> DocumentVersion:
    document = db.scalar(
        select(Document).where(Document.id == document_id, Document.tenant_id == tenant_id)
    )
    if not document:
        raise ApiError(status_code=404, code='DOCUMENT_NOT_FOUND', message='Documento nao encontrado')

    tenant = db.get(Tenant, tenant_id)
    tenant_slug = tenant.slug if tenant else str(tenant_id)

    max_version = db.scalar(
        select(func.max(DocumentVersion.version_number)).where(DocumentVersion.document_id == document.id)
    )
    next_version = (max_version or 0) + 1

    ext = Path(file_name).suffix
    relative = f'documents/{document.id}/v{next_version}_{datetime.now(UTC).timestamp():.0f}{ext}'

    provider = StorageProviderFactory.create()
    stored = provider.save_bytes(tenant_slug=tenant_slug, relative_path=relative, content=content)

    version = DocumentVersion(
        tenant_id=tenant_id,
        document_id=document.id,
        uploaded_by_user_id=uploaded_by_user_id,
        version_number=next_version,
        file_path=stored['path'],
        file_name=file_name,
        mime_type=mime_type,
        size_bytes=stored['size_bytes'],
        checksum=stored['checksum'],
        metadata_json=metadata or {},
    )
    db.add(version)
    db.flush()

    document.current_version_id = version.id
    db.add(document)
    db.commit()
    db.refresh(version)
    return version

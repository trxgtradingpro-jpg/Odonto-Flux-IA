from pathlib import Path

from fastapi import APIRouter, Depends, File, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import Principal, get_current_principal, get_tenant_id
from app.core.exceptions import ApiError
from app.db.session import get_db
from app.models import Document, DocumentVersion
from app.schemas.document import DocumentCreate, DocumentOutput
from app.services.audit_service import record_audit
from app.services.document_service import create_document, upload_document_version

router = APIRouter(prefix='/documents', tags=['documents'])


@router.get('')
def list_documents(
    db: Session = Depends(get_db),
    tenant_id=Depends(get_tenant_id),
    limit: int = Query(default=20, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    patient_id: str | None = None,
):
    stmt = select(Document).where(Document.tenant_id == tenant_id)
    if patient_id:
        stmt = stmt.where(Document.patient_id == patient_id)

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.execute(stmt.order_by(Document.created_at.desc()).offset(offset).limit(limit)).scalars().all()
    return {'data': [DocumentOutput.model_validate(item, from_attributes=True).model_dump() for item in rows], 'meta': {'total': total, 'limit': limit, 'offset': offset}}


@router.post('', response_model=DocumentOutput)
def create_document_record(
    payload: DocumentCreate,
    db: Session = Depends(get_db),
    tenant_id=Depends(get_tenant_id),
    principal: Principal = Depends(get_current_principal),
):
    item = create_document(
        db,
        tenant_id=tenant_id,
        title=payload.title,
        document_type=payload.document_type,
        description=payload.description,
        patient_id=payload.patient_id,
        unit_id=payload.unit_id,
        created_by_user_id=principal.user.id,
        is_sensitive=payload.is_sensitive,
    )

    record_audit(
        db,
        action='document.create',
        entity_type='document',
        entity_id=str(item.id),
        tenant_id=tenant_id,
        user_id=principal.user.id,
        metadata={'document_type': item.document_type},
    )
    return DocumentOutput.model_validate(item, from_attributes=True)


@router.post('/{document_id}/upload')
def upload_document(
    document_id: str,
    file: UploadFile = File(...),
    metadata: str | None = None,
    db: Session = Depends(get_db),
    tenant_id=Depends(get_tenant_id),
    principal: Principal = Depends(get_current_principal),
):
    content = file.file.read()
    if not content:
        raise ApiError(status_code=400, code='FILE_EMPTY', message='Arquivo vazio')

    version = upload_document_version(
        db,
        tenant_id=tenant_id,
        document_id=document_id,
        file_name=file.filename or 'arquivo.bin',
        mime_type=file.content_type or 'application/octet-stream',
        content=content,
        uploaded_by_user_id=principal.user.id,
        metadata={'raw': metadata} if metadata else {},
    )

    record_audit(
        db,
        action='document.upload',
        entity_type='document_version',
        entity_id=str(version.id),
        tenant_id=tenant_id,
        user_id=principal.user.id,
        metadata={'document_id': document_id, 'version': version.version_number},
    )

    return {
        'document_id': document_id,
        'version_id': str(version.id),
        'version': version.version_number,
        'file_name': version.file_name,
        'size_bytes': version.size_bytes,
        'checksum': version.checksum,
    }


@router.get('/{document_id}/versions')
def list_versions(document_id: str, db: Session = Depends(get_db), tenant_id=Depends(get_tenant_id)):
    document = db.scalar(select(Document).where(Document.id == document_id, Document.tenant_id == tenant_id))
    if not document:
        raise ApiError(status_code=404, code='DOCUMENT_NOT_FOUND', message='Documento nao encontrado')

    versions = db.execute(
        select(DocumentVersion)
        .where(DocumentVersion.tenant_id == tenant_id, DocumentVersion.document_id == document.id)
        .order_by(DocumentVersion.version_number.desc())
    ).scalars().all()

    return {
        'data': [
            {
                'id': str(version.id),
                'version_number': version.version_number,
                'file_name': version.file_name,
                'mime_type': version.mime_type,
                'size_bytes': version.size_bytes,
                'uploaded_at': version.uploaded_at,
            }
            for version in versions
        ],
        'meta': {'total': len(versions)},
    }


def _resolve_current_version(
    db: Session,
    *,
    tenant_id,
    document: Document,
) -> DocumentVersion:
    version = None
    if document.current_version_id:
        version = db.scalar(
            select(DocumentVersion).where(
                DocumentVersion.id == document.current_version_id,
                DocumentVersion.tenant_id == tenant_id,
                DocumentVersion.document_id == document.id,
            )
        )

    if not version:
        version = db.scalar(
            select(DocumentVersion)
            .where(DocumentVersion.tenant_id == tenant_id, DocumentVersion.document_id == document.id)
            .order_by(DocumentVersion.version_number.desc())
        )

    if not version:
        raise ApiError(
            status_code=404,
            code='DOCUMENT_VERSION_NOT_FOUND',
            message='Documento sem versao publicada',
        )

    return version


@router.get('/{document_id}/preview')
def preview_document(
    document_id: str,
    db: Session = Depends(get_db),
    tenant_id=Depends(get_tenant_id),
):
    document = db.scalar(select(Document).where(Document.id == document_id, Document.tenant_id == tenant_id))
    if not document:
        raise ApiError(status_code=404, code='DOCUMENT_NOT_FOUND', message='Documento nao encontrado')

    version = _resolve_current_version(db, tenant_id=tenant_id, document=document)
    file_path = Path(version.file_path)
    if not file_path.exists():
        raise ApiError(status_code=404, code='DOCUMENT_FILE_NOT_FOUND', message='Arquivo do documento nao encontrado')

    mime = version.mime_type or ''
    is_text_preview = mime.startswith('text/') or file_path.suffix.lower() in {'.txt', '.md', '.json', '.csv'}
    if not is_text_preview:
        return {
            'document_id': document_id,
            'file_name': version.file_name,
            'mime_type': version.mime_type,
            'preview_text': None,
            'preview_available': False,
            'message': 'Preview textual indisponivel para este tipo de arquivo',
        }

    max_chars = 4000
    content = file_path.read_text(encoding='utf-8', errors='ignore')
    truncated = len(content) > max_chars
    preview_text = content[:max_chars]
    return {
        'document_id': document_id,
        'file_name': version.file_name,
        'mime_type': version.mime_type,
        'preview_text': preview_text,
        'preview_available': True,
        'truncated': truncated,
    }


@router.get('/{document_id}/download')
def download_document(
    document_id: str,
    db: Session = Depends(get_db),
    tenant_id=Depends(get_tenant_id),
    principal: Principal = Depends(get_current_principal),
):
    document = db.scalar(select(Document).where(Document.id == document_id, Document.tenant_id == tenant_id))
    if not document:
        raise ApiError(status_code=404, code='DOCUMENT_NOT_FOUND', message='Documento nao encontrado')

    version = _resolve_current_version(db, tenant_id=tenant_id, document=document)
    file_path = Path(version.file_path)
    if not file_path.exists():
        raise ApiError(status_code=404, code='DOCUMENT_FILE_NOT_FOUND', message='Arquivo do documento nao encontrado')

    record_audit(
        db,
        action='document.download',
        entity_type='document',
        entity_id=str(document.id),
        tenant_id=tenant_id,
        user_id=principal.user.id,
        metadata={'version_id': str(version.id), 'file_name': version.file_name},
    )

    return FileResponse(
        path=str(file_path),
        media_type=version.mime_type or 'application/octet-stream',
        filename=version.file_name,
    )

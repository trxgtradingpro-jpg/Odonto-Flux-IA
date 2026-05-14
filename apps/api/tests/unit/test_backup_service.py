import json
import zipfile
from pathlib import Path

import pytest

from app.core.exceptions import ApiError
from app.models import Patient
from app.services import backup_service
from app.services.audit_service import record_audit


def test_run_backup_persists_non_empty_zip(monkeypatch, seeded_db, db_session, tmp_path):
    tenant_id = seeded_db["tenant_a"].id
    monkeypatch.setattr(backup_service.settings, "storage_base_path", str(tmp_path))

    entry = backup_service.run_backup(
        db_session,
        tenant_id=tenant_id,
        scope="full",
        trigger="manual",
    )

    path = Path(entry["path"])
    assert entry["status"] == "success"
    assert entry["size_bytes"] > 22
    assert path.exists()
    assert zipfile.is_zipfile(path)

    with zipfile.ZipFile(path, "r") as archive:
        names = set(archive.namelist())
    assert "manifest.json" in names
    assert "data.json" in names


def test_get_backup_file_path_rejects_empty_or_invalid_zip(monkeypatch, seeded_db, db_session, tmp_path):
    tenant_id = seeded_db["tenant_a"].id
    monkeypatch.setattr(backup_service.settings, "storage_base_path", str(tmp_path))

    entry = backup_service.run_backup(
        db_session,
        tenant_id=tenant_id,
        scope="full",
        trigger="manual",
    )

    path = Path(entry["path"])
    path.write_bytes(b"")

    with pytest.raises(ApiError) as exc_info:
        backup_service.get_backup_file_path(db_session, tenant_id=tenant_id, backup_id=entry["id"])

    assert exc_info.value.code == "BACKUP_FILE_INVALID"


def test_record_audit_creates_mutation_backup_for_updated_patient(monkeypatch, seeded_db, db_session, tmp_path):
    tenant_id = seeded_db["tenant_a"].id
    owner_id = seeded_db["owner_a"].id
    monkeypatch.setattr(backup_service.settings, "storage_base_path", str(tmp_path))

    patient = Patient(
        tenant_id=tenant_id,
        full_name="Ana Costa",
        phone="11999990000",
        normalized_phone="11999990000",
        status="ativo",
        origin="teste",
    )
    db_session.add(patient)
    db_session.commit()
    db_session.refresh(patient)

    patient.full_name = "Ana Costa Almeida"
    db_session.add(patient)
    db_session.commit()
    db_session.refresh(patient)

    record_audit(
        db_session,
        action="patient.update",
        entity_type="patient",
        entity_id=str(patient.id),
        tenant_id=tenant_id,
        user_id=owner_id,
        metadata={"changes": {"full_name": patient.full_name}},
    )

    history = backup_service.list_backup_history(db_session, tenant_id=tenant_id)
    assert len(history) == 1
    entry = history[0]
    assert entry["scope"] == backup_service.MUTATION_BACKUP_SCOPE
    assert "alterado-patient" in entry["filename"]

    with zipfile.ZipFile(Path(entry["path"]), "r") as archive:
        payload = json.loads(archive.read("data.json"))

    assert payload["action"] == "patient.update"
    assert payload["tracked_items"][0]["operation"] == "update"
    assert payload["tracked_items"][0]["before"]["full_name"] == "Ana Costa"
    assert payload["tracked_items"][0]["after"]["full_name"] == "Ana Costa Almeida"


def test_record_audit_creates_mutation_backup_for_deleted_patient(monkeypatch, seeded_db, db_session, tmp_path):
    tenant_id = seeded_db["tenant_a"].id
    owner_id = seeded_db["owner_a"].id
    monkeypatch.setattr(backup_service.settings, "storage_base_path", str(tmp_path))

    patient = Patient(
        tenant_id=tenant_id,
        full_name="Carlos Pereira",
        phone="11999991111",
        normalized_phone="11999991111",
        status="ativo",
        origin="teste",
    )
    db_session.add(patient)
    db_session.commit()
    patient_id = str(patient.id)

    db_session.delete(patient)
    db_session.commit()

    record_audit(
        db_session,
        action="patient.delete",
        entity_type="patient",
        entity_id=patient_id,
        tenant_id=tenant_id,
        user_id=owner_id,
        metadata={"full_name": "Carlos Pereira"},
    )

    history = backup_service.list_backup_history(db_session, tenant_id=tenant_id)
    assert len(history) == 1
    entry = history[0]
    assert entry["scope"] == backup_service.MUTATION_BACKUP_SCOPE
    assert "excluido-patient" in entry["filename"]

    with zipfile.ZipFile(Path(entry["path"]), "r") as archive:
        payload = json.loads(archive.read("data.json"))

    assert payload["action"] == "patient.delete"
    assert payload["tracked_items"][0]["operation"] == "delete"
    assert payload["tracked_items"][0]["before"]["full_name"] == "Carlos Pereira"
    assert payload["tracked_items"][0]["after"] is None


def test_record_audit_falls_back_to_metadata_only_when_no_tracked_snapshot(monkeypatch, seeded_db, db_session, tmp_path):
    tenant_id = seeded_db["tenant_a"].id
    owner = seeded_db["owner_a"]
    monkeypatch.setattr(backup_service.settings, "storage_base_path", str(tmp_path))

    record_audit(
        db_session,
        action="user.update",
        entity_type="user",
        entity_id=str(owner.id),
        tenant_id=tenant_id,
        user_id=owner.id,
        metadata={"changes": {"roles": ["owner", "receptionist"]}},
    )

    history = backup_service.list_backup_history(db_session, tenant_id=tenant_id)
    assert len(history) == 1
    entry = history[0]
    assert entry["scope"] == backup_service.MUTATION_BACKUP_SCOPE

    with zipfile.ZipFile(Path(entry["path"]), "r") as archive:
        payload = json.loads(archive.read("data.json"))

    assert payload["tracked_items"] == []
    assert payload["metadata"]["changes"]["roles"] == ["owner", "receptionist"]

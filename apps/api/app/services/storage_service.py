import hashlib
from pathlib import Path

from app.core.config import settings


class LocalStorage:
    def __init__(self) -> None:
        self.base_path = Path(settings.storage_base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)

    def save_bytes(self, *, tenant_slug: str, relative_path: str, content: bytes) -> dict:
        directory = self.base_path / tenant_slug / Path(relative_path).parent
        directory.mkdir(parents=True, exist_ok=True)

        target = self.base_path / tenant_slug / relative_path
        target.write_bytes(content)

        checksum = hashlib.sha256(content).hexdigest()
        return {
            'path': str(target),
            'checksum': checksum,
            'size_bytes': len(content),
        }


class StorageProviderFactory:
    @staticmethod
    def create():
        return LocalStorage()

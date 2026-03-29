# app/services/backup_container.py

import os
from pathlib import Path
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.backends import default_backend
import json
import secrets
from typing import Dict, Any, Optional

CONFIG_DIR = Path.home() / ".cryptobase"
CONTAINER_PATH = CONFIG_DIR / "backups.enc"


class BackupContainerError(Exception):
    """Базовое исключение для ошибок контейнера"""


class BackupContainer:
    """
    Простой зашифрованный контейнер для всех бэкапов в одном файле.
    Формат:
    [16 байт nonce] + [зашифрованный JSON payload] + [16 байт tag]
    """

    def __init__(self, master_key: bytes):
        self.master_key = master_key
        self.data: Dict[str, list] = {"files": {}}  # {file_id: [versions...]}
        self._load()

    def _load(self):
        """Загружает и расшифровывает контейнер, если он существует"""
        if not CONTAINER_PATH.exists():
            self.data = {"files": {}}
            return

        try:
            with open(CONTAINER_PATH, "rb") as f:
                data = f.read()

            if len(data) < 32:  # минимум nonce + tag
                raise BackupContainerError("Повреждённый контейнер")

            nonce = data[:16]
            ciphertext = data[16:]

            aesgcm = AESGCM(self.master_key)
            plaintext = aesgcm.decrypt(nonce, ciphertext, None)

            self.data = json.loads(plaintext.decode('utf-8'))

        except InvalidTag:
            raise BackupContainerError("Неверный ключ или повреждён контейнер")
        except Exception as e:
            raise BackupContainerError(f"Ошибка чтения контейнера: {e}")

    def _save(self):
        """Шифрует и сохраняет текущие данные"""
        plaintext = json.dumps(self.data, ensure_ascii=False, separators=(',', ':')).encode('utf-8')

        aesgcm = AESGCM(self.master_key)
        nonce = secrets.token_bytes(16)
        ciphertext = aesgcm.encrypt(nonce, plaintext, None)

        with open(CONTAINER_PATH, "wb") as f:
            f.write(nonce + ciphertext)

    def add_version(self, file_id: str, version_data: Dict[str, Any]):
        """
        Добавляет новую версию бэкапа для файла
        version_data пример:
        {
            "version_id": 1,
            "created_at": "2026-01-13T12:00:00",
            "hash": "abc123...",
            "comment": "Автосохранение",
            "content": b"binary content..."   # ← сырые байты файла
        }
        """
        if file_id not in self.data["files"]:
            self.data["files"][file_id] = []

        self.data["files"][file_id].append(version_data)
        self._save()

    def get_latest_version(self, file_id: str) -> Optional[Dict[str, Any]]:
        """Возвращает последнюю версию для файла или None"""
        if file_id in self.data["files"] and self.data["files"][file_id]:
            return self.data["files"][file_id][-1]
        return None

    def get_all_versions(self, file_id: str) -> list:
        """Все версии для конкретного файла"""
        return self.data["files"].get(file_id, [])

    def list_files(self) -> list:
        """Список всех file_id в контейнере"""
        return list(self.data["files"].keys())

    def delete_version(self, file_id: str, version_index: int):
        """Удаляет конкретную версию"""
        if file_id in self.data["files"]:
            versions = self.data["files"][file_id]
            if 0 <= version_index < len(versions):
                del versions[version_index]
                if not versions:
                    del self.data["files"][file_id]
                self._save()
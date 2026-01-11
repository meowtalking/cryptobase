import os
import shutil
import json
from datetime import datetime as dt
from pathlib import Path
from app.services.security import decrypt_file
from app.models import FileRecord, FileVersion
from app.services.integrity_manager import compute_hash, now_msk
from app.db import SessionLocal
import hashlib
db = SessionLocal()


class AutoBackupManager:
    def __init__(self, config_path="/Users/macbook/PycharmProjects/cryptobase/app/ui/settings.json"):
        self.config_path = config_path
        self._load_config()

    def _load_config(self):
        if not os.path.exists(self.config_path):
            raise FileNotFoundError(f"Не найден файл конфигурации: {self.config_path}")

        with open(self.config_path, "r", encoding="utf-8") as f:
            config = json.load(f)

        self.max_versions = int(config.get("max_versions", 5))
        self.local_backup = Path(config.get("local_backup_path", "/Users/macbook/backups"))
        self.local_backup.mkdir(parents=True, exist_ok=True)

    def _cleanup_old_backups(self, file_id: int, filename: str):
        backups = sorted(
            self.local_backup.glob(f"{file_id}_*_{filename}"),
            key=lambda p: p.stat().st_mtime,
            reverse=True
        )
        if len(backups) > self.max_versions:
            for old_backup in backups[self.max_versions:]:
                try:
                    old_backup.unlink()
                    print(f"[BACKUP] Удалена старая версия: {old_backup}")
                except Exception as e:
                    print(f"[BACKUP] Не удалось удалить {old_backup}: {e}")





    def create_backup(self, file_record: FileRecord, password: str = None):
        """
        Создаёт резервную копию файла только если она уникальна,
        добавляет запись в БД и удаляет устаревшие версии.
        """
        if not os.path.exists(file_record.path):
            print(f"[BACKUP] Файл не найден: {file_record.path}")
            return None

        filename = os.path.basename(file_record.path)
        file_id = file_record.id

        # Получаем содержимое файла
        if file_record.password_hash and password:
            data = decrypt_file(file_record.path, password)
        else:
            with open(file_record.path, "rb") as f:
                data = f.read()

        # Проверка дубликата по хэшу
        new_hash = compute_hash_bytes(data)
        backups = list(self.local_backup.glob(f"{file_id}_*_{filename}"))
        for backup in backups:
            if compute_hash(backup) == new_hash:
                print(f"[BACKUP] Дубликат версии найден — бэкап не создаётся")
                return None

        # Создаём уникальный бэкап
        timestamp = dt.now().strftime("%Y%m%d%H%M%S")
        dest_path = self.local_backup / f"{file_id}_{timestamp}_{filename}"
        with open(dest_path, "wb") as f:
            f.write(data)

        # Создаём запись в БД
        version = FileVersion(
            file_id=file_id,
            version_hash=new_hash,
            created_at=now_msk(),
            comment="Авто-бэкап",
            location="local"
        )
        db.add(version)
        db.commit()

        # Очистка старых
        self._cleanup_old_backups(file_id, filename)

        print(f"[BACKUP] Создан новый бэкап: {dest_path}")
        return dest_path


def compute_hash_bytes(data: bytes) -> str:
    """Вычисляет SHA256-хэш по байтовым данным."""
    hasher = hashlib.sha256()
    hasher.update(data)
    return hasher.hexdigest()
import os
import shutil
import json
from datetime import datetime
from pathlib import Path

class AutoBackupManager:
    def __init__(self, config_path="config.json", max_versions: int = 5):
        """
        :param config_path: путь к config.json
        :param max_versions: максимальное количество хранимых версий каждого файла
        """
        self.config_path = config_path
        self.max_versions = max_versions
        self._load_config()

    def _load_config(self):
        """Загружает пути резервного копирования из config.json"""
        if not os.path.exists(self.config_path):
            raise FileNotFoundError(f"Не найден конфиг: {self.config_path}")

        with open(self.config_path, "r", encoding="utf-8") as f:
            config = json.load(f)

        self.local_backup = Path(config.get("backup_path", "./backups"))
        self.external_backup = Path(config.get("external_backup_path", ""))

        # Создаём папку, если нет
        self.local_backup.mkdir(parents=True, exist_ok=True)

    def _get_backup_destination(self):
        """Определяет, куда сохранять: на носитель или локально"""
        if self.external_backup and self.external_backup.exists():
            return self.external_backup
        return self.local_backup

    def _cleanup_old_backups(self, file_id: int, filename: str, dest_root: Path):
        """Удаляет старые копии, оставляя только последние self.max_versions"""
        backups = sorted(
            dest_root.glob(f"{file_id}_*_{filename}"),
            key=lambda p: p.stat().st_mtime,
            reverse=True
        )
        if len(backups) > self.max_versions:
            for old_backup in backups[self.max_versions:]:
                try:
                    old_backup.unlink()
                    print(f"[AUTO-BACKUP] Удалена старая копия: {old_backup}")
                except Exception as e:
                    print(f"[AUTO-BACKUP] Не удалось удалить {old_backup}: {e}")

    def create_backup(self, file_path: str, file_id: int):
        """Создаёт резервную копию файла на доступном носителе и выполняет ротацию"""
        if not os.path.exists(file_path):
            print(f"[!] Файл не найден: {file_path}")
            return None

        dest_root = self._get_backup_destination()
        dest_root.mkdir(parents=True, exist_ok=True)

        filename = os.path.basename(file_path)
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        backup_filename = f"{file_id}_{timestamp}_{filename}"
        dest_path = dest_root / backup_filename

        try:
            shutil.copy2(file_path, dest_path)
            print(f"[AUTO-BACKUP] Сохранено: {dest_path}")

            # Удаляем старые версии
            self._cleanup_old_backups(file_id, filename, dest_root)

            return dest_path
        except Exception as e:
            print(f"[Ошибка резервного копирования]: {e}")
            return None

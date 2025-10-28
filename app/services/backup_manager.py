import datetime
from pathlib import Path
from typing import List

import os
import shutil
from datetime import datetime
from sqlalchemy.orm import Session
from app.models import FileRecord, FileVersion

BACKUP_DIR = "backups"  # локальная директория для резервных копий
os.makedirs(BACKUP_DIR, exist_ok=True)

def create_backup(db: Session, file_id: int):
    """Создаёт резервную копию файла и хранит только последние 5 версий."""
    file_record = db.query(FileRecord).filter(FileRecord.id == file_id).first()
    if not file_record:
        raise ValueError(f"Файл с ID={file_id} не найден.")

    if not os.path.exists(file_record.path):
        raise FileNotFoundError(f"Файл {file_record.path} не найден.")

    # Путь для резервной копии
    timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    filename = os.path.basename(file_record.path)
    backup_filename = f"{file_record.id}_{timestamp}_{filename}"
    backup_path = os.path.join(BACKUP_DIR, backup_filename)

    shutil.copy2(file_record.path, backup_path)

    # Добавляем запись версии
    version = FileVersion(
        file_id=file_record.id,
        version_hash=file_record.current_hash,
        created_at=datetime.utcnow(),
        comment="Авто-резервная копия",
        location="local"
    )
    db.add(version)
    db.commit()

    # Оставляем только последние 5 версий
    versions = db.query(FileVersion).filter(FileVersion.file_id == file_id).order_by(FileVersion.created_at.desc()).all()
    for old_version in versions[5:]:
        old_path = os.path.join(BACKUP_DIR, f"{old_version.file_id}_{old_version.created_at.strftime('%Y%m%d%H%M%S')}_{filename}")
        if os.path.exists(old_path):
            os.remove(old_path)
        db.delete(old_version)
    db.commit()

    return backup_path

def get_last_versions(db: Session, file_id: int, limit: int = 5):
    """Возвращает последние версии файла (объекты FileVersion)"""
    versions = (
        db.query(FileVersion)
        .filter(FileVersion.file_id == file_id)
        .order_by(FileVersion.created_at.desc())
        .limit(limit)
        .all()
    )
    return versions

def restore_backup(db: Session, file_id: int, version_id: int):
    """
    Восстанавливает файл из резервной копии.

    :param db: SQLAlchemy сессия
    :param file_id: ID файла в БД
    :param version_id: ID версии резервной копии
    """
    # Получаем версию резервной копии
    version = db.query(FileVersion).filter(
        FileVersion.id == version_id,
        FileVersion.file_id == file_id
    ).first()
    if not version:
        raise ValueError(f"Версия {version_id} для файла {file_id} не найдена.")

    # Получаем информацию о файле
    file_record = db.query(FileRecord).filter(FileRecord.id == file_id).first()
    if not file_record:
        raise ValueError(f"Файл с ID={file_id} не найден.")

    # Формируем путь к резервной копии
    filename = os.path.basename(file_record.path)
    timestamp = version.created_at.strftime("%Y%m%d%H%M%S")
    backup_filename = f"{file_record.id}_{timestamp}_{filename}"
    backup_path = os.path.join(BACKUP_DIR, backup_filename)

    if not os.path.exists(backup_path):
        raise FileNotFoundError(f"Резервная копия {backup_path} не найдена.")

    # Копируем резервную копию на место исходного файла
    shutil.copy2(backup_path, file_record.path)

    # Обновляем хэш и время последнего изменения
    file_record.current_hash = version.version_hash
    file_record.updated_at = datetime.utcnow()
    db.commit()

    print(f"[RESTORE] Файл {file_record.path} восстановлен из копии {backup_path}")


class BackupManager:
    """
    Менеджер резервного копирования файлов.
    Хранит до 5 последних версий каждого файла.
    """

    def __init__(self, backup_root: str = "backups"):
        """
        :param backup_root: Корневая директория для резервных копий.
        """
        self.backup_root = Path(backup_root)
        self.backup_root.mkdir(parents=True, exist_ok=True)

    def _get_backup_dir(self, file_path: str) -> Path:
        """
        Возвращает путь к директории резервных копий для данного файла.
        """
        file_name = Path(file_path).name
        backup_dir = self.backup_root / file_name
        backup_dir.mkdir(parents=True, exist_ok=True)
        return backup_dir

    def _list_backups(self, file_path: str) -> List[Path]:
        """
        Возвращает список резервных копий для данного файла, отсортированный по дате (новые — первыми).
        """
        backup_dir = self._get_backup_dir(file_path)
        backups = sorted(
            backup_dir.glob("*"),
            key=lambda p: p.stat().st_mtime,
            reverse=True
        )
        return backups

    def create_backup(self, file_path: str):
        """
        Создаёт резервную копию файла и выполняет ротацию старых копий.
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Файл '{file_path}' не найден, невозможно создать резервную копию.")

        backup_dir = self._get_backup_dir(file_path)
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_name = f"{Path(file_path).stem}_{timestamp}{Path(file_path).suffix}"
        backup_path = backup_dir / backup_name

        shutil.copy2(file_path, backup_path)
        print(f"[BACKUP] Создана резервная копия: {backup_path}")

        # Ограничиваем количество копий до 5
        backups = self._list_backups(file_path)
        if len(backups) > 5:
            for old_backup in backups[5:]:
                try:
                    os.remove(old_backup)
                    print(f"[ROTATION] Удалена старая резервная копия: {old_backup}")
                except Exception as e:
                    print(f"[ERROR] Не удалось удалить {old_backup}: {e}")

    def restore_backup(self, file_path: str, version_index: int = 0):
        """
        Восстанавливает файл из резервной копии.
        :param file_path: путь к исходному файлу
        :param version_index: индекс резервной копии (0 — последняя, 1 — предыдущая и т.д.)
        """
        backups = self._list_backups(file_path)
        if not backups:
            raise FileNotFoundError(f"Резервные копии для '{file_path}' не найдены.")

        if version_index >= len(backups):
            raise IndexError(f"Недопустимый индекс. Доступно {len(backups)} версий.")

        backup_to_restore = backups[version_index]
        shutil.copy2(backup_to_restore, file_path)
        print(f"[RESTORE] Файл восстановлен из копии: {backup_to_restore}")

    def list_backups(self, file_path: str):
        """
        Выводит список доступных резервных копий.
        """
        backups = self._list_backups(file_path)
        if not backups:
            print("Нет резервных копий.")
            return

        print(f"Доступные резервные копии для {file_path}:")
        for i, b in enumerate(backups):
            ts = datetime.datetime.fromtimestamp(b.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
            print(f"  [{i}] {b.name} — {ts}")


# ========================
# Пример использования
# ========================
if __name__ == "__main__":
    manager = BackupManager("app_backups")

    # Путь к тестовому файлу
    test_file = "example.txt"

    # Создаём файл, если его нет
    if not os.path.exists(test_file):
        with open(test_file, "w") as f:
            f.write("Исходное содержимое файла.\n")

    # Создание резервной копии
    manager.create_backup(test_file)

    # Изменяем файл вручную
    with open(test_file, "a") as f:
        f.write("Добавлена новая строка.\n")

    # Создание второй резервной копии
    manager.create_backup(test_file)

    # Просмотр всех копий
    manager.list_backups(test_file)

    # Восстановление из предыдущей версии
    manager.restore_backup(test_file, version_index=1)

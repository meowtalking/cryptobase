import os
import hashlib
from datetime import datetime
from sqlalchemy.orm import Session
from app.models import FileRecord, FileVersion, LogEntry, SessionLocal
from datetime import datetime
from zoneinfo import ZoneInfo

MOSCOW_TZ = ZoneInfo("Europe/Moscow")

# --- Хэшируем только SHA-256 ---
def compute_hash(file_path: str) -> str:
    """Вычисляет SHA-256 хэш файла"""
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            h.update(chunk)
    return h.hexdigest()



def add_file(file_path: str, password_hash: str = None):
    abs_path = os.path.abspath(file_path)  # сохраняем абсолютный путь

    if not os.path.isfile(abs_path):
        raise FileNotFoundError(f"Файл не найден: {abs_path}")

    session: Session = SessionLocal()
    try:
        from app.services.integrity_manager import now_msk
        name = os.path.basename(abs_path)
        current_hash = compute_hash(abs_path)

        # Проверка, есть ли файл в базе
        existing = session.query(FileRecord).filter(FileRecord.path == abs_path).first()
        if existing:
            print(f"Файл уже добавлен в базу: {abs_path}")
            return existing


        # Создаём запись в локальной БД
        file_record = FileRecord(
            name=name,
            path=abs_path,
            algorithm="sha256",
            current_hash=current_hash,
            password_hash=password_hash,
            created_at=now_msk(),
            updated_at=now_msk()
        )
        session.add(file_record)
        session.commit()

        # === Создаём бэкап сразу после добавления файла ===
        from app.services.AutoBackupManager import AutoBackupManager
        backup_manager = AutoBackupManager("/Users/macbook/PycharmProjects/cryptobase/config.json")
        try:
            backup_path = backup_manager.create_backup(file_record)
            if backup_path:
                print(f"[BACKUP] Создан бэкап для {file_record.name}")
        except Exception as e:
            print(f"[BACKUP ERROR] Не удалось создать бэкап: {e}")

        # Логируем добавление файла
        log = LogEntry(
            action="add_file",
            file_name=file_record.name,
            result="success",
            user_name=os.getlogin(),
            timestamp=now_msk()
        )
        session.add(log)
        session.commit()

        return file_record
    finally:
        session.close()



def delete_file(file_id: int):
    session: Session = SessionLocal()
    try:
        file_record = session.query(FileRecord).filter(FileRecord.id == file_id).first()
        if not file_record:
            print("Файл не найден")
            return
        name = file_record.name
        session.delete(file_record)
        log = LogEntry(
            action="delete_file",
            file_name=name,
            result="success",
            user_name=os.getlogin()
        )
        session.add(log)
        session.commit()
        print(f"Файл удален: {name}")
    finally:
        session.close()

def add_version(file_id: int, file_path: str, comment: str = "Automatic version"):
    session = SessionLocal()
    try:
        from app.services.integrity_manager import now_msk

        file_record = session.query(FileRecord).filter(FileRecord.id == file_id).first()
        if not file_record:
            raise ValueError("Файл не найден в БД")

        new_hash = compute_hash(file_path)
        version = FileVersion(
            file_id=file_id,
            version_hash=new_hash,
            created_at=now_msk(),
            comment=comment,
            location="local"
        )
        session.add(version)
        file_record.current_hash = new_hash
        file_record.updated_at = datetime.utcnow()
        session.commit()

        # Удаляем старые версии, если их больше 5
        versions = session.query(FileVersion).filter(FileVersion.file_id==file_id, FileVersion.location=="local").order_by(FileVersion.created_at.desc()).all()
        if len(versions) > 5:
            for old_version in versions[5:]:
                session.delete(old_version)
        session.commit()

        # Логирование
        log = LogEntry(
            action="add_version",
            file_name=file_record.name,
            result="success",
            user_name=os.getlogin()
        )
        session.add(log)
        session.commit()

        print(f"Добавлена новая версия для файла: {file_record.name}")
        return version
    finally:
        session.close()

def get_last_versions(file_id: int):
    session: Session = SessionLocal()
    try:
        versions = session.query(FileVersion).filter(FileVersion.file_id == file_id).order_by(FileVersion.created_at.desc()).limit(5).all()
        return versions
    finally:
        session.close()

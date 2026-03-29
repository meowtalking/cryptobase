import os
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import FileRecord, FileVersion, LogEntry
from app.services.file_manager import compute_hash, now_msk

MOSCOW_TZ = ZoneInfo("Europe/Moscow")




def create_version(
    db: Session,
    file_record: FileRecord,
    content_bytes: bytes,
    comment: str = "Автоматическая версия",
    location: str = "container:backups.enc"
) -> FileVersion:
    """
    Создаёт новую версию файла:
    - добавляет запись в FileVersion
    - обновляет current_hash и updated_at в FileRecord
    - логирует действие
    """
    new_hash = compute_hash(file_record.path)

    version = FileVersion(
        file_id=file_record.id,
        version_hash=new_hash,
        created_at=now_msk(),
        comment=comment,
        location=location
    )
    db.add(version)

    file_record.current_hash = new_hash
    file_record.updated_at = now_msk()
    db.commit()

    _log_action(
        db=db,
        action="add_version",
        file_name=file_record.name,
        result="success",
        comment=comment
    )

    return version


def _log_action(
    db: Session,
    action: str,
    file_name: str,
    result: str,
    user_name: str = None
):
    """Универсальное логирование (только важные события)"""
    if result in ("OK", "NoChange"):
        return

    log = LogEntry(
        action=action,
        file_name=file_name,
        result=result,
        user_name=user_name or os.getlogin(),
        timestamp=now_msk()
    )
    db.add(log)
    db.commit()


def update_file_hash(db: Session, file_record: FileRecord, new_algorithm: str = None) -> str:
    """
    Пересчитывает и обновляет хэш файла (для ручного обновления).
    Возвращает новый хэш.
    """
    if not os.path.exists(file_record.path):
        raise FileNotFoundError(f"Файл не найден: {file_record.path}")

    if new_algorithm:
        file_record.algorithm = new_algorithm

    new_hash = compute_hash(file_record.path)
    file_record.current_hash = new_hash
    file_record.updated_at = now_msk()

    db.commit()

    _log_action(
        db=db,
        action="update_hash",
        file_name=file_record.name,
        result="Updated"
    )

    return new_hash


def check_file_integrity(db: Session, file_id: int) -> str:
    """
    Проверяет целостность файла по хэшу.
    Возвращает статус: "OK", "Modified", "Missing".
    Если изменился — создаёт новую версию.
    """
    file_record = db.query(FileRecord).filter(FileRecord.id == file_id).first()
    if not file_record:
        raise ValueError(f"Файл с ID={file_id} не найден")

    if not os.path.exists(file_record.path):
        file_record.status = "Missing"
        _log_action(db, "check_integrity", file_record.name, "Missing")
        db.commit()
        return "Missing"

    current_hash = compute_hash(file_record.path)

    last_version = (
        db.query(FileVersion)
        .filter(FileVersion.file_id == file_id)
        .order_by(FileVersion.created_at.desc())
        .first()
    )
    last_hash = last_version.version_hash if last_version else file_record.current_hash

    if current_hash == last_hash:
        if file_record.status != "OK":
            file_record.status = "OK"
            db.commit()
        return "OK"

    file_record.status = "Modified"
    file_record.current_hash = current_hash
    file_record.updated_at = now_msk()

    existing = db.query(FileVersion).filter(
        FileVersion.file_id == file_id,
        FileVersion.version_hash == current_hash
    ).first()

    if not existing:
        version = FileVersion(
            file_id=file_id,
            version_hash=current_hash,
            created_at=now_msk(),
            comment="Изменение обнаружено системой"
        )
        db.add(version)
        _log_action(db, "check_integrity", file_record.name, "Modified")

    db.commit()
    return "Modified"
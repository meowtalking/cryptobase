import os
from datetime import datetime
from sqlalchemy.orm import Session
from app.models import FileRecord, FileVersion, LogEntry
from app.services.security import compute_hash


# ===================================
# 🧩 Проверка целостности файла
# ===================================

import os
from datetime import datetime
from sqlalchemy.orm import Session
from app.models import FileRecord, FileVersion, LogEntry
from app.services.security import compute_hash


def check_file_integrity(db: Session, file_id: int):
    """
    Проверяет целостность файла:
    - сравнивает текущий хэш с последней сохранённой версией;
    - обновляет статус (OK / Modified / Missing);
    - добавляет новую версию и лог только при изменении.
    """
    file_record = db.query(FileRecord).filter(FileRecord.id == file_id).first()
    if not file_record:
        raise ValueError(f"Файл с ID={file_id} не найден.")

    # Если файл удалён
    if not os.path.exists(file_record.path):
        file_record.status = "Missing"
        _log_action(db, "check_integrity", file_record.name, "Missing")
        db.commit()
        return "Missing"

    # Вычисляем текущий хэш
    current_hash = compute_hash(file_record.path, file_record.algorithm)

    # Берём последнюю зафиксированную версию
    last_version = (
        db.query(FileVersion)
        .filter(FileVersion.file_id == file_record.id)
        .order_by(FileVersion.created_at.desc())
        .first()
    )
    last_hash = last_version.version_hash if last_version else file_record.current_hash

    # Сравниваем хэши
    if current_hash == last_hash:
        # Файл не изменялся
        if file_record.status != "OK":
            file_record.status = "OK"
            db.commit()
        return "OK"

    # --- Файл изменился ---
    file_record.status = "Modified"
    file_record.current_hash = current_hash
    file_record.updated_at = datetime.utcnow()

    # Проверяем, что версия с таким хэшем ещё не существует (чтобы не дублировать)
    existing_version = (
        db.query(FileVersion)
        .filter(FileVersion.file_id == file_record.id, FileVersion.version_hash == current_hash)
        .first()
    )

    if not existing_version:
        version = FileVersion(
            file_id=file_record.id,
            version_hash=current_hash,
            created_at=datetime.utcnow(),
            comment="Изменение обнаружено системой"
        )
        db.add(version)
        _log_action(db, "check_integrity", file_record.name, "Modified")

    db.commit()
    return "Modified"


def _log_action(db: Session, action: str, file_name: str, result: str, user_name: str = None):
    """
    Добавляет запись в лог только для важных событий.
    """
    if result not in ("Modified", "Missing", "Updated"):
        return  # не логируем "OK"

    log = LogEntry(
        action=action,
        file_name=file_name,
        result=result,
        user_name=user_name,
        timestamp=datetime.utcnow()
    )
    db.add(log)
    db.commit()

# ===================================
# ♻️ Обновление эталонного хэша
# ===================================

def update_file_hash(db: Session, file_id: int, algorithm: str = None):
    """
    Пересчитывает и обновляет эталонный хэш файла.
    Используется, если файл изменился осознанно (например, обновление конфигурации).
    """
    file_record = db.query(FileRecord).filter(FileRecord.id == file_id).first()
    if not file_record:
        raise ValueError(f"Файл с ID={file_id} не найден.")

    if not os.path.exists(file_record.path):
        raise FileNotFoundError(f"Файл {file_record.path} не найден.")

    if algorithm:
        file_record.algorithm = algorithm

    new_hash = compute_hash(file_record.path, file_record.algorithm)
    file_record.current_hash = new_hash
    file_record.updated_at = datetime.utcnow()

    # Создаём новую версию
    version = FileVersion(
        file_id=file_record.id,
        version_hash=new_hash,
        created_at=datetime.utcnow(),
        comment="Хэш обновлён пользователем"
    )
    db.add(version)

    _log_action(db, "update_hash", file_record.name, "Updated")
    db.commit()

    return new_hash


# ===================================
# 🧾 Логирование действий системы
# ===================================

# def _log_action(db: Session, action: str, file_name: str, result: str, user_name: str = None):
#     log = LogEntry(
#         action=action,
#         file_name=file_name,
#         result=result,
#         user_name=user_name,
#         timestamp=datetime.utcnow()
#     )
#     db.add(log)
#     db.commit()


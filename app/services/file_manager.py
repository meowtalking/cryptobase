import getpass
import os
import hashlib
from datetime import datetime
from sqlalchemy.orm import Session
from app.models import FileRecord, FileVersion, LogEntry, SessionLocal
from app.services.auto_backup_manager import AutoBackupManager

# --- Вспомогательные функции для хэширования ---
HASH_ALGORITHMS = {
    "md5": hashlib.md5,
    "sha1": hashlib.sha1,
    "sha256": hashlib.sha256,
    "sha3_256": hashlib.sha3_256,  # более быстрый, но тоже безопасный вариант
}

def compute_hash(file_path: str, algorithm: str = "sha256") -> str:
    """Вычисляет хэш файла выбранным алгоритмом"""
    if algorithm not in HASH_ALGORITHMS:
        raise ValueError(f"Unsupported algorithm: {algorithm}")
    hash_func = HASH_ALGORITHMS[algorithm]()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_func.update(chunk)
    return hash_func.hexdigest()

# --- Функции работы с БД ---
def add_file(file_path: str, algorithm: str = "sha256", password_hash: str = None):
    if not os.path.isfile(file_path):
        raise FileNotFoundError(f"Файл не найден: {file_path}")

    session = SessionLocal()
    try:
        name = os.path.basename(file_path)
        current_hash = compute_hash(file_path, algorithm)

        file_record = FileRecord(
            name=name,
            path=file_path,
            algorithm=algorithm,
            current_hash=current_hash,
            password_hash=password_hash,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        session.add(file_record)
        session.commit()
        session.flush()

        # 🧠 После добавления файла — создаём автокопию
        try:
            backup_manager = AutoBackupManager("/Users/macbook/PycharmProjects/cryptobase/config.json")
            backup_manager.create_backup(file_path, file_record.id)
        except Exception as e:
            print(f"[!] Ошибка автокопирования: {e}")

        print(f"✅ Файл добавлен и сохранён: {name}")
        return file_record
    finally:
        session.close()


def delete_file(file_id: int):
    """Удаляет файл и все его версии"""
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
    """Добавляет новую версию файла и удаляет старые, если их больше 5"""
    session: Session = SessionLocal()
    try:
        file_record = session.query(FileRecord).filter(FileRecord.id == file_id).first()
        if not file_record:
            raise ValueError("Файл не найден в БД")

        new_hash = compute_hash(file_path, file_record.algorithm)

        # Создаем новую версию
        version = FileVersion(
            file_id=file_id,
            version_hash=new_hash,
            created_at=datetime.utcnow(),
            comment=comment,
            location="local"
        )
        session.add(version)
        file_record.current_hash = new_hash
        file_record.updated_at = datetime.utcnow()
        session.commit()

        # Удаляем старые версии, если их больше 5
        versions = session.query(FileVersion).filter(FileVersion.file_id == file_id, FileVersion.location=="local").order_by(FileVersion.created_at.desc()).all()
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
    finally:
        session.close()


def get_last_versions(file_id: int):
    """Возвращает последние 5 версий файла"""
    session: Session = SessionLocal()
    try:
        versions = session.query(FileVersion).filter(FileVersion.file_id == file_id).order_by(FileVersion.created_at.desc()).limit(5).all()
        return versions
    finally:
        session.close()

# --- Тестирование CRUD локально ---
if __name__ == "__main__":
    # Пример добавления файла
    test_file_path = "/Users/macbook/Documents/test.txt"
    file_record = add_file(test_file_path, "sha256")

    # Добавление новой версии
    add_version(file_record.id, test_file_path, comment="Updated version")

    # Получение последних 5 версий
    versions = get_last_versions(file_record.id)
    print("Последние версии:")
    for v in versions:
        print(v)

    # Удаление файла
    # delete_file(file_record.id)

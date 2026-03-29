import os
import hashlib
from datetime import datetime

from PyQt5.QtWidgets import QInputDialog, QLineEdit
from sqlalchemy.orm import Session
from app.models import FileRecord, FileVersion, LogEntry, SessionLocal
from datetime import datetime
from zoneinfo import ZoneInfo

from app.services.backup_container import BackupContainer

from app.services.security import encrypt_file, decrypt_file, hash_password_for_db

MOSCOW_TZ = ZoneInfo("Europe/Moscow")


def now_msk() -> datetime:
    """Текущее время в Москве (UTC+3)"""
    return datetime.now(MOSCOW_TZ)

# --- Хэшируем только SHA-256 ---
def compute_hash(file_path: str) -> str:
    """Вычисляет SHA-256 хэш файла"""
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            h.update(chunk)
    return h.hexdigest()

def add_file_new(file_path: str, password: str = None, master_key: bytes = None):
    """
    Добавление файла с нуля, с правильной обработкой ошибок и поддержкой отмены
    
    Args:
        file_path: Путь к файлу
        password: Пароль для шифрования (опционально)
        master_key: Мастер-ключ для контейнера (опционально)
    
    Returns:
        FileRecord: Запись о файле в базе данных
    
    Raises:
        Exception: При ошибках добавления файла
    """
    session = SessionLocal()
    
    try:
        # Проверка существования файла
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Файл не найден: {file_path}")
        
        file_path_obj = Path(file_path)
        name = file_path_obj.name
        abs_path = str(file_path_obj.absolute())
        
        # Проверка дубликатов
        existing = session.query(FileRecord).filter(FileRecord.path == abs_path).first()
        if existing:
            raise ValueError(f"Файл уже добавлен: {abs_path}")
        
        # Вычисление хэшей
        plaintext_hash = compute_hash(abs_path)
        
        # Чтение оригинального контента для контейнера
        with open(abs_path, "rb") as f:
            content = f.read()
        
        # Шифрование файла если нужен пароль
        current_hash = plaintext_hash
        password_hash = None
        
        if password:
            password_hash = hash_password_for_db(password)
            encrypt_file(abs_path, password)
            current_hash = compute_hash(abs_path)
            print(f"[ADD_FILE_NEW] Файл зашифрован: {name}")
        else:
            print(f"[ADD_FILE_NEW] Файл добавлен без шифрования: {name}")
        
        # Создание записи в БД
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
        session.refresh(file_record)
        
        # Создание версии в БД
        initial_version = FileVersion(
            file_id=file_record.id,
            version_hash=current_hash,
            created_at=now_msk(),
            comment="Initial version",
            location="container:backups.enc"
        )
        session.add(initial_version)
        session.commit()
        
        # Добавление версии в контейнер (plaintext)
        if master_key:
            container = BackupContainer(master_key)
            file_id_str = str(file_record.id)
            versions_before = container.get_all_versions(file_id_str)
            
            version_data = {
                "version_id": len(versions_before) + 1,
                "created_at": now_msk().isoformat(),
                "hash": plaintext_hash,
                "comment": "Initial version",
                "content": content.hex()  # Храним plaintext
            }
            
            container.add_version(file_id_str, version_data)
            print(f"[ADD_FILE_NEW] Версия добавлена в контейнер: {name}")
        
        # Логирование операции
        log = LogEntry(
            action="add_file",
            file_name=name,
            result="success",
            user_name=os.getlogin(),
            timestamp=now_msk()
        )
        session.add(log)
        session.commit()
        
        print(f"[ADD_FILE_NEW] Файл успешно добавлен: {name} (ID: {file_record.id})")
        return file_record
        
    except Exception as e:
        session.rollback()
        print(f"[ADD_FILE_NEW] Ошибка: {e}")
        raise
    finally:
        session.close()
    abs_path = os.path.abspath(file_path)

    if not os.path.isfile(abs_path):
        raise FileNotFoundError(f"Файл не найден: {abs_path}")

    session = SessionLocal()
    try:
        name = os.path.basename(abs_path)

        # Хэш от plaintext файла (для контейнера)
        plaintext_hash = compute_hash(abs_path)

        existing = session.query(FileRecord).filter(FileRecord.path == abs_path).first()
        if existing:
            print(f"Файл уже добавлен: {abs_path}")
            return existing

        # Хэш пароля (если передан plaintext)
        password_hash = hash_password_for_db(password) if password else None

        print(f"[ADD FILE DEBUG] Plaintext хэш: {plaintext_hash[:12]}...")

        # Читаем содержимое для версии (plaintext до шифрования)
        with open(abs_path, "rb") as f:
            content = f.read()

        # Шифруем файл, если передан пароль (ПОСЛЕ чтения контента)
        current_hash = plaintext_hash  # по умолчанию хэш от plaintext
        if password:
            print(f"[ADD FILE] Шифруем файл {abs_path} паролем...")
            encrypt_file(abs_path, password)
            print("[ADD FILE] Файл зашифрован")
            # Перевычисляем хэш для зашифрованного файла
            current_hash = compute_hash(abs_path)
            print(f"[ADD FILE DEBUG] Хэш зашифрованного файла: {current_hash[:12]}...")
        else:
            print(f"[ADD FILE DEBUG] Файл не шифруется, используем plaintext хэш: {current_hash[:12]}...")

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
        session.refresh(file_record)

        initial_version = FileVersion(
            file_id=file_record.id,
            version_hash=current_hash,
            created_at=now_msk(),
            comment="Initial version",
            location="container:backups.enc"
        )
        session.add(initial_version)
        session.commit()

        # Контейнер — plaintext
        if master_key:
            container = BackupContainer(master_key)
            file_id_str = str(file_record.id)
            versions_before = container.get_all_versions(file_id_str)

            version_data = {
                "version_id": len(versions_before) + 1,
                "created_at": now_msk().isoformat(),
                "hash": plaintext_hash,  # хэш от plaintext контента
                "comment": "Initial version",
                "content": content.hex()
            }

            container.add_version(file_id_str, version_data)
            print(f"[INITIAL BACKUP] Создана версия для {file_record.name} (всего: {len(container.get_all_versions(file_id_str))})")

        log = LogEntry(
            action="add_file",
            file_name=file_record.name,
            result="success",
            user_name=os.getlogin()
        )
        session.add(log)
        session.commit()

        return file_record

    except Exception as e:
        session.rollback()
        raise
    finally:
        session.close()

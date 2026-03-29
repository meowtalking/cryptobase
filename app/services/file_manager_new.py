#!/usr/bin/env python3
"""
New file manager with proper file addition logic
"""

import os
import hashlib
from datetime import datetime, timezone

# Add project to path
project_root = os.path.dirname(os.path.dirname(__file__))
import sys
sys.path.insert(0, str(project_root))

from app.services.security import encrypt_file, hash_password_for_db
from app.services.backup_container import BackupContainer
from app.db import SessionLocal
from app.models import FileRecord, FileVersion, LogEntry

# Moscow timezone
MOSCOW_TZ = datetime.now().astimezone().tzinfo

def now_msk():
    """Current time in Moscow timezone"""
    return datetime.now(MOSCOW_TZ)

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
        
        # Используем os.path для совместимости
        name = os.path.basename(file_path)
        abs_path = os.path.abspath(file_path)
        
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

if __name__ == "__main__":
    """Test the new function"""
    import tempfile
    from PyQt5.QtWidgets import QApplication
    
    # Create test file
    with tempfile.NamedTemporaryFile(mode='w+b', delete=False, suffix='.txt') as f:
        f.write(b"Test content for new file manager")
        test_file = f.name
    
    try:
        # Test without password
        print("=== Test without password ===")
        record1 = add_file_new(test_file, password=None, master_key=b"0123456789abcdef0123456789abcdef")
        print(f"Success: {record1.name} (ID: {record1.id})")
        
        # Test with password
        print("\n=== Test with password ===")
        record2 = add_file_new(test_file, password="TestPass123!", master_key=b"0123456789abcdef0123456789abcdef")
        print(f"Success: {record2.name} (ID: {record2.id})")
        
        print("\n✅ All tests passed!")
        
    finally:
        import os
        os.unlink(test_file)

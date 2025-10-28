# app/services/sync_service.py
import os
import asyncio
import hashlib
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from minio import Minio
from minio.error import S3Error
from datetime import datetime
from app.models import FileRecord, FileVersion
from sqlalchemy.orm import Session

# --- Настройка клиента MinIO ---
MINIO_ENDPOINT = "localhost:9000"
MINIO_ACCESS_KEY = "minioadmin"
MINIO_SECRET_KEY = "minioadmin"
BUCKET_NAME = "cryptobase-backups"

client = Minio(
    MINIO_ENDPOINT,
    access_key=MINIO_ACCESS_KEY,
    secret_key=MINIO_SECRET_KEY,
    secure=False  # локально http
)

# Создаём бакет, если его нет
if not client.bucket_exists(BUCKET_NAME):
    client.make_bucket(BUCKET_NAME)


# ===========================================
# 🔐 Шифрование и дешифрование файлов
# ===========================================

def encrypt_file(file_path: str, key: bytes) -> bytes:
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)
    with open(file_path, "rb") as f:
        data = f.read()
    ct = aesgcm.encrypt(nonce, data, None)
    return nonce + ct  # сохраняем nonce в начале

def decrypt_file(encrypted_data: bytes, key: bytes) -> bytes:
    aesgcm = AESGCM(key)
    nonce = encrypted_data[:12]
    ct = encrypted_data[12:]
    return aesgcm.decrypt(nonce, ct, None)

def compute_sha512(file_path: str) -> str:
    h = hashlib.sha512()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            h.update(chunk)
    return h.hexdigest()


# ===========================================
# ⬆️ Асинхронная загрузка и скачивание
# ===========================================

async def upload_backup(db: Session, file_id: int, key: bytes):
    file_record = db.query(FileRecord).filter(FileRecord.id == file_id).first()
    if not file_record:
        raise ValueError(f"Файл ID={file_id} не найден")

    # Шифруем файл
    encrypted = encrypt_file(file_record.path, key)

    # Вычисляем хэш
    file_hash = hashlib.sha512(encrypted).hexdigest()

    # Формируем имя объекта
    obj_name = f"{file_record.id}/{datetime.utcnow().isoformat()}.backup"

    # Загружаем в MinIO
    try:
        client.put_object(
            BUCKET_NAME,
            obj_name,
            data=encrypted,
            length=len(encrypted),
            content_type="application/octet-stream"
        )
    except S3Error as e:
        raise RuntimeError(f"Ошибка загрузки: {e}")

    # Добавляем запись в версии
    version = FileVersion(
        file_id=file_record.id,
        version_hash=file_hash,
        created_at=datetime.utcnow(),
        comment="Удалённая резервная копия",
        location="remote"
    )
    db.add(version)
    db.commit()

    # Удаляем старые версии >5
    versions = db.query(FileVersion).filter(
        FileVersion.file_id == file_record.id,
        FileVersion.location == "remote"
    ).order_by(FileVersion.created_at.desc()).all()

    for v in versions[5:]:
        try:
            obj_to_delete = f"{file_record.id}/{v.created_at.isoformat()}.backup"
            client.remove_object(BUCKET_NAME, obj_to_delete)
        except Exception:
            pass
        db.delete(v)
    db.commit()
    return obj_name


async def download_backup(db: Session, file_id: int, version_id: int, key: bytes, dest_path: str):
    version = db.query(FileVersion).filter(FileVersion.id == version_id).first()
    if not version:
        raise ValueError("Версия не найдена")

    obj_name = f"{file_id}/{version.created_at.isoformat()}.backup"
    try:
        response = client.get_object(BUCKET_NAME, obj_name)
        encrypted = response.read()
    except S3Error as e:
        raise RuntimeError(f"Ошибка скачивания: {e}")

    data = decrypt_file(encrypted, key)
    with open(dest_path, "wb") as f:
        f.write(data)

    # Проверяем целостность
    if hashlib.sha512(encrypted).hexdigest() != version.version_hash:
        raise RuntimeError("Хэш файла не совпадает после скачивания!")

    return dest_path


# ===========================================
# ⏳ Асинхронный фон
# ===========================================

async def sync_all_files(db: Session, key: bytes):
    files = db.query(FileRecord).all()
    tasks = [upload_backup(db, f.id, key) for f in files]
    await asyncio.gather(*tasks)
